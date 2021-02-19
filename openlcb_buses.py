import socket,select
import openlcb_cmri_cfg as cmri
import serial,json
import openlcb_server
import openlcb_nodes,time
import openlcb_nodes_db as nodes_db
import openlcb_RR_duino_nodes as RR_duino
from openlcb_debug import *
from openlcb_protocol import *
from collections import deque
from openlcb_cmri_cfg import hex_int

class Bus:
    separator ="\n"
    def __init__(self,name,path_to_nodes_files=None):
        self.name = name
        self.clients=[]       #client programs connected to the bus
        self.nodes_in_alias_negotiation=[]  #alias negotiations (node,alias_neg)
        self.path_to_nodes_files=path_to_nodes_files  #path to files describing the nodes

    def __str__(self):
        return "Bus: "+self.name

    def generate_frames_from_alias_neg(self):
        frames_list=[]
        for node,alias_neg in self.nodes_in_alias_negotiation:
            #debug("alias",alias_neg.aliasID," step",alias_neg.step,alias_neg.last_emit)
            if alias_neg.step < 6:
                alias_neg.step+=1
                emit = True
                if alias_neg.step < 5:
                    frame = Frame.build_CID(node,alias_neg)
                    #timestamp, we need that to make sure we wait 200ms between last CID and RID
                    alias_neg.last_emit=time.time()
                elif alias_neg.step==5:
                    if time.time()>alias_neg.last_emit+0.2:
                        #200ms has elapsed since CID 4 so emit RID
                        frame = Frame.build_RID(node)
                        #update reserved aliases
                        reserved_aliases[node.aliasID]=node.ID
                        #also delete the negotiation from the list
                        list_alias_neg.remove(alias_neg)
                    else:
                        alias_neg.step-=1   #back to step 4, we'll retry RID next time
                        emit = False
                else:
                    #emit AMD
                    frame = Frame.build_AMD(node)
                    node.permitted = True
                    debug("node of ID",node.ID," alias ",node.aliasID," now in permitted state")
                if emit:
                    frames_list.append(frame)
        return frames_list

    def prune_alias_negotiation(self):
        #we delete all finished alias negotiation and populate the reserved aliases list accordingly
        to_delete=deque()
        for i in range(len(self.nodes_in_alias_negotiation)):
            if self.nodes_in_alias_negotiation[i][1].step == 6:
                debug("deleting alias negotiation",i)
                to_delete.appendleft(i)
        #remove the clients who just connected from the unconnected list
        for index in to_delete:
            self.nodes_in_alias_negotiation.pop(index)

