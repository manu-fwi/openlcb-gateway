import time
import openlcb_nodes
from openlcb_debug import *

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
        wire_msg+=" "+hex_int(ord(CMRI_message.type_char[self.type_m]))+" "
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
            raw_msg += bytes((int(b,16),))
        return raw_msg
    
    @staticmethod
    def from_wire_message(msg):
        return CMRI_message.from_raw_message(CMRI_message.wire_to_raw_message(msg))

    @staticmethod
    def raw_to_wire_message(raw_msg):
        """
        transform the cmri raw message to its counter part on the wire (same format as cmri raw message except 
        all numbers are hexadecimal strings and space separated)
        """
        msg = ""
        for b in raw_msg:
            msg += hex_int(b)+" "
        #print("raw_to_wire=",msg,len(msg))
        return msg[:len(msg)-1]

class bits_list:
    """
    list of bits, two values per bits: first is current state, second is previous one
    """
    def __init__(self):
        self.bits_states=[]

    def build(self,nb_of_bits):
        self.bits_states = [[-1,-1] for i in range(nb_of_bits)]

    def set_bit(self,index,value): #set bit value and save previous one as last known state
        self.bits_states[index][1] = self.bits_states[index][0]
        self.bits_states[index][0]=value

    def __str__(self):
        res=""
        for bit in self.bits_states:
            res+=str(bit[0])+" "
        return res

    def has_changed(self): #returns True if one bit has a current state different from the previous state)
        for states in self.bits_states:
            if states[0]!=states[1]:
                return True
        return False

    def indices_of_changes(self):
        #returns a list of all indices of bits that have different current and previous states
        res = []
        for index in len(self.bits_states):
            if self.bits_states[index][0]!=self.bits_states[index][1]:
                res.append(index)
        return res

class inputs_list(bits_list):   #list of inputs states (current and last state)
    def __init__(self):
        super().__init__()

    def from_bytes(self,bytes_list): #set the inputs last state from a list of bytes (unpacks LSB first)
        index = 0
        for byte in bytes_list:
            for i in range(8):
                #saves current state as last state
                self.bits_states[index][1]=self.bits_states[index][0]
                #set current state
                self.bits_states[index][0] = (byte >> i)&1
                index+=1

class outputs_list(bits_list): #list of inputs states (current and last state)
    def __init__(self):
        super().__init__()

    def to_bytes(self): #pack the outputs last state to a list of bytes (unpacks LSB first) (returns a bytearray)
        index = 0
        res = bytearray()
        while index < len(self.bits_states):
            #new byte
            res.append(0)
            for i in range(8):
                #set bit in last byte
                res[-1] |= (self.bits_states[index][0] << i)
                index+=1
        return res
    
class CMRI_node:
    """
    represents a CMRI node
    The base class only has address and client (the client holds the connection to the external
    program providing the connection to the real bus
    """
    def __init__(self,address,read_period,client=None):
        self.address = address
        self.client = client
        self.last_poll = time.time()-self.read_period

    def read_inputs(self):  #returns True if poll has been sent or False otherwise
        #send poll to cpNode
        if time.time()<self.last_poll+CPNode.read_period:
            return False
        self.last_poll=time.time()
        debug("sending poll to cpNode (add=",self.address,")")
        cmd = CMRI_message(CMRI_message.POLL_M,self.address,b"")
        if self.client is not None:
            self.client.queue(cmd.to_wire_message().encode('utf-8'))
        return True
    

