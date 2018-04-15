import time

class CMRI_message:
    SYN=0xFF
    STX=0x02
    ETX=0x03
    DLE=0x10
    type_char=[b"I",b"P",b"T",b"R"]
    INIT_M = 0
    POLL_M = 1
    TRANSMIT_M = 2
    RECEIVE_M = 3
    add_offset=65
    
    def __init__(self,type_m=None,address=None,message=None):
        self.type_m = type_m
        self.address = address
        self.message = message

#    def __str__(self):
#        if self.type_m !=None:
#            return "add="+str(self.address)+" type="+str(CMRI_message.type_char[self.type_m])+" mess="+self.message.decode('utf-8')
#        return "invalid message"
        
    @staticmethod     
    def from_raw_message(raw_msg):
        msg = CMRI_message()
        if raw_msg[:3]!=bytes((CMRI_message.SYN,CMRI_message.SYN,CMRI_message.STX)) or raw_msg[len(raw_msg)-1]!=CMRI_message.ETX:
            print("malformed CMRI message!!")
            return
        if raw_msg[4]==ord("I"):
            msg.type_m = CMRI_message.INIT_M
        elif raw_msg[4]==ord("P"):
            msg.type_m = CMRI_message.POLL_M
        elif raw_msg[4]==ord("T"):
            msg.type_m = CMRI_message.TRANSMIT_M
        elif raw_msg[4]==ord("R"):
            msg.type_m = CMRI_message.RECEIVE_M
        print("message received",msg.type_m)
        if msg.type_m == None :
            msg.type_m = None
            return
        msg.address = CMRI_message.UA_to_add(raw_msg[3])
        if msg.address < 0 or msg.address>127:
            msg.type_m = None
            return
        DLE_char = False
        message = b""
        for b in raw_msg[5:len(raw_msg)-1]:
            if DLE_char:
                message += bytes((b,))
                DLE_char = False
            else:
                if b == CMRI_message.DLE:
                    DLE_char = True
                else:
                    if b==CMRI_message.ETX or b==CMRI_message.STX:
                        msg.type_m = None
                        break
                    message += bytes((b,))
                   
        msg.message = message
        return msg

    def to_raw_message(self):
        if self.type_m == None:
            return b""
        raw_message = bytes((CMRI_message.SYN,CMRI_message.SYN,CMRI_message.STX,CMRI_message.add_to_UA(self.address)))
        raw_message += CMRI_message.type_char[self.type_m]
        for b in self.message:
            raw_message += CMRI_message.encode_byte(b)
        return raw_message + bytes((CMRI_message.ETX,))

    def to_wire_message(self):
        if self.type_m == None:
            return ""
        wire_msg = (hex_int(CMRI_message.SYN)+" ")*2+hex_int(CMRI_message.STX)+" "+hex_int(CMRI_message.add_to_UA(self.address))
        wire_msg+=" "+CMRI_message.type_char[self.type_m].decode('utf-8')+" "
        for b in self.message:
            wire_msg += hex_int(b)+" "
        wire_msg += hex_int(CMRI_message.ETX)
        return wire_msg

    @staticmethod
    def find_ETX(msg):  #find the ETX char pos in the message, point right after the end of msg if not found
        DLE_char = False
        for pos in range(len(msg)):
            if DLE_char:
                DLE_char = False
            else:
                if msg[pos]==CMRI_message.ETX:
                    return pos
                if msg[pos]==CMRI_message.DLE:
                    DLE_char = True
        return len(msg)
    
    @staticmethod        
    def encode_byte(b):
        if b==CMRI_message.STX or b == CMRI_message.ETX or b == CMRI_message.DLE:
            return bytes((CMRI_message.DLE,b))
        else:
            return bytes((b,))
            
    @staticmethod
    def add_to_UA(address):
        return address+CMRI_message.add_offset
    
    @staticmethod
    def UA_to_add(UA):
        return UA-CMRI_message.add_offset

    @staticmethod
    def wire_to_raw_message(msg):
        """
        decode the cmri message gotten from the wire (same format as cmri raw message except 
        all numbers are hexadecimal strings and space separated)
        transform it as a raw msg
        """
        raw_msg = b""
        byte_list = msg.split(' ')
        for b in byte_list:
            raw_msg += int(b,16)
        return raw_msg
    
    @staticmethod
    def from_wire_message(msg):
        return from_raw_message(wire_to_raw_message(msg))

    @staticmethod
    def raw_to_wire_message(raw_msg):
        """
        transform the cmri raw message to its counter part on the wire (same format as cmri raw message except 
        all numbers are hexadecimal strings and space separated)
        """
        msg = ""
        for b in raw_msg:
            msg += hex_int(b)+" "
        return msg[:len(msg)-1]
    
