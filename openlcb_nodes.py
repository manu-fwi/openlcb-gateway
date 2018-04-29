import openlcb_cmri_cfg as cmri
from openlcb_protocol import *
import openlcb_buses as buses

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
class Mem_space:
    def __init__(self,list=None):
        self.mem = {}
        self.mem_chunks={}
        if list is not None:
            for (offset,size) in list:
                self.create_mem(offset,size)

    def create_mem(self,offset,size):
        self.mem[(offset,size)]=None
        
    def set_mem_partial(self,add,buf):
        """returns the memory space (offset,size,buf) if memory must be updated
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
                    buf=self.mem_chunks[offset]
                    del self.mem_chunks[offset]
                    print("set_mem_partial done",self.mem_chunks)
                    return (offset,size,buf)
                elif len(self.mem_chunks[offset])>size:
                    print("memory write error in set_mem_partial, chunk size is bigger than memory size at",offset)
                    del self.mem_chunks[offset]

        return None

    def set_mem(self,offset,buf):
        if (offset,len(buf)) in self.mem:
            print("set_mem(",offset,")=",buf)
            self.mem[(offset,len(buf))]=buf
            return True
        
        print("set_mem failed, off=",offset,"buf=",buf," of length=",len(buf))
        return False


    def read_mem(self,add):
        for (offset,size) in self.mem.keys():
            if add>=offset and add <offset+size:
                if self.mem[(offset,size)] is not None:
                    return self.mem[(offset,size)][add-offset:]
                else:
                    return None
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
You also most probably want to extend set_mem and maybe read_mem to sync the node's memory with the
real node's mem
"""
class Node:
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
        print("node set_mem");
        return self.memory[mem_sp].set_mem(offset,buf)
    
    def set_mem_partial(self,mem_sp,add,buf):
        res = self.memory[mem_sp].set_mem_partial(add,buf)
        if res is not None:
            print("node set_mem_partial calls set_mem",mem_sp,res)
            self.set_mem(mem_sp,res[0],res[2])
        
    def read_mem(self,mem_sp,add):
        print("read_mem",mem_sp,add)
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
    
class Node_cpnode(Node):
    CDI_header="""<?xml version="1.0"?>
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
<group>
<name>Base I/O configuration</name>
<int size="1">
<default>2</default>
<map>
<relation><property>1</property><value>6 Inputs / 10 Outputs</value></relation>
<relation><property>2</property><value>8 Inputs / 8 Outputs</value></relation>
<relation><property>3</property><value>8 Outputs / 8 Inputs</value></relation>
<relation><property>4</property><value>12 Outputs / 4 Inputs</value></relation>
<relation><property>5</property><value>16 Inputs</value></relation>
<relation><property>6</property><value>16 Outputs</value></relation>
<relation><property>7</property><value>RSMC 5 Inputs / 11 Outputs</value></relation>
<relation><property>7</property><value>RSMC LOCK 4 Inputs / 12 Outputs</value></relation>
</map>
</int>
</group>
<group replication="16">
<name>Channels</name>
<description>Each channel is an I/O line.</description>
<repname>Channel</repname>

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
"""
    CDI_footer = """</segment>
</cdi>
\0"""
    CDI_IOX = """<group>
<name>IOX expansions</name>
<int size="1">
<default>2</default>
<map>
<relation><property>0</property><value>8 Outputs</value></relation>
<relation><property>1</property><value>8 Inputs</value></relation>
</map>
</int>
<group replication="8">
<name> IOX channels</name>
<description> Each channel is an I/O line on a IOX expander</description>
<repname>Channel</repname>
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
</group>
"""
    CDI_IOX_repetition_beg="""<group replication="%nbiox">
<name> IOX expansions</name>
<description> Each group describes and IOX card I/O group</description>
<repname>Cards</repname>
"""
    CDI_IOX_repetition_end="""</group>
"""
    def create_memory(self):
        channels_mem=Mem_space([(0,1)])  #first: node address
        offset = 1
        for i in range(16):   #loop over 16 channels
            for j in range(2):
                channels_mem.create_mem(offset,8)
                offset+=8
        self.memory = {251:Mem_space([(0,1),(1,63),(64,64)]),
                  253:channels_mem}
        offset = 1
        self.set_mem(253,offset,b"\2")
        for i in range(16):
            buf = bytearray()
            buf.extend([i]*8)
            self.set_mem(253,offset,buf)
            buf = bytearray()
            buf.extend([i]*7)
            buf.append(i+1)
            self.set_mem(253,offset+8,buf)
            offset+=16
            
    def __init__(self,ID):
        super().__init__(ID)
        self.aliasID = ID & 0xFFF   #FIXME!!!
        self.cp_node=None        #real node
        self.ev_list=[None]*16   #event list
        self.create_memory()

    def get_IOX_CDI(self):
        nb_iox_io = (self.cp_node.nb_IOX_inputs()+self.cp_node.nb_IOX_inputs())//8
        if nb_iox_io==0:
            return ""
        res=""
        if nb_iox_io>0:
            res += Node_cpnode.CDI_IOX_repetition_beg.replace("%nbiox",str(nb_iox_io))
        res+=Node_cpnode.CDI_IOX
        if nb_iox_io>0:
            res+=Node_cpnode.CDI_IOX_repetition_end
        return res
        
    def get_CDI(self):
        return Node_cpnode.CDI_header+self.get_IOX_CDI()+Node_cpnode.CDI_footer

    def set_mem(self,mem_sp,offset,buf):
        print("node_cpnode set_mem")
        super().set_mem(mem_sp,offset,buf)
       
        if mem_sp == 253:
            if offset == 0:
                #address change
                print("changing address",self.cp_node.address,buf[0])
                self.cp_node.address = buf[0]
            elif offset > 1:
                #FIXME: I dont handle the I/O type change for now
                #rebuild the events if they have changed
                entry = (offset-2)//16
                
                if (offset-2)%16==0:
                    offset_0 = offset
                else:
                    offset_0 = offset - 8
                self.ev_list[entry]=(Event(self.read_mem(mem_sp,offset_0)),Event(self.read_mem(mem_sp,offset_0+8)))

    def poll(self):
        self.cp_node.read_inputs()
        
    def generate_events(self):
        ev_lst = []
        cpn = self.cp_node
        for i in range(cpn.nb_I):
            if cpn.inputs[i][0]!=cpn.inputs[i][1]: #input change send corresponding event
                ev_lst.append((self,self.ev_list[i][cpn.inputs[i][0]]))
        return ev_lst

    def consume_event(self,ev):
        val = -1
        index = 0
        for ev_pair in self.ev_list:
            if ev.id == ev_pair[0].id:
                val = 0
                break
            elif ev.id == ev_pair[1].id:
                val = 1
                break
            index+=1
        if val>=0 and index>=self.cp_node.nb_I:  #we only consume event for outputs
            print("consume_ev",ev.id,index,val)
            self.cp_node.set_output(index-self.cp_node.nb_I,val)
            self.cp_node.write_outputs()
        
def find_node_from_cmri_add(add,nodes):
    for n in nodes:
        if n.cp_node.address == add:
            return n
    return None

def find_node(aliasID):
    for n in all_nodes:
        if n.aliasID == aliasID:
            return n
    return None

def find_managed_node(aliasID):
    for b in buses.Bus_manager.buses:
        for c in b.clients:
            for n in c.managed_nodes:
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
all_nodes = []       #list of all known nodes
