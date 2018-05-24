import openlcb_cmri_cfg as cmri
from openlcb_protocol import *
import openlcb_buses as buses
from openlcb_debug import *

"""This file defines a basic openlcb node (the gateway will handle several of these
You derive your "real node class" from it and add the handling specific to your hardware
Also contains the memory space management (as in CDI config)
"""
        
"""mem_space is a segment of memory you read from /write to using addresses
It is made of triples: beginning address(offset), size and a write_callback function
This function is called when the memory cell is written to with the following parameters:
write_callback(offset,buf)
where offset is the begining of the cell and buf is the buf which has just been written
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
        self.PRNG = None

    def set_mem(self,mem_sp,offset,buf): #extend this to sync the "real" node (cpNode or whatever)
                                         #with the openlcb memory
        print("node set_mem");
        return self.memory[mem_sp].set_mem(offset,buf)

    def create_alias_negotiation(self):
        """
        Set up a new alias negotiation (creates an alias also)
        """
        if self.PRNG is None:
            PRNG = self.ID
        else:
            PRNG += PRNG << 9 + 0x1B0CA37A4BA9
        alias = ((PRNG >> 36)^(PRNG>> 24)^(PRNG >> 12)^PRNG) & 0xFFF
        return Alias_negotiation(alias,self.ID)
        
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
<default>1</default>
<map>
<relation><property>0</property><value>No card</value></relation>
<relation><property>1</property><value>8 Outputs</value></relation>
<relation><property>2</property><value>8 Inputs</value></relation>
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
<repname>Card </repname>
"""
    CDI_IOX_repetition_end="""</group>
"""

    #default dict to add new nodes to the DB when they have no description (used by cmri_net_bus)
    DEFAULT_JSON = { "fullID":None,"cmri_node_add":0 }
    @staticmethod
    def from_json(js):
        def normalize(s,length):
            res = bytearray(s.encode('utf-8'))
            if len(res)>length:
                res=res[:length]
            elif len(res)<length:
                res.extend(b"\0"*(length-len(res)))
            return res
            
        n = Node_cpnode(js["fullID"])
        if "IO_config" in js:
            nb_I = cmri.CPNode.decode_nb_inputs(js["IO_config"])
        else:
            nb_I = 16
        n.cp_node = cmri.CPNode(js["cmri_node_add"], nb_I)
        n.create_memory()
        n.set_mem(253,0,bytes((js["cmri_node_add"],)))
        n.set_mem(253,1,bytes((js["IO_config"],)))
        if "IOX_config" in js:
            IOX= js["IOX_config"]
        else:
            IOX=[0]*16
        index=0
        debug(IOX)
        for i in IOX:
            debug("IOX",i,2+cmri.CPNode.total_IO*2*8+index*(1+2*8*8))
            n.set_mem(253,2+cmri.CPNode.total_IO*2*8+index*(1+2*8*8),bytes((i,)))
            index+=1
        if "version" in js:
            version = js["version"]
        else:
            version = 0
        n.set_mem(251,0,bytes((version,)))
        if "name" in js:
            name = js["name"]
        else:
            name = ""
        n.set_mem(251,1,normalize(name,63))
        if "description" in js:
            description= js["description"]
        else:
            description = ""
        n.set_mem(251,64,normalize(description,64))
        if "basic_events" in js:
            index=0
            for ev in js["basic_events"]:
                debug("basic",index,ev)
                n.set_mem(253,2+index*8,Event.from_str(ev).id)
                index+=1
        if "IOX_events" in js:
            debug("IOX",index,ev)
            offset = 2+cmri.CPNode.total_IO*2*8+1   #beginning of the first IOX event
            index = 0
            for ev in js["IOX_events"]:
                #compute the offset where the event must go in memory (remember its 1 byte (I or O)
                #and then 16 times two events
                n.set_mem(253,offset,Event.from_str(ev).id)
                index+=1
                offset+=8    #next event
                if index%16==0:  #16 events per card, add 1 to skip the I/O byte of the next card
                    offset+=1
        n.memory[253].dump()
        return n

    def to_json(self):
        name = self.read_mem(251,1)
        descr = self.read_mem(251,64)
        #dict describing the node, first part
        node_desc = {"fullID":self.ID,"cmri_node_add":self.cp_node.address,
                     "version":self.read_mem(251,0)[0],"name":name[:name.find(0)].decode('utf-8'),
                     "description":descr[:descr.find(0)].decode('utf-8'),
                     "IO_config":self.read_mem(253,1)[0],
                     "IOX_config":self.cp_node.IOX}
        str_events=[]
        debug("ev_list",len(self.ev_list))
        for ev in self.ev_list:
            debug(ev)
            str_events.extend((str(Event(ev[0])),str(Event(ev[1]))))
        node_desc["basic_events"]=str_events
        str_events_IOX=[]
        debug("ev_list_IOX",len(self.ev_list_IOX))
        for ev in self.ev_list_IOX:
            debug(ev)
            str_events_IOX.extend((str(Event(ev[0])),str(Event(ev[1]))))
        node_desc["IOX_events"]=str_events_IOX
        debug("node desc=",node_desc)
        return node_desc
        
                
    def create_memory(self):           
        channels_mem=Mem_space([(0,1),(1,1)])  #node address and io config
        offset = 2
        #loop over 16 channels (basic IO)
        for i in range(self.cp_node.total_IO*2): #2 events per IO line
            channels_mem.create_mem(offset,8)
            channels_mem.set_mem(offset,b"\0"*8)    #default event
            offset+=8
        #now IOX associated memory
        for i in range(cmri.CPNode.IOX_max):
            channels_mem.create_mem(offset,1)   #Input or output for the IOX card
            offset+=1
            for j in range(16):   #2 events per IO line
                channels_mem.create_mem(offset,8)
                channels_mem.set_mem(offset,b"\0"*8)    #default event
                offset+=8
        self.memory = {251:Mem_space([(0,1),(1,63),(64,64)]),
                       253:channels_mem}
        self.memory[251].dump()
        self.memory[253].dump()
        
            
    def __init__(self,ID):
        super().__init__(ID)
        self.aliasID = ID & 0xFFF   #FIXME!!!
        self.cp_node=None        #real node
        self.ev_list=[(b"\0"*8,b"\0"*8)]*16   #basic event list
        self.ev_list_IOX = [(b"\0"*8,b"\0"*8)]*128    #IOX events list for 8 IO lines for 16 cards max

    def get_IOX_CDI(self):
        
        res = Node_cpnode.CDI_IOX_repetition_beg.replace("%nbiox","16")
        res+=Node_cpnode.CDI_IOX
        res+=Node_cpnode.CDI_IOX_repetition_end
        return res
        
    def get_CDI(self):
        return Node_cpnode.CDI_header+self.get_IOX_CDI()+Node_cpnode.CDI_footer

    def set_mem(self,mem_sp,offset,buf):
        super().set_mem(mem_sp,offset,buf)
        if mem_sp == 253:
            if offset == 0:
                #address change
                debug("changing address",self.cp_node.address,buf[0])
                self.cp_node.address = buf[0]
            elif offset == 1:
                pass
                #FIXME: I dont handle the I/O type change for now
            elif offset >=2 and offset-2<self.cp_node.total_IO*2*8: #check if we change a basic IO event
                #rebuild the events if they have changed
                entry = (offset-2)//16
                
                if (offset-2)%16==0:
                    offset_0 = offset
                else:
                    offset_0 = offset - 8
                debug("entry=",entry,"off=",offset,"off0=",offset_0)
                self.ev_list[entry]=(self.read_mem(mem_sp,offset_0),self.read_mem(mem_sp,offset_0+8))
            else: #memory changed is about IOX part
                offset_0 =offset-2-self.cp_node.total_IO*2*8
                card = offset_0//(1+8*2*8) #compute the card number, each description is 129 bytes long
                                       #IO type + 8 bytes for 8 pairs of events (1 pair per I/O line)
                offset_in_card = offset_0 % (1+8*2*8)
                debug(offset,offset_0,card,offset_in_card,(offset_in_card-1)//16)
                if offset_in_card == 0:  #IO Type
                    self.cp_node.IOX[card]=self.read_mem(mem_sp,offset)[0]
                    self.cp_node.build_IOX()
                else:   #event
                    ev_pair_index=(offset_in_card-1)//16
                    if (offset_in_card-1)%16 == 0: #first event
                        offset_0 = offset
                    else:
                        offset_0 = offset - 8
                    self.ev_list_IOX[card*8+ev_pair_index]=(self.read_mem(mem_sp,offset_0),self.read_mem(mem_sp,offset_0+8))

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
        #the node might consume the same event for several outputs (one event controlling several outputs)
        index = 0
        for ev_pair in self.ev_list:
            val = -1
            if ev.id == ev_pair[0]:
                val = 0
            elif ev.id == ev_pair[1]:
                val = 1
            index+=1
            debug("consume event:",index,">?",self.cp_node.nb_I," val=",val)
            if val>=0 and index>=self.cp_node.nb_I:  #we only consume event for outputs
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
                    return (n,c)
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
