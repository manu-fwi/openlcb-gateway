import openlcb_cmri_cfg as cmri
from openlcb_protocol import *
from openlcb_debug import *
import openlcb_config
import openlcb_nodes as nodes

class Node_SUSIC(nodes.Node):
    CDI_header="""<?xml version="1.0"?>
<cdi xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:noNamespaceSchemaLocation="http://openlcb.org/schema/cdi/1/1/cdi.xsd">

<identification>
<manufacturer>(S)USIC-OLCB-GW</manufacturer>
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
<description>The (S)USIC address.</description>
<min>0</min><max>127</max>
</int>
<group>
<name>Node type</name>
<int size="1">
<default>1</default>
<map>
<relation><property>N</property><value>USIC or 24 bits cards SUSIC</value></relation>
<relation><property>X</property><value>SUSIC with 32 bits cards</value></relation>
</map>
</int>
</group>
"""
    CDI_cards_begin = """<group>
<name>Card %cardindex</name>
<description>Expansion card</description>
"""
    CDI_cards_end ="""</group>"""
    CDI_slots ="""<group replication="%nbslots">
<name>Slots</name>
<description>Slots</description>
<repname>Slot</repname>
<group replication="%nbbits">
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
</group>
"""
    CDI_footer = """</segment>
</cdi>
\0"""

    CDI_IO_repetition_end="""</group>
"""
    #default dict to add new nodes to the DB when they have no description (used by cmri_net_bus)
    DEFAULT_JSON = { "fullID":None,"cmri_node_add":0,"type":"N" }
    @staticmethod
    def from_json(js):
        debug("from JSON")
        if "type" not in js:
            js["type"]="N"
        if "cards_sets" not in js:
            js["cards_sets"]=[]
        n = Node_SUSIC(js["fullID"],js["cmri_node_add"],js["type"],js["cards_sets"])
        n.create_memory()
        n.set_mem(253,0,bytes((js["cmri_node_add"],)))
        n.set_mem(253,1,js["type"].encode("ascii"))
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
        debug("avant2")
        if "description" in js:
            description= js["description"]
        else:
            description = ""
        n.set_mem(251,64,nodes.normalize(description,64))
        debug("apres2")
        if "events" in js:
            index=0
            for ev in js["events"]:
                debug("event",index,ev)
                n.set_mem(253,2+index*8,Event.from_str(ev).id)
                index+=1
        debug("SUSIC from JSON")
        return n

    def to_json(self):
        name = self.read_mem(251,1,63)
        descr = self.read_mem(251,64,64)
        #dict describing the node, first part
        node_desc = {"fullID":self.ID,"cmri_node_add":self.cp_node.address,
                     "version":self.read_mem(251,0,1)[0],"name":name[:name.find(0)].decode('utf-8'),
                     "description":descr[:descr.find(0)].decode('utf-8'),
                     "type":self.read_mem(253,1,1)[0],
                     "cards_sets":self.cards_sets}
        str_events=[]
        debug("ev_list",len(self.ev_list))
        for ev in self.ev_list:
            debug(ev)
            str_events.extend((str(Event(ev[0])),str(Event(ev[1]))))
        node_desc["events"]=str_events

        debug("node desc=",node_desc)
        return node_desc
        
                
    def create_memory(self):           
        channels_mem=nodes.Mem_space([(0,1),(1,1)])  #node address and node type ("N" or "X")
        offset = 2
        #loop over all I/O channels
        for i in range((len(self.susic.inputs)+len(self.susic.outputs))*2): #2 events per IO line
            channels_mem.create_mem(offset,8)
            channels_mem.set_mem(offset,b"\0"*8)    #default event
            offset+=8
        self.memory = {251:nodes.Mem_space([(0,1),(1,63),(64,64)]),
                       253:channels_mem}
        #self.memory[251].dump()
        #self.memory[253].dump()
        
            
    def __init__(self,ID,address,node_type,cards_sets):
        super().__init__(ID)
        self.cards_sets = cards_sets   #list of cards config strings ("IOII", or "O" for example)
        self.susic=cmri.SUSIC(address,node_type,self.cards_sets_encode())        #real node
        self.ev_list=[]  #events list:list of 4 elements:
                         #event pair,type of I/O ("I" or "O") and index of the corresponding I/O line
        self.create_ev_list()

    def get_low_level_node(self):  #return the underlying susic node object
        return self.susic
    
    def create_ev_list(self):
        input_index = 0
        output_index = 0
        for card in self.cards_sets:  #for each card
            for io in card:           #for each I/O
                for i in range(self.susic.nb_bits_per_slot()): #one event pair for each I/O line
                    if io=="I":  #input
                        self.ev_list.append([b"\0"*8,b"\0"*8,io,input_index])
                        input_index+=1
                    else:  #output
                        self.ev_list.append([b"\0"*8,b"\0"*8,io,output_index])
                        output_index+=1
                        
    def cards_sets_encode(self):
        """
        Encode the cards sets from list of strings (ex: ["IOO",...]) to list of bytes as per CMRI documentation
        """
        encoded_cards = []
        for card in self.cards_sets:
            debug("card=",card)
            encoded_byte = 0
            shift = 0
            for slot in card:
                if shift>6:
                    debug("card description too long!")
                    continue
                debug("slot=",slot," shift=",shift," encoded_byte=",encoded_byte)
                if slot == "O":
                    encoded_byte |= 2 << shift
                elif slot =="I":
                    encoded_byte |= 1 << shift
                else:
                    debug("Cards sets decode error!")
                shift += 2
            encoded_cards.append(encoded_byte)
        return encoded_cards
    
    def get_IO_CDI(self):
        res = ""
        nb_bits_per_slot = self.susic.nb_bits_per_slot()
        for index in range(len(self.cards_sets)):
            res += Node_SUSIC.CDI_cards_begin.replace("%cardindex",str(index))
            res += Node_SUSIC.CDI_slots.replace("%nbslots",str(len(self.cards_sets[index]))).replace("%nbbits",str(nb_bits_per_slot))
            res+= Node_SUSIC.CDI_cards_end
        return res
        
    def get_CDI(self):
        return Node_SUSIC.CDI_header+self.get_IO_CDI()+Node_SUSIC.CDI_footer

    def set_mem(self,mem_sp,offset,buf):
        super().set_mem(mem_sp,offset,buf)
        if mem_sp == 253:
            if offset == 0:
                #address change
                debug("changing address",self.susic.address,buf[0])
                self.susic.address = buf[0]
            elif offset == 1:
                pass
                #FIXME: I dont handle the I/O type change for now
            elif offset >=2 and offset-2<(len(self.susic.inputs)+len(self.susic.outputs))*2*8: #check if we change a IO event
                #rebuild the events if they have changed
                entry = (offset-2)//16
                
                self.ev_list[entry][(offset-2)%16]=self.read_mem(mem_sp,offset,8)
            else:
                debug("set_mem out of IO")
                
    def poll(self):
        self.susic.read_inputs()
        
    def generate_events(self):
        ev_lst = []
        changes = self.susic.inputs.indices_of_changes()  #sorted list of indices of changed input lines
        ev_index = 0
        for index in changes:
            #look for an input line with corresponding to the current index
            while ev_index<len(self.ev_list) and (self.ev_list[ev_index][2]!="I"
                                                  or self.ev_list[ev_index][3]!=index):
                ev_index+=1
            if ev_index >= len(self.ev_list):
                debug("Index error in SUSIC generate events!")
                return
            if self.ev_list[ev_index][self.susic.inputs[index][0]]!=b"\0"*8: #do not generate event if 0.0.0.0.0.0.0.0
                    ev_lst.append(Event(self.ev_list[ev_index][self.susic.inputs[index][0]],self.aliasID))

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

    def consume_event(self,rcvd_ev,filename):
        #the node might consume the same event for several outputs (one event controlling several outputs)
        debug("node consume, ev=",rcvd_ev.id)
        modified = False
        for ev in self.ev_list:
            val = -1
            if rcvd_ev.id == ev[0]:
                val = 0
            elif rcvd_ev.id == ev[1]:
                val = 1
            debug("SUSIC consume event:",rcvd_ev.id," val=",val)
            if val>=0 and ev[2]=="O":  #we only consume event for outputs
                self.susic.outputs.set_bit(ev[3],val)
                modified = True
            elif val>=0:
                debug("[SUSIC] Event received for an input! (event id=",ev.id,")")
        
        if modified:
            self.susic.write_outputs(filename)
        
def find_node_from_cmri_add(add,nodes):
    for n in nodes:
        if n.cp_node.address == add:
            return n
    return None
