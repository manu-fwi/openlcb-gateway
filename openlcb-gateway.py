import openlcb_cmri_cfg as cmri
import openlcb_server
from openlcb_nodes import *
import socket,select,time

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
        res+=convert_to_hex_b(self.data)+";"
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
        res+=convert_to_hex_b(self.data)+";"
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
        res=":X1"+chr(ord(b"A")+self.pos)+hexp(self.dest.aliasID,3)+hexp(self.src.aliasID,3)+"N"
        res+=convert_to_hex_b(self.data)+";"
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
    def __init__(self,id):  #id is a 8 bytes array
        self.id = id

    def automatically_routed(self):
        return self.id[0]==0 and self.id[1]==0

class alias_negotiation:
    def __init__(self,alias):
        self.aliasID = alias
        self.fullID=0
        self.step=0
    def next_step(self,fullID_part):
        self.fullID <<= 12
        self.fullID+=fullID_part
        self.step+=1
    def reserve(self):
        if self.step<4:
            print("Reserve alias=",self.aliasID," before all CID received (",self.step,")")
            return False
        return True


class can_segment:
    def __init__(self,name):
        self.name = name
        self.nodes = []

    def push_datagram(self,dgram):
        if dgram.dest_node is None and dgram.dest_node in self.nodes:
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

def get_alias_neg_from_alias(alias):
    found = None
    for n in list_alias_neg:
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

def send_fields(sock,src_node,MTI,fields,dest):
    send_long_message(sock,src_node,MTI,("\0".join(fields)).encode('utf-8'),dest)

def send_long_message(sock,src_node,MTI,text,dest): #text must be a byte array
    pos = 0
    last=False
    first=True
    while not last:
        msg = ":X19A08"+hexp(src_node.aliasID,3)+"N"
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

def send_datagram_multi(s,src_id,dest_id,reply,buf,first_payload):
    #exaclty send the byte buffer buf: must be null terminated if it is a string

    msg = ":X1"
    if len(buf)<=first_payload:
        msg+="A"
    else:
        msg+="B"
    msg+=hexp(dest_id,3)+hexp(src_id,3)+"N"+reply
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
                
        msg+=hexp(dest_id,3)+hexp(src_id,3)+"N"
        msg+=convert_to_hex_b(buf[pos:end])+";"
        msg2=buf[pos:end]
        pos+=8
        s.send(msg.encode('utf-8'))
        print("datagram sent >>",msg," = ",msg2)
        
def send_CDI(s,src_node,dest_id,address):
    acdi_xml = src_node.get_CDI()
    msg = ":X1"
    end = min(address+2,len(acdi_xml))
    acdi_xml = src_node.get_CDI()
    if len(acdi_xml)>end:   #check if one frame is enough
        msg+="B"
    else:
        msg+="A"
    msg+=hexp(dest_id,3)+hexp(src_node.aliasID,3)+"N2053"
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
                
        msg+=hexp(dest_id,3)+hexp(src_node.aliasID,3)+"N"
        msg+=convert_to_hex(acdi_xml[address+pos:end])+";"
        msg2=acdi_xml[address+pos:end]
        pos+=8
        s.send(msg.encode('utf-8'))
        print("datagram sent >>",msg," = ",msg2)

def memory_read(s,src,dest,add,msg):   #msg is mem read msg as string
    global memory
    to_send=bytearray()

    if msg[13:15]=="40":
        mem_sp = int(msg[23:25],16)
        size = int(msg[25:27],16)
        m = hexp(mem_sp,2)
        first_payload=1
    else:
        mem_sp = 0xFC+int(msg[14])
        size=int(msg[23:25],16)
        m = ""
        first_payload=2
    print("memory read at",mem_sp,"offset",add,"size",size)
    if mem_sp not in src.memory:
        print("memory unknown!!")
        return
    mem = src.read_mem(mem_sp,add)
    print("memory read sends:",mem)
    if mem is None:
        print("memory error")
    else:
        to_send= bytearray("205"+msg[14]+hexp(add,8)+m,'utf-8')
        to_send.extend(mem[:size])
        print("to_send=",to_send," raccourci=",to_send[12+len(m):12+len(m)+size])
        dgrams = create_datagram_list(src,dest,to_send)
        print("mem read datagrams:",end="")
        #for d in dgrams:
        #    print(d.to_gridconnect())
            
        send_datagram_multi(s,src.aliasID,dest.aliasID,("205"+msg[14]+hexp(add,8)+m),
                            to_send[12+len(m):12+len(m)+size],first_payload)