class CPNode (CMRI_node):
    total_IO = 16
    read_period = 1 #in seconds
    IOX_max = 16   #max number of IO ports (*8 to get max number of IO lines)

    @staticmethod
    def decode_nb_inputs(cpn_type):
        if cpn_type==0:
            return 6
        elif cpn_type==1:
            return 8
        elif cpn_type==2:
            return 8
        elif cpn_type==3:
            return 4
        elif cpn_type==4:
            return 16
        elif cpn_type==5:
            return 0
        elif cpn_type==6:
            return 5
        elif cpn_type==7:
            return 4

        debug("Unknown cpnode I/O configuration")
        return None
    
    def __init__(self,address,nb_I,client=None):
        super().__init__(address,CPNode.read_period,client)
        self.nb_I = nb_I
        self.IOX=[0]*16   #16 boards max
        self.last_input_read = time.time() #timestamp used to trigger a periodic input read
        #inputs states pair (first is current state, second is last state)
        #state = -1: never polled
        self.inputs=inputs_list()
        self.inputs.build(nb_I)
        self.inputs_IOX = inputs_list()
        #outputs states (first is desired state, second is last known state)
        #state=-1: never been set: FIXME do we need this?
        self.outputs=outputs_list()
        self.outputs.build(CPNode.total_IO-nb_I)
        self.outputs_IOX=outputs_list()
        self.last_poll = time.time()-CPNode.read_period
        self.last_receive = time.time()-CPNode.read_period
        self.client = client

    def __str__(self):
        res = "CPNode,bus="+str(self.bus)+",add="+str(self.address)+",NB I="+str(self.nb_I)
        if len(self.IOX)>0:
            for i in range(len(self.IOX)):
                res += "<>IOX["+str(i)+"]="+str(self.IOX[i])+" I/"+str(8-self.IOX[i])+" O"
        return res

    def nb_IOX_inputs(self):
        res = 0
        for i in self.IOX:
            if i==2:
                res += 8
        return res 
    
    def nb_IOX_outputs(self):
        res = 0
        for i in self.IOX:
            if i==1:
                res += 8
        return res
    
    def build_IOX(self):
        debug(self.IOX)
        for i in range(len(self.IOX)):
            if self.IOX[i]==1:
                self.outputs_IOX.extend([[0,-1] for k in range(8)])
            elif self.IOX[i]==2:
                self.inputs_IOX.extend([[-1,-1] for k in range(8)])  #extend bits array
        
    def process_receive(self,msg):
        debug("process receive=",msg.message)
        message=msg.message
        index = 0
        n = 0
        while n < self.nb_I and index <=1:
            new_value = (message[index] >> (n%8))&0x01
            #only register the new value if its different from the current one
            if new_value != self.inputs[n][0]:
                self.inputs[n][1] = self.inputs[n][0]  #current value becomes last value
                self.inputs[n][0] = new_value
            n+=1
            if n % 8==0:
                index +=1 #next byte
        index = 2
        n=0
        while n<self.nb_IOX_inputs() and index < len(message):
            self.inputs_IOX[n][1] = self.inputs_IOX[n][0]  #current value becomes last value
            self.inputs_IOX[n][0] = (message[index] >> (n%8))&0x01
            n+=1
            if n % 8==0:
                index +=1 #next byte
        if n<self.nb_IOX_inputs():
            debug("Error: number of inputs in Receive message not corresponding to setup")
            
    def write_outputs(self,filename,save=True):
        #send outputs to node
        bytes_value = self.outputs.to_bytes()
        if len(bytes_value)==1:
            bytes_value+=b"\0"
        first_bit = 0
        for i in self.IOX:
            if i==1:
                bits = [io[0] for io in self.outputs_IOX[first_bit:first_bit+8]]
                #bytes_value+=bytearray((CPNode.pack_bits(bits),)) FIXME
                debug("(",i,") bytes=",bytes_value)
                first_bit += 8
        debug("bytes_value",bytes_value)
        if self.client is not None:
            cmd = CMRI_message(CMRI_message.TRANSMIT_M,self.address,bytes_value)
           self.client.queue(cmd.to_wire_message().encode('utf-8'))
        #fixme do we need this?
        for io in self.outputs:
            io[1]=io[0]  #value has been sent so sync last known value to that
        for i in self.IOX:
            if i==1:
                for io in self.outputs_IOX[first_bit:first_bit+8]:
                    io[1]=io[0]
                    first_bit+=8
        #save outputs states to file
        if save:
            with open(filename,"w") as file:
                for io in self.outputs:
                    file.write(str(io[0])+" ")
                file.write('\n')
                first_bit=0
                for i in self.IOX:
                    if i==1:
                        for iox in self.outputs_IOX[first_bit:first_bit+8]:
                            file.write(str(iox[0])+" ")
                        file.write('\n')
                        first_bit+=8

    def load_outputs(self,filename):
        debug("loading outputs from file",filename)
        exists=True
        try:
            file = open(filename,"r")
        except IOError:
            exists=False
        if exists:
            line = file.readline()
            index = 0
            for i in line.split():
                if index==CPNode.total_IO - self.nb_I:
                    debug("Too many outputs values in the file",filename)
                    break
                self.outputs[index][0]=int(i)
                index+=1
            if index<CPNode.total_IO - self.nb_I:
                debug("Not enough outputs values in the file",filename)
            if file:
                line = file.readline()
                index = 0
                for i in line.split():
                    if index==self.nb_IOX_outputs():
                        debug("Too many outputs values in the file",filename)
                        break
                    self.outputs_IOX[index][0]=int(i)
                    index+=1
                if index<self.nb_IOX_outputs():
                    debug("Not enough outputs values in the file",filename)
            debug(self.outputs)
            debug(self.outputs_IOX)
            file.close()
            
    def set_output(self,index_out,value):
        if index_out<CPNode.total_IO - self.nb_I:
            self.outputs[index_out][0]=value
        else:
            debug("output index out of range")

    def set_output_IOX(self, index_out,value):
        if index_out<self.nb_IOX_outputs():
            debug("setoutputIOX(",index_out,",",value,")")
            self.outputs_IOX[index_out][0]=value
        else:
            debug("IOX output index out of range")    

    def get_IO_nb(self):
        res = CPNode.total_IO
        for IO in self.IOX:
            if IO>0:
                res+=8
        return res

