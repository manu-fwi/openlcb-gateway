import openlcb_nodes,json
from openlcb_debug import *
import time

"""
Format: a (json) list each element of which is a node description
Format for a node description: json format with the following fields
"fullID" (integer)
"cmri_node_add" (integr)
"version" (integer)
"name" (string)
"description" (string)
"IO_config" (integer)
"IOX_config" (list of pairs of integers (-1,0 or 1), only the needed number <=8)
"basic_events" 16 pairs of events (8 bytes, hex noted, separated by '.')
"IOX_events" pairs of events (only the needed number <=128)
"""


class Nodes_db_cpnode:
    def __init__(self,file_name):
        self.file_name = file_name
        self.db={}   #dict holding all nodes description, key is full ID
        self.synced = False
        self.last_sync = 0
        self.sync_period = 60 #1 min minimum between syncs to file

    def store_all_nodes(self):
        with open(self.file_name,'w') as file:
            db_list=[]
            for n in self.nodes_db:
                db_list.append(n.to_json())
                #fixme: error handling
            json.dump(db_list,file)
        self.synced = True
        self.last_sync = time.time()
                
    def load_all_nodes(self):
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
        
    def load_node(self,js):
        
        if "fullID" not in js or "cmri_node_add" not in js or "IO_config" not in js:
            debug("missing fields in the node description",js)
            return None
        
        return openlcb_nodes.Node_cpnode.from_json(js)

    def sync(self):
        if not self.synced and self.last_sync+self.sync_period<time.time():
            self.store_all_nodes()