class Cmri_net_bus(Bus):
    """
    message format (messages are separated by a ";", also number is presented as an hexdecimal string):
    - space separated (only ONE space) word and numbers/CMRI message (distinguished by the 2 SYN chars at the beginning)
    Message types (other than the CMRI message)
    - New node: "start_node" followed by: full_ID(8 bytes)
    """
    nodes_db_file = "cmri_net_bus_db.cfg"
    POLL_TIMEOUT = 0.3  #poll every 300ms
    def __init__(self,path_to_nodes_files):
        super().__init__(Bus_manager.cmri_net_bus_name,path_to_nodes_files)
        self.nodes_db = nodes_db.Nodes_db_CMRI(self.path_to_nodes_files+Cmri_net_bus.nodes_db_file)
        self.nodes_db.load_all_nodes()
        self.last_poll = time.time()

        
    def process(self):
        #check all messages and return a list of events that has been generated in response
        #also checks all alias negotiation and return the corresponding can frames (CID,AMD,...)
        ev_list=[]
        for c in self.clients:
            msg = c.next_msg()
            if msg:
                msg.lstrip() #get rid of leading spaces
                words_list = msg.split(' ')
                try:
                    first_byte = int(words_list[0],16)
                except:
                    first_byte=None
                if first_byte==cmri.CMRI_message.SYN:
                    #it is a CMRI message, process it
                    node = openlcb_nodes.find_node_from_cmri_add(cmri.CMRI_message.UA_to_add(int(words_list[3],16)),c.managed_nodes)
                    if node is None:
                        debug("Unknown node!! add=",cmri.CMRI_message.UA_to_add(int(words_list[3],16)) )
                    else:
                        node.get_low_level_node().process_receive(cmri.CMRI_message.from_wire_message(msg))
                        ev_list.extend(node.generate_events())
                else:
                    #it is a bus message (new node...)
                    if msg.startswith("start_node"):
                        fullID= int(msg.split(' ')[1])
                        debug("full ID=",fullID)
                        node = None
                        debug(self.nodes_db.db)
                        if fullID in self.nodes_db.db:
                            node = self.nodes_db.db[fullID]   #get node from db
                        else:
                            debug("Unknown node of full ID",fullID,", adding it to the DB")
                            #js = openlcb_nodes.Node_cpnode.DEFAULT_JSON
                            #js["fullID"]=fullID
                            #node = openlcb_nodes.Node_cpnode.from_json(js)
                            #self.nodes_db.db[fullID]=node
                        if node is not None:
                            node.get_low_level_node().client = c
                            #send INIT message to node
                            cmd = node.get_low_level_node().init_msg()
                            if cmd is not None:
                                c.queue(cmd.to_wire_message().encode('utf-8'))
                                debug("init msg", cmd.to_wire_message())
                            #create and register alias negotiation
                            alias_neg = node.create_alias_negotiation()
                            #loop while we find an unused alias
                            while (alias_neg.aliasID in reserved_aliases) or (get_alias_neg_from_alias(alias_neg.aliasID) is not None):
                                alias_neg = node.create_alias_negotiation()
                            self.nodes_in_alias_negotiation.append((node,alias_neg))
                            #also add it to the list of aliases negotiation
                            list_alias_neg.append(alias_neg)
                            c.managed_nodes.append(node)
                            #now load the recorded outputs states for this node
                            filename = self.path_to_nodes_files
                            if self.path_to_nodes_files:
                                filename+="/"
                                filename+=str(node.ID)+".outputs"
                                node.get_low_level_node().load_outputs(filename)
                                node.get_low_level_node().write_outputs(filename,False)
                    else:
                        debug("unknown cmri_net_bus command")
                        
            #now poll all nodes if needed
            if time.time() > self.last_poll+Cmri_net_bus.POLL_TIMEOUT:
                for node in c.managed_nodes:
                    node.poll()
        #move forward for alias negotiation
        frames_list=self.generate_frames_from_alias_neg()
        self.prune_alias_negotiation()
        self.nodes_db.sync()
        return ev_list,frames_list

class Can_bus(Bus):
    pass

