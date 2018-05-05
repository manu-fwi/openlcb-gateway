import openlcb_nodes

class Nodes_db:
    def __init__(self,file_name):
        self.file_name = file_name
        self.nodes_db={}   #dict holding all nodes description, key is full ID

    def load_all_nodes(self):
        
        with open(self.file_name,'r') as file:
            while file:
                self.load_node(file)

    def load_node(self,file):
        pass

    def store_all_nodes(self):
        with open(self.file_name,'w') as file:
            for n in self.nodes_db:
                self.store_node(n)
