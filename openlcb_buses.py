import socket,select
import openlcb_cmri_cfg as cmri
import serial
import openlcb_server
import openlcb_nodes
import openlcb_nodes_db as nodes_db
from openlcb_debug import *

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
    - New node: "start_node" followed by: full_ID(8 bytes)
    """
    separator = ";"
    nodes_db_file = "cmri_net_bus_db.cfg"
    def __init__(self):
        super().__init__(Bus_manager.cmri_net_bus_name)
        self.nodes_db = nodes_db.Nodes_db_cpnode(Cmri_net_bus.nodes_db_file)
        self.nodes_db.load_all_nodes()
        
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
                        if msg.startswith("start_node"):
                            fullID= int(msg.split(' ')[1],16)
                            if fullID in self.nodes_db.db:
                                node = self.nodes_db.db[fullID]   #get node from db
                                c.managed_nodes.append(node)
                            else:
                                debug("Error: unknown node of full ID",fullID,self.nodes_db.db.keys())
                        else:
                            print("unknown cmri_net_bus command")
                        
            #now poll all nodes
            for node in c.managed_nodes:
                node.poll()
        self.nodes_db.sync()
        return ev_list

class Can_bus(Bus):
    pass

class Bus_manager:
    #buses constants
    #cmri_net_bus
    cmri_net_bus_name = "CMRI_NET_BUS"
    cmri_net_bus_separator = ";"
    #this is the name of the file where all nodes are described (full ID, description,name,version,events)
    #see openlcb_nodes_db.py for more info
    cmri_net_bus_db_file="cmri_net_bus_nodes_db.cfg"

    #can_bus FIXME
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
            