class RR_duino_net_bus(Bus):
    """
    message format (messages are separated by a newline "\r\n):
    - 
    - New node: "start_node" followed by: full_ID(8 bytes) and node config (version, sensors, turnouts)
    """
    separator = "\r\n"
    nodes_db_file = "RR_duino_net_bus_db.cfg"

    def __init__(self):
        super().__init__(Bus_manager.RR_duino_net_bus_name)
        self.nodes = {} #dict of fullID <-> nodes correspondance
        self.nodes_db = nodes_db.Nodes_db_RR_duino_node(RR_duino_net_bus.nodes_db_file)
        self.nodes_db.load_all_nodes()
        
    def get_subadd_lst_from_bits(self,bits_str):
        """
        This translates a string of bytes into a list of subadd (MSB unused)
        bits_str is a string of space separated numbers (in decimal format)
        """

        numbers = bits_str.split()
        #first subadd is 1
        subadds_lst = []
        subadd = 1
        for n in numbers:
            nb = int(n)
            #check first 7 bits (MSB is always 0)
            for bit_n in range(0,7):
                if nb & (1<<bit_n):
                    subadds_lst.append(subadd)
                subadd+=1
        return subadds_lst

    def get_states_lst_from_bits(self,net_str):
        """
        This translates a string of bytes into a list of states (MSB unused)
        bits_str is a string of space separated numbers (in decimal format)
        """
        numbers = bits_str.split()
        #first subadd is 1
        states_lst = []

        for n in numbers:
            nb = int(n)
            #check first 7 bits (MSB is always 0)
            for bit_n in range(0,7):
                if nb & (1<<bit_n):
                    states_lst.append(1)
                else:
                    states_lst.append(0)
        return states_lst        
            
    def get_desc_from_RR_duino_init(self,net_desc):
        """
        This translates the string received from the RR_duino_net (after the address) into a list of config parameters:
        [0] (number) => version
        [1] (list) => inputs sensors subaddresses
        [2] (list) => outputs sensors subaddresses
        [3] (list) => turnouts subaddresses
        [4] (dict) => states of each sensor (input/output mixed) (key is subaddress)
        [5] (dict) => states of each turnout (key is subaddress)

        Format of net_desc: see arduino helper sketch
        """
        params = net_desc.split(",")
        #get version
        result = int(params[0])
        #get subaddresses of input sensors, output sensors and turnouts
        for i in range(1,4):
            result.append(self.get_subadd_lst_from_bits(params[i]))
        #get states of sensors
        result.append(self.get_states_lst_from_bits(params[4]))
        #get states of turnouts
        result.append(self.get_states_lst_from_bits(params[5]))
        
        return result

    def check_msg_format(self,msg):
        #check msg format and returns error message on error or tuple (address,subaddress,value) otherwise
        if not msg.startswith("ISRS") and not msg.startswith("ITRT"):
            return ("Unvalid prefix",)
        begin,sep,end = msg[len("ISRS"):].partition(":")
        if sep=="":
            return ("Bad format",)
        address = 0
        try:
            address = int(begin)
        except:
            pass
        if address<=0 or address>62:
            #bad integer format
            return ("Incorrect integer value/format for address",)
        begin,sep,end = end.partition(",")
        if sep=="":
            return ("Bad format",)
        subadd = 0
        try:
            subadd = int(begin)
        except:
            pass
        if subadd<=0 or subadd>62:
            #bad integer format
            return ("Incorrect integer value/format for subaddress",)
        value = -1
        try:
            value = int(end)
        except:
            pass
        if value!=0 and value!=1:
            #bad integer format
            return ("Incorrect integer value/format for value",)

        return (address,subadd,value)
        
    def process(self):
        #check all messages and return a list of events that has been generated in response
        #also checks all alias negotiation and return the corresponding can frames (CID,AMD,...)
        ev_list=[]
        for c in self.clients:
            msg = c.next_msg()
            if msg:
                debug("rr_duino new msg=",msg)
                msg.lstrip() #get rid of leading spaces
                debug("RR_duino_net_bus processing",msg)
                if msg.startswith("ISRS"):
                    #the RR_duino controller sends a sensor value, process it
                    debug("RR duino message processed!")
                    msg_value = self.check_msg_format(msg)
                    if len(msg_value)==1:
                        #There was an error, the tuple is only made of the error message
                        debug(msg_value[0])
                        return
                    node = RR_duino.find_node_from_add(msg_value[0],c.managed_nodes)
                    if node is None:
                        debug("Unknown node!! add=", address)
                    else:
                        #fixme!
                        ev_list.extend(node.process_receive(msg_value[1],msg_values[2]))
                else:
                    #it is a bus message (new node...)
                    #format: See arduino sketch
                    begin,sep,end = msg.partition(" ")
                    debug("begin=",begin,"sep=",sep,"end=",end)
                    if begin=="NEW-NODE" and end!="":
                        #get address (first field)
                        begin,sep,end = end.partition(",")
                        #fixme: exception might happen here
                        address = int(begin)
                        desc = self.nodes_db.get_db_node_from_add(c.name,address)
                        if desc is None:
                            debug("Node with address",address,"has no corresponding fullID!")
                        else:
                            if desc.desc_dict["fullID"] in c.managed_nodes:
                                debug("Node already managed!",desc["fullID"])
                            else:
                                #build node FIXME
                                nodecfg = self.get_cfg_from_RR_duino_init(end)
                                node = RR_duino.RR_duino_node(c,
                                                              desc.desc_dict["fullID"],
                                                              address,
                                                              nodecfg[0],
                                                              desc)
                                sensors_val = nodecfg[4]
                                #get input sensors subaddresses and values
                                for subadd in nodecfg[1]:
                                    node.sensors_cfg[subadd]=[RR_duino.RR_duino_message.INPUT_SENSOR,
                                                              sensors_val[subadd]]
                                #get output sensors subaddresses and values
                                for subadd in nodecfg[2]:
                                    node.sensors_cfg[subadd]=[RR_duino.RR_duino_message.OUTPUT_SENSOR,
                                                              sensors_val[subadd]]
                                #get turnouts subaddresses and values
                                node.turnouts_cfg=nodecfg[5]

                                #build node memory and populate it from the DB
                                node.create_memory()
                                node.load_from_desc()
                                debug("description dict=",node.desc.desc_dict)
                                self.nodes[desc.desc_dict["fullID"]]=node
                                #create and register alias negotiation
                                alias_neg = node.create_alias_negotiation()
                                #loop while we find an unused alias
                                while (alias_neg.aliasID in reserved_aliases) or (get_alias_neg_from_alias(alias_neg.aliasID) is not None):
                                    alias_neg = node.create_alias_negotiation()
                                self.nodes_in_alias_negotiation.append((node,alias_neg))
                                #also add it to the list of aliases negotiation
                                list_alias_neg.append(alias_neg)
                                c.managed_nodes.append(node)
                    elif begin=="STOP-NODE":
                        #FIXME: not sure we need this
                        #get the node out the managed list (device is offline or config has changed, in the latter case
                        #there should be a start_node with the new config)
                        #format stop_node fullID
                        #FIXME: must stop the OpenLCB part of the node here
                        found = False
                        for n in c.managed_nodes:
                            if n.ID==int(end):
                                found = True
                                break
                        if not found:
                            debug("Error:Node marked as dead not in managed nodes!!")
                        else:
                            debug("Remove node ",end," from the managed nodes")
                            c.managed_nodes.remove(n)
                    else:
                        debug("unknown RR_duino_net_bus command")

        #move forward for alias negotiation
        frames_list=self.generate_frames_from_alias_neg()
        self.prune_alias_negotiation()
        self.nodes_db.sync()
        return ev_list,frames_list    

