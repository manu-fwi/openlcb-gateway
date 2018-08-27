from openlcb_cmri_cfg.py import hex_int
from openlcb_protocol import *
from openlcb_debug import *
import openlcb_config

class RR_duino_message:
    BEG=0xFF
    #command byte special bits positions
    CMD_ANSW_BIT = 0
    CMD_LAST_ANSW_BIT=1
    CMD_ASYNC_BIT=2
    #address byte special bits positions
    ADD_LIST_BIT=6
    
    def __init__(self,raw_message=None):
        self.raw_message = raw_message

    def get_address():
        return self.raw_message[2] & 0x3F

    def is_answer():
        #return True if this message is an answer from the device
        return (self.raw_message[1] & (1 << CMD_ANSW_BIT))==0
    
    def last_answer():
        #return True if this message is the last answer (used mainly by show commands/async events reporting)
        return (self.raw_message[1] & (1 << CMD_LAST_ANSW_BIT))==0
    
    def async_events_pending():
        #return True if this message indicates that there are async events waiting to be sent
        #by the device
        return (self.raw_message[1] & (1 << CMD_ASYNC_BIT))!=0
    
    def is_list():
        #return True if message is a list (of sensors/turnouts)...
        return (self.raw_message[2] & (1 << ADD_LIST_BIT))!=0

    def to_wire_message(self):
        if self.raw_message == None:
            return ""
        for b in self.raw_message:
            wire_msg += hex_int(b)+" "

        return wire_msg

    @staticmethod
    def wire_to_raw_message(msg):
        """
        decode the message gotten from the wire (same format as cmri raw message except 
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
        return RR_duino_message(RR_duino_message.wire_to_raw_message(msg))
    
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
    read_period = 2 #in seconds
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
        super().__init__(address)
        self.nb_I = nb_I
        self.IOX=[0]*16   #16 boards max
        self.last_input_read = time.time() #timestamp used to trigger a periodic input read
        #inputs states pair (first is current state, second is last state)
        #state = -1: never polled
        self.inputs=[[-1,-1] for i in range(nb_I)]
        self.inputs_IOX = []
        #outputs states (first is desired state, second is last known state)
        #state=-1: never been set: FIXME do we need this?
        self.outputs=[[0,-1] for i in range(CPNode.total_IO-nb_I)]
        self.outputs_IOX=[]
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
                   
        
    def read_inputs(self):  #returns True if poll has been sent or False otherwise
        #send poll to cpNode
        if time.time()<self.last_poll+CPNode.read_period:
            return False
        self.last_poll=time.time()
        debug("sending poll to cpNode (add=",self.address,")")
        cmd = CMRI_message(CMRI_message.POLL_M,self.address,b"")
        if self.client is not None:
            self.client.queue(cmd)
        return True

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
        bits = [io[0] for io in self.outputs]
        bytes_value = bytearray((CPNode.pack_bits(bits),))
        if len(bytes_value)==1:
            bytes_value+=b"\0"
        first_bit = 0
        for i in self.IOX:
            if i==1:
                bits = [io[0] for io in self.outputs_IOX[first_bit:first_bit+8]]
                bytes_value+=bytearray((CPNode.pack_bits(bits),))
                debug("(",i,") bytes=",bytes_value)
                first_bit += 8
        debug("bytes_value",bytes_value)
        cmd = CMRI_message(CMRI_message.TRANSMIT_M,self.address,bytes_value)
        if self.client is not None:
            self.client.queue(cmd)
        #fixme do we need this?
        #fixme but we should save the outputs states to file (to recover after a reboot/power cycle)
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

    @staticmethod
    def pack_bits(bits_list): #will pack a list of bit values as a list of bytes, MSB is first bit and so on
        res = 0
        shift=0
        for i in bits_list:
            print("i=",i,"res=",res)            
            res |= i << shift
            shift+=1
            print("i=",i,"res=",res)
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
