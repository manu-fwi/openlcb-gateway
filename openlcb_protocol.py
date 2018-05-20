from openlcb_debug import *

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

class Frame:
    @staticmethod
    def build_verified_nID(src_node,simple_proto):
        if simple_proto:
            res = Frame(src_node,None,0x19171)
        else:
            res = Frame(src_node,None,0x19170)
        res.data=src_node.ID.to_bytes(6,byteorder='big')
        return res
    @staticmethod
    def build_PCER(src_node,ev):
        res = Frame(src_node,None,0x195B4)
        res.data = ev
        return res
                    
    def __init__(self,src_node,dest_node,header):
        self.src = src_node
        self.dest = dest_node
        self.header = header
        
    def add_data(self,bytes_arr):
        self.data = bytes_arr   #data is a byte array, no more than 8 bytes!

    def to_gridconnect(self):
        res=":X"+hexp(self.header,5)+hexp(self.src.aliasID,3)+"N"
        res+=convert_to_hex_b(self.data)+";"
        return res.encode('utf-8')
    
class Addressed_frame(Frame):
    ONE = 0
    FIRST = 1
    MIDDLE = 3
    LAST = 2
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
    
class Datagram_content(Frame):
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
        

class Datagram_rcv(Frame):
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
        l = [Datagram_content(src,dest,Datagram_content.ONE)]
        l[0].add_data(data)
        return l
    pos = 0
    l=[Datagram_content(src,dest,Datagram_content.FIRST)]
    l[0].add_data(data[:8])
    pos = 8
    while pos < len(data):
        if pos+8 < len(data):
            datagram_pos = Datagram_content.MIDDLE
        else:
            datagram_pos = Datagram_content.LAST
        d = Datagram_content(src,dest,datagram_pos)
        d.add_data(data[pos:pos+8])
        pos+=8
        l.append(d)
    return l

def create_addressed_frame_list(src,dest,MTI,data,pad_last=False):  #data is the payload, no more than 64 bytes!
    if len(data)<=6:
        l = [Addressed_frame(src,dest,Addressed_frame.ONE,MTI)]
        l[0].add_data(data)
        return l
    l=[Addressed_frame(src,dest,Addressed_frame.FIRST,MTI)]
    l[0].add_data(data[:6])
    pos = 6
    while pos < len(data):
        if pos+6 < len(data):
            frame_pos = Addressed_frame.MIDDLE
        else:
            frame_pos = Addressed_frame.LAST
        d = Addressed_frame(src,dest,frame_pos,MTI)
        if frame_pos==3 and pos+6>len(data) and pad_last:
            d.add_data(data[pos:len(data)]+bytearray([0]*(pos+6-len(data))))
        else:
            d.add_data(data[pos:pos+6])
        debug("data=",d.data)
        pos+=6
        l.append(d)
    return l

def data_from_dgram_list(dgram_l):
    l = b""
    for d in dgram_l:
        l += d.data
    return l

class Event:

    @staticmethod
    def from_str(s):  #from a hex dotted notation xx.xx.xx.xx.xx.xx.xx.xx
        if s=="None":
            return Event(b"\0"*8)
        l = s.split(".")
        if len(l)!=8:
            debug("Malformed event")
            return None
        ev = b""
        for i in l:
            ev+=bytes((int(i,16),))
        return Event(ev)
    
    def __init__(self,id):  #id is a 8 bytes array
        self.id = id

    def automatically_routed(self):
        return self.id[0]==0 and self.id[1]==0
    
    def __str__(self):
        if self.id == None:
            return "0."*7+"0"
        s=""
        for i in self.id:
            s+=hexp(i,2)+"."
        return s[:len(s)-1]
    
class Alias_negotiation:
    """
    This class holds information on an ongoing alias ID reservation
    """
    def __init__(self,alias):
        self.aliasID = alias   #alias being reserved
        self.fullID=0          #partial or complete full ID 
        self.step=0            #current step 0:nothing yet, 1-4:  each CID step and 5 means reserved
    def next_step(self,fullID_part):
        self.fullID <<= 12
        self.fullID+=fullID_part
        self.step+=1
    def reserve(self):
        if self.step<4:
            debug("Reserve alias=",self.aliasID," before all CID received (",self.step,")")
            return False
        self.step = 5
        return True

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