class Bus_manager:
    #buses constants
    #cmri_net_bus
    cmri_net_bus_name = "CMRI_NET_BUS"
    #cmri_net_bus_separator = ";"
    #this is the name of the file where all nodes are described (full ID, description,name,version,events)
    #see openlcb_nodes_db.py for more info
    cmri_net_bus_db_file="cmri_net_bus_nodes_db.cfg"

    #can_bus FIXME
    can_bus_name = "CAN_BUS"
    #can_bus_separator = ";"

    #RR_duino_bus
    RR_duino_net_bus_name = "RR_DUINO"
    #RR_duino_bus_separator = "\r\n"

    #list of active buses
    buses=[]
    @staticmethod
    def create_bus(client,msg,path_to_outputs_files=None):
        """
        create a bus based on the name provided in the msgs field of the client
        returns the bus if it has been found (or created if needed)
        None otherwise
        """
        if msg.startswith(Bus_manager.cmri_net_bus_name):
            #create a cmri_net bus
            bus = Bus_manager.find_bus_by_name(Bus_manager.cmri_net_bus_name)
            if bus == None:
                bus = Cmri_net_bus(path_to_outputs_files)
                Bus_manager.buses.append(bus)
                debug("creating a cmri net bus")
            else:
                debug("Found cmri net bus:",bus.name)
            bus.clients.append(client)
            return bus
        elif  msg.startswith(Bus_manager.RR_duino_net_bus_name):
            #create a RR_duino_net bus
            bus = Bus_manager.find_bus_by_name(Bus_manager.RR_duino_net_bus_name)
            if bus is None:
                bus = RR_duino_net_bus()
                Bus_manager.buses.append(bus)
                debug("creating a RR_duino_net bus")
            bus.clients.append(client)
            return bus
        elif  msg.startswith(Bus_manager.can_bus_name):
            #create a can bus
            bus = Bus_manager.find_bus_by_name(Bus_manager.can_bus_name)
            if bus == None:
                bus = Can_bus()
                Bus_manager.buses.append(bus)
                debug("creating a can bus")
            bus.clients.append(client)
            return bus
        return None

    @staticmethod
    def find_bus_by_name(name):
        for b in Bus_manager.buses:
            if b.name == name:
                return b
        return None
            
def find_managed_node(aliasID):
    for b in Bus_manager.buses:
        for c in b.clients:
            for n in c.managed_nodes:
                if n.aliasID == aliasID:
                    return (n,c)
    return (None,None)
   
