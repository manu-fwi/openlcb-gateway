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
    
    def __init__(self):
        self.type_m = None

    def __str__(self):
        if self.type_m !=None:
            return "add="+str(self.address)+" type="+str(CMRI_message.type_char[self.type_m])+" mess="+self.message.decode('utf-8')
        return "invalid message"

    @staticmethod
    def from_message(type_m,address,message):
        mess = CMRI_message()
        mess.type_m = type_m
        mess.address = address
        mess.message = message
        return mess
        
    @staticmethod     
    def from_raw_message(raw_mess):
        mess = CMRI_message()
        if raw_mess[:3]!=bytes((CMRI_message.SYN,CMRI_message.SYN,CMRI_message.STX)) or raw_mess[len(raw_mess)-1]!=CMRI_message.ETX:
            return
        if raw_mess[4]==ord("I"):
            mess.type_m = CMRI_message.INIT_M
        elif raw_mess[4]==ord("P"):
            mess.type_m = CMRI_message.POLL_M
        elif raw_mess[4]==ord("T"):
            mess.type_m = CMRI_message.TRANSMIT_M
        elif raw_mess[4]==ord("R"):
            mess.type_m = CMRI_message.RECEIVE_M
        print(mess.type_m)
        if mess.type_m == None :
            mess.type_m = None
            return
        mess.address = CMRI_message.UA_to_add(raw_mess[3])
        if mess.address < 0 or mess.address>127:
            mess.type_m = None
            return
        DLE_char = False
        message = b""
        for b in raw_mess[5:len(raw_mess)-1]:
            if DLE_char:
                message += bytes((b,))
                DLE_char = False
            else:
                if b == CMRI_message.DLE:
                    DLE_char = True
                else:
                    if b==CMRI_message.ETX or b==CMRI_message.STX:
                        mess.type_m = None
                        break
                    message += bytes((b,))
                   
        if raw_mess[len(raw_mess)-1]!=CMRI_message.ETX:
            mess.type_m = None
        else:
            mess.message = message
        return mess

    def to_raw_message(self):
        if self.type_m == None:
            return b""
        raw_message = bytes((CMRI_message.SYN,CMRI_message.SYN,CMRI_message.STX,CMRI_message.add_to_UA(self.address)))
        raw_message += CMRI_message.type_char[self.type_m]
        for b in self.message:
            raw_message += CMRI_message.encode_byte(b)
        return raw_message + bytes((CMRI_message.ETX,))

            
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
    
class CMRI_node:
    
    def __init__(self,address,bus):
        self.address = address
        self.bus = None

class CPNode (CMRI_node):
    total_IO = 16
    read_period = 500 #in ms
    def __init__(self,address,bus,nb_I):
        super().__init__(address,bus)
        self.nb_I = nb_I
        self.IOX=[]
        self.last_input_read = time.time() #timestamp used to trigger a periodic input read
        #inputs states pair (first is current state, second is last state)
        #state = -1: never polled
        self.inputs=[[-1,-1] for i in range(nb_I)]
        self.inputs_IOX = []
        #outputs states (first is desired state, second is last known state)
        #state=-1: never been set
        self.outputs=[[-1,-1] for i in range(CPNode.total_IO-nb_I)]
        self.outputs_IOX=[]

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
                    self.outputs_IOX.extend([[-1,-1] for i in range(8)])
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

    def read_inputs(self):
        #send poll to cpNode
        print("sending poll to cpNode (add=",self.address,")")
        cmd = CMRI_message.from_message(CMRI_message.POLL_M,self.address,b"")
        raw_cmd = cmd.to_raw_message()
        if self.bus!=None:
            self.bus.send(raw_cmd)
        else:
            print("send to bus ",raw_cmd)

    def process_receive(self,message): #message must have been cleaned up (no SYN STX/ETX or DLE)
        index = 0
        n = 0
        while n < self.nb_I and index <2:
            print("message=",message[index],"n=",n," index = ",index, "v=",(message[index] >> (n%8))&0x01)
            self.inputs[n][1] = self.inputs[n][0]  #current value becomes last value
            self.inputs[n][0] = (message[index] >> (n%8))&0x01
            n+=1
            if n % 8==0:
                index +=1 #next byte
        index = 2
        n=0
        while n<self.nb_IOX_inputs() and index < len(message):
            #print("message=",message[index],"n=",n," index = ",index, "v=",(message[index] >> (n%8))&0x01)
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
        bytes = CPNode.pack_bits(bits)
        if len(bytes)==1:
            bytes+=b"\0"
        first_bit = 0
        print(self.IOX)
        for i in self.IOX:
            if i==-1:
                bytes += b"\0"
            elif i==0:
                bits = [io[0] for io in self.outputs_IOX[first_bit:first_bit+8]]
                bytes+=CPNode.pack_bits(bits)
                print(i," bytes=",bytes)
        cmd = CMRI_message.from_message(CMRI_message.TRANSMIT_M,self.address,bytes)
        raw_cmd = cmd.to_raw_message()
        if self.bus!=None:
            self.bus.send(raw_cmd)
        else:
            print("send to bus ",raw_cmd)
        

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
        res = bytearray(b"")
        j = 0
        for i in bits_list:
            if j%8 == 0:
                res += b"\0"
            res[j//8] = (res[j//8] << 1) | i
            print("j=",j,"i=",i,"res=",res)
            j+=1
        return res

#
#Reads the config file
#Format (space separated):
# CMRI node's bus number (FIXME: need to be more precise)
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

def load_cmri_cfg(filename):
    cmri_nodes=[]
    with open(filename) as f:
        line = f.readline()
        while line!='':
            print("line=",line)
            if line == '':
                return
            args = line.split(' ')
            if args[2]=='C':
                if int(args[3])==0:
                    new = CPNode(int(args[1]),int(args[0]),6)
                elif int(args[3])==1:
                    new = CPNode(int(args[1]),int(args[0]),8)
                elif int(args[3])==2:
                    new = CPNode(int(args[1]),int(args[0]),8)
                elif int(args[3])==3:
                    new = CPNode(int(args[1]),int(args[0]),4)
                elif int(args[3])==4:
                    new = CPNode(int(args[1]),int(args[0]),16)
                elif int(args[3])==5:
                    new = CPNode(int(args[1]),int(args[0]),0)
                elif int(args[3])==6:
                    new = CPNode(int(args[1]),int(args[0]),5)
                elif int(args[3])==7:
                    new = CPNode(int(args[1]),int(args[0]),4)
                else:
                    print("Unknown pin config!")
                    #fixme: error handling
                    return
                for i in range(4,len(args)):
                    new.decode_IOX(args[i])
                cmri_nodes.append(new)
            else:
                print("Node type not managed")
            line = f.readline()
    return cmri_nodes