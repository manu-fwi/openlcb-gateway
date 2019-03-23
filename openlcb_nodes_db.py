import json,openlcb_cpnodes,openlcb_RR_duino_nodes
from openlcb_debug import *
import time

class Nodes_db_node:
    """
    Class to handle the load/saving of all/part of nodes config
    This includes at least all the event ids configured in the CDI
    This may also include other parameters depending on the type of nodes
    Each subclass is reponsible for the file format (JSON)
    """
    def __init__(self,file_name):
        self.file_name = file_name
        self.db={}   #dict holding all nodes description, key is full ID
        self.synced = False
        self.last_sync = 0
        self.sync_period = 10 #10 s minimum between syncs to file

    def store_all_nodes(self):
        debug("storing nodes DB")
        with open(self.file_name,'w') as file:
            db_list=[]
            for n in self.db:
                db_list.append(self.db[n].to_json())
                #fixme: error handling
            json.dump(db_list,file)
        self.synced = True
        self.last_sync = time.time()

    def load_node(self):  # virtual function to be overloaded by subclasses
        return None
    
    def load_all_nodes(self):
        try:
            with open(self.file_name,'r') as file:
                #fixme: error handling
                db_list = json.load(file)
                for desc in db_list:
                    n = self.load_node(desc)
                    if n is not None:
                        if n.ID in self.db:
                            debug("2 nodes with same full ID in the DB!")
                        else:
                            self.db[n.ID]=n
            self.synced = True
            self.last_sync = time.time()
        except:
            debug("Error loading nodes DB, missing or malformed file")
        
    def sync(self):
        if not self.synced and self.last_sync+self.sync_period<time.time():
            self.store_all_nodes()


"""
Base class for all CMRI nodes types:CPNodes and SUSICs for now

Format for a CP node: a (json) list each element of which is a node description
"fullID" (integer)
"type" (character) "C"
"cmri_node_add" (integr)
"version" (integer)
"name" (string)
"description" (string)
"IO_config" (integer)
"IOX_config" (list of pairs of integers (-1,0 or 1), only the needed number <=8)
"basic_events" 16 pairs of events (8 bytes, hex noted, separated by '.')
"IOX_events" pairs of events (only the needed number <=128)

Format for a SUSIC node: a (json) list each element of which is a node description
Format for a node description: json format with the following fields
"fullID" (integer)
"type" (character) "X" or "N"
"cmri_node_add" (integer)
"version" (integer)
"name" (string)
"description" (string)
"type" (character)
"cards_sets" (list of integers)
"events" pairs of events (8 bytes, hex noted, separated by '.')
"""
class Nodes_db_CMRI(Nodes_db_node):  
    def __init__(self,filename):
        super().__init__(filename)
        
    def load_node(self,js):
        
        if "fullID" not in js or "cmri_node_add" not in js or "IO_config" not in js:
            debug("missing fields in the node description",js)
            return None
        if js["type"]=="C":
            return openlcb_cpnodes.Node_cpnode.from_json(js)
        elif js["type"]=="N" or js["type"]=="X":            
            return openlcb_susic.Node_SUSIC.from_json(js)

class Nodes_db_RR_duino_node(Nodes_db_node):  
    def __init__(self,filename):
        super().__init__(filename)
        
    def load_node(self,js):
        
        if "fullID" not in js:
            debug("missing fields in the node description",js)
            return None
        debug("load node from db",js)
        return openlcb_RR_duino_nodes.RR_duino_node_desc(js)