def memory_write(s,src_node,dest_node,add,buf):  #buf: write msg as string

    print("memory write")
    if buf[3]=="A" or buf[3]=="B":
        if buf[14]=="0":
            mem_sp = int(buf[23:25],16)
            data_beg=25
        else:
            mem_sp = 0xFC+int(buf[14])
            data_beg=23
        src_node.current_write=(mem_sp,add)
        s.send((":X19A28"+hexp(src_node.aliasID,3)+"N0"+hexp(dest_node.aliasID,3)+";").encode("utf-8"))
        print("datagram received ok sent --->",":X19A28"+hexp(src_node.aliasID,3)+"N0"+hexp(dest_node.aliasID,3)+";")
    else:
        data_beg=11
    if src_node.current_write is None:
        print("write error: trying to write but current_write is none!!")
    else:
        res=b""
        for pos in range(data_beg,len(buf)-1,2):
            print(buf[pos:pos+2])
            res+=bytes([int(buf[pos:pos+2],16)])
        print("written:",res)
        print("node:",src_node.ID,"memory write",src_node.current_write[0],"offset",src_node.current_write[1])
        if src_node.current_write[0] not in src_node.memory:
            print("memory unknown!")
            return
        src_node.memory[src_node.current_write[0]].set_mem_partial(src_node.current_write[1],res)
    if buf[3]=="A" or buf[3]=="D":
        src_node.current_write = None

def reserve_aliasID(src_id):
    neg=get_alias_neg_from_alias(src_id)
    if neg.reserve():
        if neg.aliasID in reserved_aliases:
            print("Error: trying to reserve alias ",neg.aliasID,"(",neg.fullID,") but its already reserved!")
        else:
            reserved_aliases[neg.aliasID]=neg.fullID
            list_alias_neg.remove(neg)
            
def process_grid_connect(cli,msg):
    s=cli.sock
    if msg[:2]!=":X":
        print("Error: not an extended frame!!")
        return
    if msg[10]!="N":
        print("Error: not a normal frame!!")
        return
    data_present = msg[11]!=";"
    first_b = int(msg[2:4],16)
    can_prefix = (first_b & 0x18) >> 3
    var_field = int(msg[4:7],16)
    src_id = int(msg[7:10],16)
    print("data pre=",data_present," first_b=",first_b," can_prefix=",can_prefix," var_field=",var_field," src_id=",src_id)
    
    if can_prefix % 2==0:
        #Can Control frame
        data_needed = False
        #fixme: process these frame properly

        if first_b & 0x7>=4 and first_b & 0x7<=7:
            print("CID Frame n°",first_b & 0x7," * ",hex(var_field),end=" * 0x")
            #full_ID = var_field << 12*((first_b&0x7) -4)
            if first_b&0x7==7:
                alias_neg = alias_negotiation(src_id)
            else:
                alias_neg = get_alias_neg_from_alias(src_id)
            alias_neg.next_step(var_field)
            list_alias_neg.append(alias_neg)
                
        elif first_b&0x7==0:
            if var_field==0x700:
                print("RID Frame * full ID=")#,hex(full_ID),end=" * ")
                jmri_identified = True   #FIXME
                neg = get_alias_neg_from_alias(src_id)
                reserve_aliasID(src_id)
                new_node(node(neg.fullID,True,neg.aliasID))
                
            elif var_field==0x701:
                print("AMD Frame",end=" * ")
                neg = get_alias_neg_from_alias(src_id)
                new_node(node(neg.fullID,True,neg.aliasID)) #JMRI node only for now
                reserve_aliasID(src_id)
                data_needed = True   #we could check the fullID
                
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
            
            if var_field==0x490:  #Verify node ID (global) FIXME
                for n in managed_nodes:
                    s.send((":X19170"+hexp(n.aliasID,3)+"N"+hexp(n.ID,12)+";").encode('utf-8'))
                    print("Sent---> :X19170"+hexp(n.aliasID,3)+"N"+hexp(n.ID,12)+";")
    
            elif var_field==0x828:#Protocol Support Inquiry
                dest_node_alias = int(msg[12:15],16)
                dest_node = find_managed_node(dest_node_alias)
                
                if dest_node is not None:
                    #FIXME: set correct bits
                    s.send((":X19668"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+hexp(SPSP|SNIP|CDIP,6)+"000000;").encode("utf-8"))
                    print("sent--->:X19668"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+hexp(SPSP|SNIP|CDIP,6)+"000000;")
            elif var_field == 0xDE8:#Simple Node Information Request

                dest_node_alias = int(msg[12:15],16)
                dest_node = find_managed_node(dest_node_alias)
                if dest_node is not None:
                    print("sent SNIR Reply")
                    #s.send((":X19A08"+hexp(gw_add.aliasID,3)+"N1"+hexp(src_id,3)+"04;").encode("utf-8"))#SNIR header
                    #print(":X19A08"+hexp(gw_add.aliasID,3)+"N1"+hexp(src_id,3)+"04;")
                    #FIXME:
                    send_fields(s,dest_node,0xA08,mfg_name_hw_sw_version,src_id)

                    #s.send((":X19A08"+hexp(gw_add.aliasID,3)+"N3"+hexp(src_id,3)+"02;").encode("utf-8"))#SNIR header
                    #print(":X19A08"+hexp(gw_add.aliasID,3)+"AAAN3"+hexp(src_id,3)+"02;")
                    #send_fields(0xA08,username_desc,src_id,True)
        elif (first_b & 0x7)>=2 and (first_b & 0x7)<=5: #Datagram
            address = int(msg[15:23],16)
            print("datagram!!")
            #for now we assume a one frame datagram
            dest_node_alias = int(msg[4:7],16)
            dest_node = find_managed_node(dest_node_alias)
            if dest_node is None:   #not for us
                print("Frame is not for us!!")
                #FIXME: we have to transmit it ??
                return
            src_node = find_node(src_id)

            if dest_node.current_write is not None:
                #if there is a write in progress then this datagram is part of it
                memory_write(s,dest_node,src_node,address,msg)
            elif msg[11:15]=="2043": #read command for CDI
                print("read command, address=",int(msg[15:23],16))
                s.send((":X19A28"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+";").encode('utf-8'))
                print("datagram received ok sent --->",(":X19A28"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+";").encode("utf-8"))
                send_CDI(s,dest_node,src_id,address)
            elif msg[11:13]=="20": #read/write command
                s.send((":X19A28"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+";").encode('utf-8'))
                print("datagram received ok sent --->",(":X19A28"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+";").encode("utf-8"))
                if msg[13]=="4":
                    memory_read(s,dest_node,src_node,address,msg)
                elif msg[13]=="0":
                    memory_write(s,dest_node,src_node,address,msg)

