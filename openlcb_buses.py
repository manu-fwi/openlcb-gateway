import socket,select
import openlcb_cmri_cfg as cmri
import serial
import openlcb_server
import openlcb_nodes

class Bus:
    def __init__(self,name):
        self.name = name
        self.clients=[]       #client programs connected to the bus

    def __str__(self):
        return "Bus: "+self.name
     
class Cmri_net_bus(Bus):
    """
    message format (messages are separated by a ";", also number is presented as an hexdecimal string):
    - space separated (only ONE space) word and numbers/CMRI message (distinguished by the 2 SYN chars at the beginning)
    Message types (other than the CMRI message)
    - New node: "new_node" followed by: full_ID(8 bytes) version(one byte) name(string <63 chars) description(string <64 chars)
    and the format describing a cmri node (cf openlcb_cmri_cfg.py)
    - load nodes descriptions from a file: "nodes_from_file" followed by a file name
       File format: LF separated lines following the format above (without the new_node prefix and without the trailing ";")
    """
    separator = ";"
    def __init__(self):
        super().__init__(Bus_manager.cmri_net_bus_name)
        
    def process(self):
        #check all messages and return a list of events that has been generated in response
        ev_list=[]
        for c in self.clients:
            msg = c.next_msg()
            if msg:
                print("received=",msg)
                msg=msg[:len(msg)-1]  #remove the trailing ";"
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
                            print("Unknown node!! add=",cmri.CMRI_message.UA_to_add(int(words_list[3],16)) )
                        else:
                            node.cp_node.process_receive(cmri.CMRI_message.from_wire_message(msg))
                            ev_list.extend(node.generate_events())
                    else:
                        #it is a bus message (new node...)
                        if msg.startswith("new_node"):
                            l = msg.split(' ')
                            cpnode=cmri.decode_cmri_node_cfg(l[5:])
                            if cpnode is not None:
                                cpnode.client = c
                                node = openlcb_nodes.Node_cpnode(int(l[1],16))    #full ID (Hex)
                                node.cp_node = cpnode
                                node.create_memory()
                                #set info
                                node.set_mem(251,0,bytes((int(l[2],16),)))
                                node.set_mem(251,1,l[3].encode('utf-8')+(b"\0")*(63-len(l[3])))
                                node.set_mem(251,64,l[4].encode('utf-8')+(b"\0")*(64-len(l[4])))
                                #set address
                                node.set_mem(253,0,bytes((cpnode.address,)))
                                c.managed_nodes.append(node)
                        elif msg.startswith("nodes_from_file"):
                            cmri.load_cmri_cfg(c,msg.split(' ')[1])
                        else:
                            print("unknown cmri_net_bus command")
                        
            #now poll all nodes
            for node in c.managed_nodes:
                node.poll()
        return ev_list

class Can_bus(Bus):
    pass

class Bus_manager:
    #buses names as received online
    
    cmri_net_bus_name = "CMRI_NET_BUS"
    cmri_net_bus_separator = ";"
    can_bus_name = "CAN_BUS"
    can_bus_separator = ";"

    #list of active buses
    buses = []
    @staticmethod
    def create_bus(client,msg):
        """
        create a bus based on the name provided in the msgs field of the client
        returns True if bus has been found (or created if needed)
        False otherwise
        """
        if msg.startswith(Bus_manager.cmri_net_bus_name):
            #create a cmri_net bus
            bus = Bus_manager.find_bus_by_name(Bus_manager.cmri_net_bus_name)
            if bus == None:
                bus = Cmri_net_bus()
                Bus_manager.buses.append(bus)
                print("creating a cmri net bus")
            bus.clients.append(client)
            return True
        elif  msg.startswith(Bus_manager.can_bus_name):
            #create a cmri_net bus
            bus = Bus_manager.find_bus_by_name(Bus_manager.can_bus_name)
            if bus == None:
                bus = Can_bus()
                Bus_manager.buses.append(bus)
                print("creating a cmri net bus")
            bus.clients.append(client)
            return True
        return False

    @staticmethod
    def find_bus_by_name(name):
        for b in Bus_manager.buses:
            if b.name == name:
                return b
        return None
            
