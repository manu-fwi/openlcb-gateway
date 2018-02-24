import openlcb_cmri_cfg as cmri
import openlcb_server

acdi_xml = """<?xml version="1.0"?>
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
                elif len(self.mem_chunks[offset])>size:
                    print("memory write error in set_mem_partial, chunk size is bigger than memory size at",offset)
                    

    def set_mem(self,offset,buf):
        if (offset,len(buf)) in self.mem:
            self.mem[(offset,len(buf))]=buf
            return True
        else:
            print("set_mem failed, off=",offset,"buf=",buf," fo length=",len(buf))
            return False
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

class frame:
    @staticmethod
    def build_verified_nID(src_node,simple_proto):
        if simple_proto:
            res = frame(src_node,None,0x19171)
        else:
            res = frame(src_node,None,0x19170)
        res.data=hexp(src_node.ID,12).encode('utf-8')
        return res
                    
    def __init__(self,src_node,dest_node,header):
        self.src = src_node
        self.dest = dest_node
        self.header = header
        
    def add_data(self,bytes_arr):
        self.data = bytes_arr   #data is a byte array, no more than 8 bytes!

    def to_gridconnect(self):
        res=":X"+hexp(self.header,4)+hexp(self.src_node.aliasID,3)+"N"
        res+=convert_hex_b(self.data)+";"
        return res
    
class addressed_frame(frame):
    def __init__(self,src,dest,pos,MTI):
        super().__init__(src,dest,0x19)
        self.pos = pos   # pos = 0: one datagram alone, 1=first of several, 2=middle,3=last
        self.MTI = MTI

    def to_gridconnect(self):
        res=":X19"+hexp(self.MTI,3)+hexp(self.src.aliasID,3)+"N"
        if self.dest!=None and (self.MTI & 0x008)!=0: #address present is set
            res+=hexp(self.pos,1)+hexp(self.dest.aliasID,3)
        res+=convert_hex_b(self.data)+";"
        return res.encode('utf-8')
    
class datagram_content(frame):
    ONE = 0
    FIRST = 1
    MIDDLE =2
    LAST=3
    def __init__(self,src_node,dest_node,pos):
        super().__init__(src_node,dest_node,None)
        self.pos = pos    # pos = 0: one datagram alone, 1=first of several, 2=middle,3=last

    def to_gridconnect(self):
        res=":X1"+chr(ord(b"A")+self.pos)+hexp(self.dest.aliasID,3)+hexp(self.src.aliasID,3)+b"N"
        res+=convert_hex_b(self.data)+";"
        return res.encode('utf-8')
        

class datagram_rcv(frame):
    def __init__(self,src_node,dest_node,OK,reply_pending = False):
        super().__init__(src_node,dest_node,None)
        self.OK = OK
        self.reply_pending = reply_pending

    def to_gridconnect(self): #return string
        res = ":X19A"
        if self.OK:
            res+="2"
        else:
            res+="4"
        res+="8"+hexp(self.src_node.aliasID,3)+"N"
        if self.reply_pending:#fixme: need to make sure where to put this flag
            res+="8"
        else:
            res+="0"
        res+=hexp(self.dest_node.aliasID,3)
        if not self.OK:
            res+="0000" #FIXME for rejected datagram we need error codes
        return res

    def set_flags(self,reply_pending):
        self.reply_pending = reply_pending
        
def create_datagram_list(src,dest,data):  #data is the payload, no more than 64 bytes!
    if len(data)<=8:
        l = [datagram_content(src,dest,datagram_content.ONE)]
        l[0].add_data(data)
        return l
    pos = 0
    l=[datagram_content(src,dest,datagram_content.FIRST)]
    l[0].add_data(data[:8])
    pos = 8
    while pos < len(data):
        if pos+8 < len(data):
            datagram_pos = datagram_content.MIDDLE
        else:
            datagram_pos = datagram_content.LAST
        d = datagram_content(src,dest,datagram_pos)
        d.add_data(data[pos:pos+8])
        pos+=8
    return l

def create_addressed_frame_list(src,dest,MTI,data):  #data is the payload, no more than 64 bytes!
    if len(data)<=6:
        l = [addressed_frame(src,dest,0,MTI)]
        l[0].add_data(data)
        return l
    pos = 0
    l=[addressed_frame(src,dest,1,MTI)]
    l[0].add_data(data[:6])
    pos = 8
    while pos < len(data):
        if pos+6 < len(data):
            frame_pos = 2
        else:
            frame_pos = 3
        d = datagram_content(src,dest,frame_pos,MTI)
        d.add_data(data[pos:pos+6])
        pos+=6
    return l

def data_from_dgram_list(dgram_l):
    l = b""
    for d in dgram_l:
        l += d.data
    return l

class event:
    def __init__(self,id):
        self.id = id

    def automatically_routed(self):
        return self.id[0]==0 and self.id[1]==0

class node:
    def __init__(self,ID,permitted,aliasID=None):
        self.ID = ID
        self.aliasID = aliasID
        self.permitted=permitted
        self.produced_ev=[]
        self.consumed_ev=[]
        self.simple_info = []

    def add_consumed_ev(self,ev):
        self.consumed_ev.append(ev)

    def add_produced_ev(self,ev):
        self.produced_ev.append(ev)

    def set_simple_info(self,list):
        self.simple_info = list  #byte arrays

    def build_simple_info(self): # return datagrams holding the simple info
        print("build_simple_info not implemented!") #fixme
    
class can_segment:
    def __init__(self,name):
        self.name = name
        self.nodes = []

    def push_datagram(self,dgram):
        if dgram.dest_node is not None or dgram.dest_node in self.nodes:
            self.send_frame(dgram.to_can())

    def push_event(self,ev):
        for n in self.nodes:
            if ev in n.consumed_ev:
                self.send_frame(ev.to_can())
                return
            
    def send_frame(self,can_frame):
        #fixme to do!
        print("sending can frame",can_frame)
        
        
#protocols definitions
SPSP   = 0x800000 # Simple Protocol subset
DGP    = 0x400000 # Datagram Protocol
STP    = 0x200000 # Stream Protocol
MCP    = 0x100000 # Memory Configuration Protocol
RP     = 0x080000 # Reservation Protocol
EEP    = 0x040000 # Event Exchange (Producer/Consumer) Protocol
IDP    = 0x020000 # Identification Protocol
TLCP   = 0x010000 # Teaching/Learning Configuration Protocol
RBP    = 0x008000 # Remote Button Protocol
ADCDIP = 0x004000 # Abbreviated Default CDI Protocol
DP     = 0x002000 # Display Protocol
SNIP   = 0x001000 # Simple Node Information Protocol
CDIP   = 0x000800 # Configuration Description Information (CDI)
TCP    = 0x000400 # Traction Control Protocol (Train Protocol)
FDIP   = 0x000200 # Function Description Information (FDI)
DCCCSP = 0x000100 # DCC Command Station Protocol
STNIP  = 0x000080 # Simple Train Node Information Protocol
FCP    = 0x000040 # Function Configuration
FUP    = 0x000020 # Firmware Upgrade Protocol
FUAP   = 0x000010 # Firmware Upgrade Active

#globals: fixme
gw_add= node(0x020112AAAAAA,True,0xAAA)
mfg_name_hw_sw_version=["\4python gateway","test","1.0","1.0","\2gw1","gateway-1"]
current_write = None
managed_nodes = {}   #holds the correspondance LCB node <-> CMRI node

def get_lcb_node_from_alias(alias):
    found = None
    for n in managed_nodes.keys():
        if n.aliasID == alias:
            found = n
            break
    return found

def hexp(i,width):
    s=hex(i)[2:].upper()
    return "0"*(width-len(s))+s

def convert_to_hex(buf): #return string
    res=""
    for c in buf.encode('utf-8'):
        res+=hexp(c,2)
    return res

def convert_to_hex_b(buf): #return string
    res=""
    for c in buf:
        res+=hexp(c,2)
    return res

def send_fields(sock,MTI,fields,dest):
    send_long_message(sock,MTI,("\0".join(fields)).encode('utf-8'),dest)

def send_long_message(sock,MTI,text,dest): #text must be a byte array
    pos = 0
    last=False
    first=True
    while not last:
        msg = ":X19A08"+hexp(gw_add.aliasID,3)+"N"
        if pos+6>len(text):
            last=True
            if not first:
                msg+="2"  #last frame
            else:
                msg+="0"  #only one frame
        else:
            if not first:
                msg+="3"  #middle frame
            else:
                msg+="1"  #first frame
            first = False
        msg+=hexp(dest,3)
        #print("pos=",pos,"len=",len(text),"txt=",text[pos:min(pos+6,len(text))])
        for c in text[pos:min(pos+6,len(text))]:
            msg+=hexp(c,2)
        if last:
            msg+=hexp(0,2*(pos+6-len(text))) #pad with zero bytes
        msg+=";"
        print("sent SNRI-->",msg)
        sock.send(msg.encode('utf-8'))
        pos+=6

def send_datagram_multi(s,src_id,reply,buf,first_payload):
    #exaclty send the byte buffer buf: must be null terminated if it is a string

    msg = ":X1"
    if len(buf)<=first_payload:
        msg+="A"
    else:
        msg+="B"
    msg+=hexp(src_id,3)+"AAAN"+reply
    msg+=convert_to_hex_b(buf[:first_payload])+";"
    print("datagram sent >>",msg," = ",buf[:first_payload])
    s.send(msg.encode('utf-8'))
    #Now the rest of the data

    pos = first_payload
    while pos<len(buf) and pos<64:
        if pos+8<len(buf) and pos+8<64: #more than enough remaining
            msg=":X1C"
            end=pos+8
        else:
            msg=":X1D"  #last frame
            end = min(64,len(buf))
                
        msg+=hexp(src_id,3)+"AAAN"
        msg+=convert_to_hex_b(buf[pos:end])+";"
        msg2=buf[pos:end]
        pos+=8
        s.send(msg.encode('utf-8'))
        print("datagram sent >>",msg," = ",msg2)
        
def send_CDI(s,src_id,address,acdi_xml):
    msg = ":X1"
    end = min(address+2,len(acdi_xml))
    if len(acdi_xml)>end:   #check if one frame is enough
        msg+="B"
    else:
        msg+="A"
    msg+=hexp(src_id,3)+hexp(gw_add.aliasID,3)+"N2053"
    msg+=hexp(address,8)
   
    msg+=convert_to_hex(acdi_xml[address:end])+";"
    print("datagram sent >>",msg," = ",acdi_xml[address:address+2])
    s.send(msg.encode('utf-8'))
    if len(acdi_xml)<=end:  #we are done already
        return
    #Now the rest of the data
    pos = 2
    while address+pos<len(acdi_xml) and pos<64:
        if address+pos+8<len(acdi_xml) and pos+8<64: #more than enough remaining
            msg=":X1C"
            end=address+pos+8
        else:
            msg=":X1D"  #last frame
            end = min(address+64,len(acdi_xml))
                
        msg+=hexp(src_id,3)+hexp(gw_add.aliasID,3)+"N"
        msg+=convert_to_hex(acdi_xml[address+pos:end])+";"
        msg2=acdi_xml[address+pos:end]
        pos+=8
        s.send(msg.encode('utf-8'))
        print("datagram sent >>",msg," = ",msg2)

def memory_read(s,src,add,msg):   #msg is mem read msg as string
    global memory
    to_send=bytearray()

    if msg[13:15]=="40":
        mem_sp = int(float.fromhex(msg[23:25]))
        size = int(float.fromhex(msg[25:27]))
        m = hexp(mem_sp,2)
        first_payload=1
    else:
        mem_sp = 0xFC+int(msg[14])
        size=int(float.fromhex(msg[23:25]))
        m = ""
        first_payload=2
    print("memory read at",mem_sp,"offset",size)
    if mem_sp not in memory:
        print("memory unknown!!")
        return
    mem = memory[mem_sp].read_mem(add)
    if mem is None:
        print("memory error")
    else:
        to_send= bytearray("205"+msg[14]+hexp(add,8)+m,'utf-8')
        to_send.extend(mem[:size])
        print(to_send)
        dgrams = create_datagram_list(gw_add,src,to_send)
        print("mem read datagrams:",end="")
        for d in dgrams:
            print(d.to_gridconnect())
            
        send_datagram_multi(s,src,("205"+msg[14]+hexp(add,8)+m),
                            to_send[:size],first_payload)

def memory_write(s,src_id,add,buf):  #buf: write msg as string
    global memory,current_write

    print("memory write")
    if buf[3]=="A" or buf[3]=="B":
        if buf[14]=="0":
            mem_sp = int(float.fromhex(buf[23:25]))
            data_beg=25
        else:
            mem_sp = 0xFC+int(buf[14])
            data_beg=23
        current_write=(mem_sp,add)
        s.send((":X19A28"+hexp(gw_add.aliasID,3)+"N0"+hexp(src_id,3)+";").encode("utf-8"))
        print("datagram received ok sent --->",":X19A28"+hexp(gw_add.aliasID,3)+"N8"+hexp(src_id,3)+";")
    else:
        data_beg=11
    if current_write is None:
        print("write error: trying to write but current_write is none!!")
    else:
        res=b""
        for pos in range(data_beg,len(buf)-1,2):
            print(buf[pos:pos+2])
            res+=bytes([int(float.fromhex(buf[pos:pos+2]))])
        print("written:",res)
        print("memory write",current_write[0],"offset",current_write[1])
        if current_write[0] not in memory:
            print("memory unknown!")
            return
        memory[current_write[0]].set_mem_partial(current_write[1],res)
    if buf[3]=="A" or buf[3]=="D":
        current_write = None

def process_grid_connect(cli,msg):
    s=cli.sock
    if msg[:2]!=":X":
        print("Error: not an extended frame!!")
        return
    if msg[10]!="N":
        print("Error: not a normal frame!!")
        return
    data_present = msg[11]!=";"
    first_b = int(float.fromhex(msg[2:4]))
    can_prefix = (first_b & 0x18) >> 3
    var_field = int(float.fromhex(msg[4:7]))
    src_id = int(float.fromhex(msg[7:10]))
    print("data pre=",data_present," first_b=",first_b," can_prefix=",can_prefix," var_field=",var_field," src_id=",src_id)
    
    if can_prefix % 2==0:
        #Can Control frame
        data_needed = False
        #fixme: process these frame properly
        #full_ID = var_field << 12*((first_b&0x7) -4)
        if first_b & 0x7>=4 and first_b & 0x7<=7:
            print("CID Frame n°",first_b & 0x7," * ",hex(var_field),end=" * 0x")
            #full_ID = var_field << 12*((first_b&0x7) -4)
        elif first_b&0x7==0:
            if var_field==0x700:
                print("RID Frame * full ID=")#,hex(full_ID),end=" * ")
                jmri_identified = True
                #managed_nodes[node(full_ID,True,src_id)]=None #JMRI node only for now
            elif var_field==0x701:
                print("AMD Frame",end=" * ")
                data_needed = True
            elif var_field==0x702:
                print("AME Frame",end=" * ")
                data_nedded=True
            elif var_field==0x703:
                print("AMR Frame",end=" * ")
                data_nedded=True
            elif var_field>=0x710 and var_field<=0x713:
                print("Unknown Frame",end=" * ")
        print(hexp(src_id,3))
        if data_needed and not data_present:
            print("Data needed but none is present!")
            return
    else:
        if (first_b & 0x7)==1:  #global or addressed frame msg
            
            if var_field==0x490:  #Verify node ID
                s.send((":X19170"+hexp(gw_add.aliasID,3)+"N"+hexp(gw_add.ID,12)+";").encode('utf-8'))
                print("Sent---> :X19170"+hexp(gw_add.aliasID,3)+"N"+hexp(gw_add.ID,12)+";")
            elif var_field==0x828:#Protocol Support Inquiry
                dest_node = int(float.fromhex(msg[12:15]))
                if dest_node==gw_add.aliasID:
                    s.send((":X19668"+hexp(gw_add.aliasID,3)+"N0"+hexp(src_id,3)+hexp(SPSP|SNIP|CDIP,6)+"000000;").encode("utf-8"))
                    print("sent--->:X19668"+hexp(gw_add.aliasID,3)+"N0"+hexp(src_id,3)+hexp(SPSP|SNIP|CDIP,6)+"000000;")
            elif var_field == 0xDE8:#Simple Node Information Request

                dest_node = int(float.fromhex(msg[12:15]))
                if dest_node==gw_add.aliasID:
                    print("sent SNIR Reply")
                    #s.send((":X19A08"+hexp(gw_add.aliasID,3)+"N1"+hexp(src_id,3)+"04;").encode("utf-8"))#SNIR header
                    #print(":X19A08"+hexp(gw_add.aliasID,3)+"N1"+hexp(src_id,3)+"04;")
                    send_fields(s,0xA08,mfg_name_hw_sw_version,src_id)

                    #s.send((":X19A08"+hexp(gw_add.aliasID,3)+"N3"+hexp(src_id,3)+"02;").encode("utf-8"))#SNIR header
                    #print(":X19A08"+hexp(gw_add.aliasID,3)+"AAAN3"+hexp(src_id,3)+"02;")
                    #send_fields(0xA08,username_desc,src_id,True)
        elif (first_b & 0x7)>=2 and (first_b & 0x7)<=5: #Datagram
            address = int(float.fromhex(msg[15:23]))
            print("datagram!!")
            #for now we assume a one frame datagram
            if var_field!=gw_add.aliasID: #not for us
                print("Frame is not for us!!")
                return
            print(msg[11:13])
            if current_write is not None: #Fixme
                memory_write(s,src_id,address,msg)
            elif msg[11:15]=="2043": #read command for CDI
                print("read command, address=",int(float.fromhex(msg[15:23])))
                s.send((":X19A28"+hexp(gw_add.aliasID,3)+"N8"+hexp(src_id,3)+";").encode('utf-8'))
                print("datagram received ok sent --->",(":X19A28"+hexp(gw_add.aliasID,3)+"N8"+hexp(src_id,3)+";").encode("utf-8"))
                send_CDI(s,src_id,address,acdi_xml)
            elif msg[11:13]=="20": #read/write command
                s.send((":X19A28"+hexp(gw_add.aliasID,3)+"N8"+hexp(src_id,3)+";").encode('utf-8'))
                print("datagram received ok sent --->",(":X19A28"+hexp(gw_add.aliasID,3)+"N8"+hexp(src_id,3)+";").encode("utf-8"))
                if msg[13]=="4":
                    memory_read(s,get_lcb_node_from_alias(src_id),address,msg)
                elif msg[13]=="0":
                    memory_write(s,src_id,address,msg)

#for now: 1 can segment with all cmri nodes on it
cmri_nodes = cmri.load_cmri_cfg("cmri_cfg_test.txt")
#create mem segment for each channel
channels_mem=mem_space([(0,1)])  #first: version
channels_mem.set_mem(0,b"\1")
info_sizes = [1,8,8]         #one field for I or O and 4 events (2 for I and 2 for O)
offset = 1
for i in range(16):   #loop over 16 channels
    for j in info_sizes:
        channels_mem.create_mem(offset,j)
        buf = bytearray()
        buf.extend([i]*j)
        channels_mem.set_mem(offset,buf)
        offset+=j
                             
memory = {251:mem_space([(0,1),(1,63),(64,64)]),
          253:channels_mem}
memory[251].set_mem(0,b"\1")
memory[251].set_mem(1,b"gw1"+(b"\0")*(63-3))
memory[251].set_mem(64,b"gateway-1"+(b"\0")*(64-9))
memory[251].dump()
memory[253].dump()
input("waiting")
serv = openlcb_server.server("127.0.0.1",50000)
serv.start()

done = False
while not done:
    reads = serv.wait_for_clients()
    serv.process_reads(reads)
    for c in serv.clients:
        msg = c.next_msg(";")
        if msg and msg != ";":
            process_grid_connect(c,msg)