class CMRI_node:
    """
    represents a CMRI node
    The base class only has address and client (the client holds the connection to the external
    program providing the connection to the real bus
    """
    def __init__(self,address,client=None):
        self.address = address
        self.client = client

class CPNode (CMRI_node):
    total_IO = 16
    read_period = 10 #in seconds
    def __init__(self,address,nb_I,client=None):
        super().__init__(address)
        self.nb_I = nb_I
        self.IOX=[]
        self.last_input_read = time.time() #timestamp used to trigger a periodic input read
        #inputs states pair (first is current state, second is last state)
        #state = -1: never polled
        self.inputs=[[-1,-1] for i in range(nb_I)]
        self.inputs_IOX = []
        #outputs states (first is desired state, second is last known state)
        #state=-1: never been set
        self.outputs=[[0,-1] for i in range(CPNode.total_IO-nb_I)]
        self.outputs_IOX=[]
        self.last_poll = time.time()-CPNode.read_period
        self.last_receive = time.time()-CPNode.read_period

    def __str__(self):
        res = "CPNode,bus="+str(self.bus)+",add="+str(self.address)+",NB I="+str(self.nb_I)
        if len(self.IOX)>0:
            for i in range(len(self.IOX)):
                res += "<>IOX["+str(i)+"]="+str(self.IOX[i])+" I/"+str(8-self.IOX[i])+" O"
        return res

    def nb_IOX_inputs(self):
        res = 0
        for i in self.IOX:
            if i>0:
                res += i
        return res
    
    def nb_IOX_outputs(self):
        res = 0
        for i in self.IOX:
            if i==0:
                res+=8
        return res
    
    def add_IOX(self,IO):
        for i in range(len(IO)):
            if IO[i]!=-1:
                IO[i] <<= 3   #x8 because each element is the nb of inputs: 8 or 0
                if IO[i]>0:
                    self.inputs_IOX.extend([[-1,-1] for i in range(8)])  #extend bits array
                else:
                    self.outputs_IOX.extend([[0,-1] for i in range(8)])
        self.IOX.extend(IO)
        
    def decode_IOX(self,IO):
        print("decoding IOX",IO)
        
        a = [int(io) for io in IO.split(',')]
        if len(a)!=2:
            print("bad IOX")
        else:
            if (abs(a[0])!=1 and a[0]!=0) or (abs(a[1])!=1 and a[1]!=0):
                print("bad IOX")
            else:
                self.add_IOX(a)

    def read_inputs(self):  #returns True if poll has been sent or False otherwise
        #send poll to cpNode
        if time.time()<self.last_poll+CPNode.read_period:
            return False
        self.last_poll=time.time()
        print("sending poll to cpNode (add=",self.address,")")
        cmd = CMRI_message(CMRI_message.POLL_M,self.address,b"")
        if self.client!=None:
            self.client.queue(cmd)
        return True

    def process_receive(self,msg):
        message=msg.message
        index = 1
        n = 0
        while n < self.nb_I and index <=2:
            print("message=",message[index],"n=",n," index = ",index, "v=",(message[index] >> (n%8))&0x01)
            self.inputs[n][1] = self.inputs[n][0]  #current value becomes last value
            self.inputs[n][0] = (message[index] >> (n%8))&0x01
            n+=1
            if n % 8==0:
                index +=1 #next byte
        index = 3
        n=0
        while n<self.nb_IOX_inputs() and index < len(message):
            print("message=",message[index],"n=",n," index = ",index, "v=",(message[index] >> (n%8))&0x01)
            self.inputs_IOX[n][1] = self.inputs_IOX[n][0]  #current value becomes last value
            self.inputs_IOX[n][0] = (message[index] >> (n%8))&0x01
            n+=1
            if n % 8==0:
                index +=1 #next byte
        if n<self.nb_IOX_inputs():
            print("Error: number of inputs in Receive message not corresponding to setup")
            
    def write_outputs(self):
        #send outputs to node
        bits = [io[0] for io in self.outputs]
        bytes_value = CPNode.pack_bits(bits)
        if len(bytes_value)==1:
            bytes_value+=b"\0"
        first_bit = 0
        for i in self.IOX:
            if i==-1:
                bytes_value += b"\0"
            elif i==0:
                bits = [io[0] for io in self.outputs_IOX[first_bit:first_bit+8]]
                bytes_value+=CPNode.pack_bits(bits)
                print(i," bytes=",bytes_value)
        cmd = CMRI_message(CMRI_message.TRANSMIT_M,self.address,bytes_value)
        if self.client!=None:
            self.client.queue(cmd)
        for io in self.outputs:
            io[1]=io[0]  #value has been sent so sync last known value to that
        for i in self.IOX:
            if i==0:
                for io in self.outputs_IOX[first_bit:first_bit+8]:
                    io[1]=io[0]

    def set_output(self,index_out,value):
        if index_out<CPNode.total_IO - self.nb_I:
            self.outputs[index_out][0]=value
        else:
            print("output index out of range")

    def set_output_IOX(self, index_out,value):
        if index_out<self.nb_IOX_outputs():
            self.outputs_IOX[index_out][0]=value
        else:
            print("IOX output index out of range")    

    def get_IO_nb(self):
        res = CPNode.total_IO
        for IO in self.IOX:
            if IO!=-1:
                res+=8
        return res

    @staticmethod
    def pack_bits(bits_list): #will pack a list of bit values as a list of bytes, MSB is first bit and so on
        res = bytearray(b"\0\0")
        j = 0
        for i in bits_list:
            print("aavant j=",j,"i=",i,"res=",res)            
            res[j//8] = (res[j//8] << 1) | i
            print("apres j=",j,"i=",i,"res=",res)
            j+=1
        return res

#
#Reads the config file
#Format (space (ONE only) separated):
# CMRI node's address followed by the node type (N,X,C)
# (FIXME):for now only C is allowed
#   For C type:
#      next is the I/O config:
#            0 -> 10 O / 6 I(BASE_NODE)
#            1 -> 8 I/8 O (BASE_NODE_8IN8OUT)
#            2 -> 8 O/8 I (BASE_NODE_8OUT8IN)
#            3-> 12 O/4 I (BASE_NODE_12OUT4IN)
#            4 -> 16I     (BASE_NODE_16IN)
#            5 -> 16 O    (BASE_NODE_16OUT)
#            6 -> 11 O / 5 I (BASE_NODE_RSMC)
#            7 -> 12 O / 4 I (BASE_NODE_RSMC_LOCK)
#      next is the IOX config: a list of space separated pairs of numbers (0=OUTPUT, 1=INPUT, -1=Not assigned)
#                          ex: 0,0 0,1 0,-1
#

def decode_cmri_node_cfg(args_list):
    node = None
    print(args_list)
    if args_list[1]=='C':
        if int(args_list[2],16)==0:
            node = CPNode(int(args_list[0],16),6)
        elif int(args_list[2],16)==1:
            node = CPNode(int(args_list[0],16),8)
        elif int(args_list[2],16)==2:
            node = CPNode(int(args_list[0],16),8)
        elif int(args_list[2],16)==3:
            node = CPNode(int(args_list[0],16),4)
        elif int(args_list[2],16)==4:
            node = CPNode(int(args_list[0],16),16)
        elif int(args_list[2],16)==5:
            node = CPNode(int(args_list[0],16),0)
        elif int(args_list[2],16)==6:
            node = CPNode(int(args_list[0],16),5)
        elif int(args_list[2],16)==7:
            node = CPNode(int(args_list[0],16),4)
        else:
            print("Unknown pin config!")
            #fixme: error handling
            return
        for i in range(3,len(args_list)):
            node.decode_IOX(args_list[i])
    else:
        print("Node type not managed")
    return node

def load_cmri_cfg(filename):
    nodes=[]
    with open(filename) as f:
        line = f.readline()
        while line!='':
            print("line=",line)
            if (line.lstrip())[0]!="#":  #only process uncommented line
                if line == '':
                    return
                args = line.split(' ')
                node = decode_cmri_node_cfg(args)
                if node is not None:
                    nodes.append(node)
            line = f.readline()
    return nodes
def hex_int(i):   #same as hex but withouth the leading "0x"
    return hex(i)[2:] 
