import openlcb_cmri_cfg as cmri

"""This file defines a basic openlcb node (the gateway will handle several of these
You derive your "real node class" from it and add the handling specific to your hardware
Also contains the memory space management (as in CDI config)
"""
        
"""mem_space is a segment of memory you read from /write to using addresses
It is made of triples: beginning address(offset), size and a write_callback function
This function is called when the memory cell is written to with the following parameters:
write_callback(offset,buf)
where offset is the beginnon of the cell and buf is the buf which has just been written
"""
class mem_space:
    def __init__(self,list=None):
        self.mem = {}
        self.mem_chunks={}
        if list is not None:
            for (offset,size) in list:
                self.create_mem(offset,size)
                print("created: ",offset,"-->",offset+size-1," size=",size)

    def create_mem(self,offset,size):
        self.mem[(offset,size)]=None
        
    def set_mem_partial(self,add,buf):
        """returns the memory space (offset,size) if memory has been updated
        or None if the write is incomplete: some writes are still expected for this memory space
        """
        
        for (offset,size) in self.mem.keys():
            if add>=offset and add <offset+size:
                print("set_mem_partial:",add," in ",offset,size,"=",buf)
                if offset in self.mem_chunks:
                    self.mem_chunks[offset]+=buf
                    print("chunk is now=",self.mem_chunks[offset])
                else:
                    self.mem_chunks[offset]=buf
                print("set_mem_partial:",offset,size,"=",buf)
                if len(self.mem_chunks[offset])==size:
                    self.mem[(offset,size)]=self.mem_chunks[offset]
                    del self.mem_chunks[offset]
                    print("set_mem_partial done",self.mem_chunks)
                    return (offset,size)
                elif len(self.mem_chunks[offset])>size:
                    print("memory write error in set_mem_partial, chunk size is bigger than memory size at",offset)

        return None

    def set_mem(self,offset,buf):
        if (offset,len(buf)) in self.mem:
            print("set_mem(",offset,")=",buf)
            self.mem[(offset,len(buf))]=buf
            return True
        
        print("set_mem failed, off=",offset,"buf=",buf," fo length=",len(buf))
        return False


    def read_mem(self,add):
        for (offset,size) in self.mem.keys():
            if add>=offset and add <offset+size:
                return self.mem[(offset,size)][add-offset:]
        return None

    def mem_valid(self,offset):
        return offset not in self.mem_chunks
    
    def __str__(self):
        return str(self.mem)
    
    def dump(self):
        for (off,size) in self.mem:
            print("off=",off,"size=",size,"content=",self.mem[(off,size)])

    def get_size(self,offset):
        for (off,size) in self.mem.keys():
            if off==offset:
                return size
        return None #offset not found

"""
Base class for all node types
You must implement get_cdi() so that the gateway can retrieve the CDI describing your node
You also most probablu want to extend set_mem and maybe read_mem to sync the node's memory with the
real node's mem
"""
class node:
    def __init__(self,ID,permitted=False,aliasID=None):
        self.ID = ID
        self.aliasID = aliasID
        self.permitted=permitted
        self.produced_ev=[]
        self.consumed_ev=[]
        self.simple_info = []
        self.memory = None    #this is the object representing the OpenLCB node memory
                              #you need to create the memory spaces (see the mem_space class)
        self.current_write = None  #this is a pair (memory space, address) that holds
                                   #the current writing process

    def set_mem(self,mem_sp,offset,buf): #extend this to sync the "real" node (cpNode or whatever)
                                         #with the openlcb memory
        return self.memory[mem_sp].set_mem(offset,buf)
    
    def set_mem_partial(self,add,buf):
        return self.memory[mem_sp].set_mem_partial(add,buf)
        
    def read_mem(self,mem_sp,add):
        return self.memory[mem_sp].read_mem(add)

    def get_mem_size(self,mem_sp,offset):
        return self.memory[mem_sp].get_size()
        
    def add_consumed_ev(self,ev):
        self.consumed_ev.append(ev)

    def add_produced_ev(self,ev):
        self.produced_ev.append(ev)

    def set_simple_info(self,list):
        self.simple_info = list  #byte arrays

    def build_simple_info_dgram(self): # return datagrams holding the simple info
        print("build_simple_info not implemented!") #fixme
    
class node_CPNode(node):
    CDI="""<?xml version="1.0"?>
<cdi xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:noNamespaceSchemaLocation="http://openlcb.org/schema/cdi/1/1/cdi.xsd">

<identification>
<manufacturer>cpNode-OLCB-GW</manufacturer>
<model>Test</model>
<hardwareVersion>0.1</hardwareVersion>
</identification>
<acdi/>

<segment space='251'>
<name>User Identification</name>
<description>Lets the user add his own description</description>
<int size='1'>
<name>Version</name>
</int>
<string size='63'>
<name>Node Name</name>
</string>
<string size='64'>
<name>Node Description</name>
</string>
</segment>

<segment space="253">
<int size="1">
<name>Address</name>
<description>The cpNode address.</description>
<min>0</min><max>127</max>
</int>
<group replication="16">
<name>Channels</name>
<description>Each channel is an I/O line.</description>
<repname>Channel</repname>
<group>
<name>I/O selection</name>
<int size="1">
<default>0</default>
<map>
<relation><property>0</property><value>Output</value></relation>
<relation><property>1</property><value>Input</value></relation>
</map>
</int>
</group>
<group>
<name>Input/Output</name>
<eventid>
<name>Input/Output LOW</name>
<description>When this event arrives, the output will be switched to LOW or if it is an Input this event is generated when it is LOW</description>
</eventid>
<eventid>
<name>Input/Output HIGH</name>
<description>When this event arrives, the output will be switched to HIGH or if it is an Input this event is generated when it is HIGH.</description>
</eventid>
</group>
</group>
</segment>
</cdi>
\0"""
    
    def __init__(self,CMRI_add,ID,bus=None):
        super().__init__(ID)
        print(node_CPNode.CDI)
        self.cp_node=cmri.CPNode(CMRI_add,bus,0)  #"real" node

    def get_CDI(self):
        return node_CPNode.CDI

    def set_bus(self,bus):
        if self.cp_node.bus is not None:
            self.cp_node.bus.stop()
        self.cp_node.bus = bus
        
    def poll(self):
        self.cp_node.read_inputs()
        
    def generate_events(self):
        cpn = self.cp_node
        for i in range(cpn.nb_I):
            if cpn.inputs[i][0]!=cpn.inputs[i][1]: #input change send corresponding event
                

def find_node_from_cmri_add(add):
    for n in managed_nodes:
        if n.cp_node.address == add:
            return n
    return None

def find_node(aliasID):
    for n in all_nodes:
        if n.aliasID == aliasID:
            return n
    return None

def find_managed_node(aliasID):
    for n in managed_nodes:
        if n.aliasID == aliasID:
            return n
    return None
   

"""
append the new node if it was not known before (return True)
or does nothing if it was (return False)
"""
def new_node(new_n):
    for n in all_nodes:
        if n.ID == new_n.ID:
            return False
    all_nodes.append(new_n)
    return True
#globals
managed_nodes = []   #holds all nodes that the gateway manages
all_nodes = []       #list of all known nodes