#
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

def decode_cpnode_cfg(args_list):
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


def split_args(msg):
    """
    splits the msg in args (strings must be quoted)
    """
    beg = msg.find('"')
    args = msg[:beg-1].split(' ')  #split the args before the first "
    end = msg.find('"',beg+1)  #find next "
    args.append(msg[beg+1:end]) #get the string without the "
    beg = msg.find('"',end+1)
    end = msg.find('"',beg+1)
    args.append(msg[beg+1:end]) #get the string without the "
    args.extend(msg[end+2:].split(' '))  #make sure we go pass the next space after the last "
    return args

def load_cmri_cfg(client,filename):
    with open(filename) as f:
        line = f.readline()
        while line!='':
            print("line=",line)
            if (line.lstrip())[0]!="#":  #only process uncommented line
                if line == '':
                    return
                args = split_args(line)
                print("args=",args)
                cpnode = decode_cpnode_cfg(args[4:])
                if cpnode is not None:
                    cpnode.client = client
                    node = openlcb_nodes.Node_cpnode(int(args[0],16))    #full ID (Hex)
                    node.cp_node = cpnode
                    node.create_memory()
                    node.set_mem(251,0,bytes((int(args[1],16),)))
                    node.set_mem(251,1,args[2].encode('utf-8')+(b"\0")*(63-len(args[2])))
                    node.set_mem(251,64,args[3].encode('utf-8')+(b"\0")*(64-len(args[3])))
                    node.set_mem(253,0,bytes((cpnode.address,)))
                    client.managed_nodes.append(node)
            line = f.readline()


class SUSIC(CMRI_node):
    read_period = 1 #in seconds
    
    def __init__(self,address,node_type,cards_sets,client=None):
        super().__init__(address,CMRI_SUSIC.read_period,client)
        self.cards_sets = cards_sets
        self.node_type = node_type
        self.build_bits_states()
        
    def build_bits_states(self):
        if self.node_type=="N":
            nb_bits_per_card=24
        elif self.node_type=="X":
            nb_bits_per_card=32
        nb_inputs=0
        nb_outputs=0
        for c in self.cards_sets:
            nb_inputs+=bit_value(c,0) + bit_value(c,2) + bit_value(c,4)+bit_value(c,6)
            nb_outputs+=bit_value(c,1) + bit_value(c,3) + bit_value(c,5)+bit_value(c,7)
        self.inputs = inputs_list()
        self.inputs.build(nb_bits_per_card*nb_inputs)
        self.outputs = outputs_list()
        self.outputs.build(nb_bits_per_card*nb_outputs)

    def write_outputs(self,filename,save=True):
        if self.client is not None:
            cmd = CMRI_message(CMRI_message.TRANSMIT_M,self.address,bytes_value)
            self.client.queue(cmd.to_wire_message().encode('utf-8'))
        
        #save outputs states to file
        if save:
            with open(filename,"w") as file:
                file.write(str(self.outputs))
                
    def load_outputs(self,filename):
        debug("loading outputs from file",filename)
        exists=True
        try:
            file = open(filename,"r")
        except IOError:
            exists=False
        if exists:
            line = file.readline()
            index = 0
            for i in line.split():
                if index==len(self.outputs):
                    debug("Too many outputs values in the file",filename)
                    break
                self.outputs[index][0]=int(i)
                index+=1
            if index<len(self.outputs):
                debug("Not enough outputs values in the file",filename)
            debug(self.outputs)
            debug(self.outputs_IOX)
            file.close()

    def process_receive(self,msg):
        debug("process receive=",msg.message)
        message=msg.message
        index = 0
        n = 0
        while n < len(self.inputs.bits_states) and index < len(message):
            new_value = (message[index] >> (n%8))&0x01
            #only register the new value if its different from the current one
            if new_value != self.inputs[n][0]:
                self.inputs.set_bit(n,new_value)
            n+=1
            if n % 8==0:
                index +=1 #next byte

        if n<len(self.intputs.bits_states):
            debug("Error: number of inputs in Receive message not corresponding to setup")

def hex_int(i):   #same as hex but withouth the leading "0x"
    return hex(i)[2:] 

def bit_value(c,bit_n):
    return (c & (1 << bit_n)) >> bit_n