def poll_cmri():
    global cmri_test_client,last_poll

    if time.time()<last_time+20:
        #poll every 20 seconds FIXME
        return
    msg = cmri.CMRI_message(cmri.CMRI_message.POLL_M,1,b"")
    print("polling cmri test",msg.to_raw_message())
    cmri_test_client.send(msg.to_raw_message())

def process_cmri():
    global cmri_test_client

    #check if there is something to read FIXME
    ready_to_read = select.select([cmri_test_client],[],[],0)
    if ready_to_read:
        received = cmri_test_client.recv(200)
        print("cmri answer:",received)
        msg = cmri.CMRI_message.from_raw_message(received)
        print("msg=",msg.type_m,msg.address,msg.message)
        cmri_n = find_cmri_node_from_add(msg.address)
        cmri_n.set_outputs(msg.message[1])
        
    
#globals: fixme
cp_node=cpNode(1,0x020112AAAAAA)
cp_node.aliasID = 0xAAA    #FIXME negotiation not done yet
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
                             
cp_node.memory = {251:mem_space([(0,1),(1,63),(64,64)]),
          253:channels_mem}
cp_node.memory[251].set_mem(0,b"\1")
cp_node.memory[251].set_mem(1,b"gw1"+(b"\0")*(63-3))
cp_node.memory[251].set_mem(64,b"gateway-1"+(b"\0")*(64-9))
cp_node.memory[251].dump()
cp_node.memory[253].dump()

managed_nodes.append(cp_node)
new_node(cp_node)

cp_node=cpNode(1,0x020112AAABBB)
cp_node.aliasID = 0xBBB    #FIXME negotiation not done yet
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
                             
cp_node.memory = {251:mem_space([(0,1),(1,63),(64,64)]),
          253:channels_mem}
cp_node.memory[251].set_mem(0,b"\2")
cp_node.memory[251].set_mem(1,b"gw2"+(b"\0")*(63-3))
cp_node.memory[251].set_mem(64,b"gateway-2"+(b"\0")*(64-9))
cp_node.memory[251].dump()
cp_node.memory[253].dump()

managed_nodes.append(cp_node)
new_node(cp_node)
mfg_name_hw_sw_version=["\4python gateway","test","1.0","1.0","\2gw1","gateway-1"]

list_alias_neg=[]  #list of ongoing alias negotiations
reserved_aliases = {}  #dict alias--> fullID of reserved aliases

#for now: 1 can segment with all cmri nodes on it
cmri_nodes = cmri.load_cmri_cfg("cmri_cfg_test.txt")

input("waiting")
serv = openlcb_server.server("127.0.0.1",50000)
serv.start()

#cmri test server
cmri_test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
cmri_test_socket.bind(("127.0.0.1",50010))
cmri_test_socket.listen(5)
print("gateway-test-cmri listening on 127.0.0.1 at port ",50010,"waiting until connected to test prog")
print(select.select([cmri_test_socket],[],[]))
cmri_test_client,addr= cmri_test_socket.accept()
print("connected to cmri test!")
last_time = 0
# queue up to 5 requests

done = False
while not done:
    reads = serv.wait_for_clients()
    serv.process_reads(reads)
    for c in serv.clients:
        msg = c.next_msg(";")
        if msg and msg != ";":
            process_grid_connect(c,msg)
    process_cmri()
    #FIXME: take care of the non openlcb messages here
