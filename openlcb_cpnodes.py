import openlcb_cmri_cfg as cmri
from openlcb_protocol import *
from openlcb_debug import *
import openlcb_config
import openlcb_nodes as nodes

class Node_cpnode(nodes.Node):
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
    CHANNELS_SEGMENT = 253
    @staticmethod
    def from_json(js):            
        n = Node_cpnode(js["fullID"])
        if "IO_config" in js:
            nb_I = cmri.CPNode.decode_nb_inputs(js["IO_config"])
        else:
            nb_I = 16
            js["IO_config"]=5
        n.cp_node = cmri.CPNode(js["cmri_node_add"], nb_I)
        n.create_memory()
        n.memory[Node_cpnode.CHANNELS_SEGMENT].set_mem(0,bytes((js["cmri_node_add"],)))
        n.memory[Node_cpnode.CHANNELS_SEGMENT].set_mem(1,bytes((js["IO_config"],)))
        if "IOX_config" in js:
            IOX= js["IOX_config"]
        else:
            IOX=[0]*16
        index=0
        debug(IOX)
        for i in IOX:
            debug("IOX",i,2+cmri.CPNode.total_IO*2*8+index*(1+2*8*8))
            n.set_mem(Node_cpnode.CHANNELS_SEGMENT,
                      2+cmri.CPNode.total_IO*2*8+index*(1+2*8*8),bytes((i,)))
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
        n.set_mem(251,1,nodes.normalize(name,63))
        if "description" in js:
            description= js["description"]
        else:
            description = ""
        n.set_mem(251,64,nodes.normalize(description,64))
        if "basic_events" in js:
            index=0
            for ev in js["basic_events"]:
                debug("basic",index,ev)
                n.set_mem(Node_cpnode.CHANNELS_SEGMENT,2+index*8,Event.from_str(ev).id)
                index+=1
        if "IOX_events" in js:
            debug("IOX",index,ev)
            offset = 2+cmri.CPNode.total_IO*2*8+1   #beginning of the first IOX event
            index = 0
            for ev in js["IOX_events"]:
                #compute the offset where the event must go in memory (remember its 1 byte (I or O)
                #and then 16 times two events
                n.set_mem(Node_cpnode.CHANNELS_SEGMENT,offset,Event.from_str(ev).id)
                index+=1
                offset+=8    #next event
                if index%16==0:  #16 events per card, add 1 to skip the I/O byte of the next card
                    offset+=1
        return n

    def to_json(self):
        name = self.read_mem(251,1,63)
        descr = self.read_mem(251,64,64)
        #dict describing the node, first part
        node_desc = {"fullID":self.ID,"cmri_node_add":self.cp_node.address,
                     "version":self.read_mem(251,0,1)[0],"name":name[:name.find(0)].decode('utf-8'),
                     "description":descr[:descr.find(0)].decode('utf-8'),
                     "IO_config":self.read_mem(Node_cpnode.CHANNELS_SEGMENT,1,1)[0],
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
        channels_mem=nodes.Mem_space([(0,1),(1,1)])  #node address and io config
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
        self.memory = {251:nodes.Mem_space([(0,1),(1,63),(64,64)]),
                       Node_cpnode.CHANNELS_SEGMENT:channels_mem}
        #self.memory[251].dump()
        #self.memory[Node_cpnode.CHANNELS_SEGMENT].dump()
        
            
    def __init__(self,ID):
        super().__init__(ID)
        self.cp_node=None        #real node
        self.ev_list=[[b"\0"*8,b"\0"*8]]*16   #basic event list: inputs events always first!
        self.ev_list_IOX = [[b"\0"*8,b"\0"*8]]*128    #IOX events list for 8 IO lines for 16 cards max

    def get_low_level_node(self): #returns the underlying cpnode
        return self.cpnode
    
    def get_IOX_CDI(self):
        
        res = Node_cpnode.CDI_IOX_repetition_beg.replace("%nbiox","16") #fixme
        res+= Node_cpnode.CDI_IOX
        res+= Node_cpnode.CDI_IOX_repetition_end
        return res
        
    def get_CDI(self):
        return Node_cpnode.CDI_header+self.get_IOX_CDI()+Node_cpnode.CDI_footer

    def set_mem(self,mem_sp,offset,buf):
        super().set_mem(mem_sp,offset,buf)
        if mem_sp == Node_cpnode.CHANNELS_SEGMENT:
            if offset == 0:
                #address change
                debug("changing address",self.cp_node.address,buf[0])
                self.cp_node.address = buf[0]
            elif offset == 1:
                debug("Changing IO type, not supported!")
                pass
                #FIXME: I dont handle the I/O type change for now
            elif offset >=2 and offset-2<self.cp_node.total_IO*2*8: #check if we change a basic IO event
                #rebuild the events if they have changed
                entry = (offset-2)//16
                if (offset-2)%16==0:
                    index_ev=0
                else:
                    index_ev=1
                debug("entry=",entry,"off=",offset)
                self.ev_list[entry][index_ev]=self.read_mem(mem_sp,offset,8)
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
                        index_ev = 0
                    else:
                        index_ev = 1
                    self.ev_list_IOX[card*8+ev_pair_index][index_ev]=self.read_mem(mem_sp,offset)

    def poll(self):
        self.cp_node.read_inputs()
        
    def generate_events(self):
        ev_lst = []
        cpn = self.cp_node
        for i in range(cpn.nb_I):
            if cpn.inputs[i][0]!=cpn.inputs[i][1]: #input change send corresponding event
                if self.ev_list[i][cpn.inputs[i][0]]!=b"\0"*8: #do not generate event if 0.0.0.0.0.0.0.0
                    ev_lst.append(Event(self.ev_list[i][cpn.inputs[i][0]],self.aliasID))
        current_bit = 0
        ev_index = 0
        for i in cpn.IOX:
            if i==2: #its an input port
                for j in range(8): #check all bits
                    if cpn.inputs_IOX[current_bit][0]!=cpn.inputs_IOX[current_bit][1]:
                        if self.ev_list[ev_index][cpn.inputs_IOX[current_bit][0]]!=b"\0"*8:
                            ev_lst.append(Event(self.ev_list[ev_index][cpn.inputs_IOX[current_bit][0]],
                                                self.aliasID))
                    ev_index+=1 #next ev index
                    current_bit+=1 #next bit
            else:
                current_bit+=8   #first bit of next card
                ev_index+=8
                
        return ev_lst

    def check_id_producer_event(self,ev):
        """
        check if the event ev is coherent with one input state
        This is used to reply to "identify producer" event
        Return valid/invalid/unknown if the event corresponds to an input
        None otherwise
        """
        #First for board outputs
        for i in range(self.cp_node.nb_I):
            val = -1
            if ev.id == self.ev_list[i][0]:
                val = 0
            elif ev.id == self.ev_list[i][1]:
                val = 1
            if val!=-1:
                #found the input corresponding to the event
                #check if state is coherent with event
                #if state is -1, we return unknown
                if self.cp_node.inputs[i][0] == val:
                    return Node.ID_PRO_CON_VALID
                elif self.cp_node.inputs[i][0] != -1:
                    return Node.ID_PRO_CON_INVAL
                else:
                    return Node.ID_PRO_CON_UNKNOWN
        #Second for IOX:fixme
        
        return None

    def find_consumer_event(self,ev):
        """
        Find the Output event (we are then a consumer here)
        Return a list of tuples (index,value), index indicates the outputs index
        """
        res = []
        for i in range(self.cp_node.nb_I,self.cp_node.total_IO):
            if ev.id == self.ev_list[i][0]:
                res.append( (i-self.cp_node.nb_I,0) )
            elif ev.id == self.ev_list[i][1]:
                res.append( (i-self.cp_node.nb_I,1) )
        #fixme add IOX
        return res

    def find_consumer_event_IOX(self,ev):
        """
        Find the IOX Output events (we are then a consumer here)
        Return a list of tuples (index,value), index indicates the IOX outputs index
        """
        res = []
        ev_index=0
        output_index=0
        for i in self.IOX:
            if i==1: #output card
                for j in range(8):
                    if ev.id == self.ev_list_IOX[ev_index][0]:
                        res.append( (output_index,0) )
                    elif ev.id == self.ev_list_IOX[ev_index][1]:
                        res.append( (output_index,1) )
                    ev_index+=1
                    output_index+=1
            else:
                ev_index+=8  #input card so skip 8 events pairs
        return res
    
    def producer_identified(self,ev,filename,valid):
        """
        Will set the output according to the validity returned by the producer node
        valid is True or False
        """
        modified = False
        res = self.find_consumer_event(ev)
        for index,val in res:
            if not valid:
                #invalid so we set value to the one not corresponding to the event
                if val==0:
                    val = 1
                else:
                    val = 0
            if val!=self.cp_node.outputs[index]:
                self.cp_node.set_output(index,val)
                modified = True
                
        #IOX outputs
        res = self.find_consumer_event_IOX(ev)
        for index,val in res:
            if not valid:
                #invalid so we set value to the one not corresponding to the event
                if val==0:
                    val = 1
                else:
                    val = 0
            if val!=self.cp_node.outputs_IOX[index]:
                self.cp_node.set_output_IOX(index,val)
                modified = True

        if modified:
            self.cp_node.write_outputs(filename)

    def check_id_consumer_event(self,ev):
        """
        check if the event ev is coherent with output state
        This is used to reply to "identify consumer" event
        Return valid/invalid/unknown if the event corresponds to an output
        If there are several outputs consuming the same event, we return UNKNOWN
        if 2 outputs have different state (we do not count unset outputs)
        None otherwise
        """
        
        consumers = self.find_consumer_events(ev)
        result = None
        for index,val in consumers:
            if self.cp_node.outputs[index][0] == val:
                new = Node.ID_PRO_CON_VALID
            elif self.cp_node.outputs[index][0] != -1:
                new = Node.ID_PRO_CON_INVAL
            if result is not None and new!=result:
                return Node.ID_PRO_CON_UNKNOWN
            result = new
        #IOX
        consumers = self.find_consumer_events_IOX(ev)
        for index,val in consumers:
            if self.cp_node.outputs_IOX[index][0] == val:
                new = Node.ID_PRO_CON_VALID
            elif self.cp_node.outputs_IOX[index][0] != -1:
                new = Node.ID_PRO_CON_INVAL
            if result is not None and new!=result:
                return Node.ID_PRO_CON_UNKNOWN
            result = new
        
        return result

    def consume_event(self,ev,filename):
        #the node might consume the same event for several outputs (one event controlling several outputs)
        debug("node consume, ev=",ev.id)
        modified = False
        index = 0
        for ev_pair in self.ev_list:
            val = -1
            if ev.id == ev_pair[0]:
                val = 0
            elif ev.id == ev_pair[1]:
                val = 1
            debug("consume event:",index,">=?",self.cp_node.nb_I," val=",val)
            if val>=0 and index>=self.cp_node.nb_I:  #we only consume event for outputs
                self.cp_node.set_output(index-self.cp_node.nb_I,val)
                modified = True
            elif val>=0 and index<self.cp_node.nb_I:
                debug("Event received for an input! (event id=",ev.id,")")
            index+=1
        card_index = 0
        output_index=0
        counter = 0  #count each event so card index is counter//8
        #fixme check if correct
        for ev_pair in self.ev_list_IOX:
            val = -1
            if ev.id == ev_pair[0]:
                val = 0
            elif ev.id == ev_pair[1]:
                val = 1
            debug("consume event:",index," val=",val)
            if self.cp_node.IOX[counter//8]==1:
                if val>=0:  #we only consume event for outputs
                    self.cp_node.set_output_IOX(output_index,val)
                    modified = True
                output_index+=1 #next output
            elif val>=0 and self.cp_node.IOX[counter//8]==2:
                debug("Event received for an IOX input! (event id=",ev.id,")")
            elif val>=0 and self.cp_node.IOX[counter//8]==0:
                debug("Event received for an empty IOX slot! (event id=",ev.id,")")
            
            counter+=1
        if modified:
            self.cp_node.write_outputs(filename)
