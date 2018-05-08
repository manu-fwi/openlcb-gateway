import openlcb_nodes,json

"""
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
class Nodes_db:
    def __init__(self,file_name):
        self.file_name = file_name
        self.nodes_db={}   #dict holding all nodes description, key is full ID

    def load_all_nodes(self):
        
        with open(self.file_name,'r') as file:
            while file:
                n = self.load_node(file)
                if fullID in self.nodes_db:
                    debug("2 nodes with same full ID in the DB!")
                else:
                    self.nodes_db[n.fullID]=n

    #two "virtual" methods to be defined by the subclasses
    def load_node(self,file):
        pass
    def store_node(self,file,node):
        pass

    def store_all_nodes(self):
        with open(self.file_name,'w') as file:
            for n in self.nodes_db:
                self.store_node(file,n)

class Nodes_db_cpnode(Nodes_db):
    
    def load_node(self,file):
        try:
            js = json.load(file)
        except JSONDecodeError:
            debug("Json error when trying to load node",js)

        if "fullID" not in js or "cmri_node_add" not in js or "IO_config" not in js or "version" not in js:
            debug("missing fields in the node description",js)
            return None
        
        return Node_cpnode.from_json(js)

    def store_node(self,file,node):
        try:
            json.dump(node.to_json(),file)
        except JSONDecodeError:
            debug("Json error when storing node",node.fullID)
    
