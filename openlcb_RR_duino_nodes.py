from openlcb_cmri_cfg import hex_int
from openlcb_protocol import *
from openlcb_debug import *
import openlcb_config

class RR_duino_message:
    START=0xFF
    #command byte special bits positions
    CMD_ANSW_BIT = 0
    CMD_LAST_ANSW_BIT=1
    CMD_ASYNC_BIT=2
    CMD_SPECIAL_CONFIG_BIT=3
    CMD_RW_BIT=4
    CMD_SENSOR_TURNOUT_BIT=4
    CMD_CONFIG_DEL_BIT=5
    CMD_ALL_BIT=6
    CMD_CONFIG_BIT = 7

    CMD_SPECIAL_CONFIG_CODE_POS=4
    CMD_SPECIAL_CONFIG_CODE_MASK=7

    CMD_VERSION = 0
    CMD_SET_ADDRESS = 1
    CMD_STORE_EEPROM = 2
    CMD_LOAD_EEPROM = 3
    CMD_SHOW_SENSORS = 4
    CMD_SHOW_TURNOUTS = 5
    CMD_TURNOUT_FINE_TUNE=6
    CMD_CLEAR_EEPROM = 7
    
    #address byte special bits positions
    ADD_LIST_BIT=6
    
    #subaddress byte special bits positions
    SUBADD_VALUE_BIT = SUBADD_SENSOR_IO_BIT=SUBADD_TURNOUT_RELAY_PINS_BIT=6
    SUBADD_LAST_IN_LIST_BIT=7
    
    #subaddress byte special bits positions
    PIN_PULSE_PIN_BIT = 7
    PIN_PULLUP_BIT = 7

    #other constants
    INPUT_SENSOR = 0
    INPUT_SENSOR_PULLUP = 1
    OUTPUT_SENSOR=2

    
    def __init__(self,raw_message=None):  # raw_message must be a bytearray
        self.raw_message = raw_message

    def set_header(self,command,address):
        self.raw_message = bytearray((RR_duino_message.START,command,address))

    def extend_payload(self,array_b):
        self.raw_message.extend(array_b)

    def get_address(self):
        return self.raw_message[2] & 0x3F

    def get_command(self):
        return self.raw_message[1]
    
    def get_version(self):
        return self.raw_message[2]

    def is_valid(self):
        #crude test about correctness: only check the start byte for now
        return self.raw_message[0]==RR_duino_message.START
    
    def is_answer(self):
        #return True if this message is an answer from the device
        return (self.raw_message[1] & (1 << RR_duino_message.CMD_ANSW_BIT))==0

    def is_answer_to_cmd(self,cmd):
        #return True if this message is an answer to the command "cmd"
        #fixme
        if not self.is_answer():
            return False
        #check base command code
        if (self.raw_message[1] & 0b11111000) != (cmd & 0b11111000):
            return False
        #check if async bit was set in command
        if cmd & (1 << CMD_ASYNC_BIT) != 0:
            return self.raw_message[1] (1 << CMD_ASYNC_BIT) !=0
        return TRUE
    
    def is_last_answer(self):
        #return True if this message is the last answer (used mainly by show commands/async events reporting)
        return (self.raw_message[1] & (1 << RR_duino_message.CMD_LAST_ANSW_BIT))==0

    def is_read_cmd(self):
        return not self.is_config_cmd() and (self.raw_message[1] & (1 << RR_duino_message.CMD_RW_BIT))==0

    def is_config_cmd(self):
        #returns True if this is a config command (might be a special config command)
        return (self.raw_message[1] & (1 << RR_duino_message.CMD_CONFIG_BIT))!=0

    def get_special_config(self):
        #returns the special config code (cf top of the class)
        #use it only if the command is a special config command
        return (self.raw_message[1] >> RR_duino_message.CMD_SPECIAL_CONFIG_CODE_POS ) & RR_duino_message.CMD_SPECIAL_CONFIG_CODE_MASK
    
    def is_special_config_cmd(self):
        #returns True if this is a special config command
        return self.is_config_cmd() and (self.raw_message[1] & (1 << RR_duino_message.CMD_SPECIAL_CONFIG_BIT))!=0

    def on_turnout(self):
        #returns True if this command is about sensors
        return (self.raw_message[1] & (1 << RR_duino_message.CMD_SENSOR_TURNOUT_BIT))!=0
    
    def async_events_pending(self):
        #return True if this message indicates that there are async events waiting to be sent
        #by the device
        return (self.raw_message[1] & (1 << RR_duino_message.CMD_ASYNC_BIT))!=0
    
    def is_list(self):
        #return True if message is a list (of sensors/turnouts)...
        return (self.raw_message[2] & (1 << RR_duino_message.ADD_LIST_BIT))!=0

    def is_all(self):
        #return True if it is about ALL sensors/turnouts (only for read or write commands/answer)
        return self.is_list() and (self.raw_message[1] & (1 << RR_duino_message.CMD_ALL_BIT))!=0

    def get_error_code(self):
        if (self.raw_message[-1] & 0x80) == 0:
            return None
        return self.raw_message[-1] & 0x0F

    def set_error_code(self,err):
        self.raw_message.append(0x80+err)

    def get_list_of_values(self):
        #return a list of pairs (subaddress,value)
        #only valid for a r/w list command
        l = []
        for c in self.raw_message[3:-1]: #forget last byte (the list stop byte)
            l.append((c & 0x3F,c >> RR_duino_message.SUBADD_VALUE_BIT))
        return l

    def get_sensor_config(self,index):
        #return a tuple (subaddress,pin,type)
        #only valid for a config sensor list command or a show sensor command answer

        if self.raw_message[index] & (1 << RR_duino_message.SUBADD_SENSOR_IO_BIT) != 0:
            sensor_type = RR_duino_message.SENSOR_OUTPUT
        else:
            if self.raw_message[index+1] & (1 << RR_duino_message.PIN_PULLUP_BIT) != 0:
                sensor_type = RR_duino_message.SENSOR_INPUT_PULLUP
            else:
                sensor_type = RR_duino_message.SENSOR_INPUT
        return (self.raw_message[index] & 0x3F, self.raw_message[index+1] & 0x7F, sensor_type)
    
    def get_list_of_sensors_config(self):
        #return a list if tuples (see get_sensor_config)
        l = []
        index = 3 #beginning of list
        while index<len(self.raw_message)-1:  #end of list
            l.append(self.get_sensor_config(index))
            index+=2  #next sensor config
        return l
        
    def get_turnout_config(self,index):
        #return a tuple (subaddress,servo_pin,straight pos,thrown pos [,relay pin 1, relay pin 2,pulse pin 1, pulse pin 2])
        #only valid for a config turnout list command or a show turnout command answer
        subadd = self.raw_message[index] & 0x3F
        if self.raw_message[index] & (1 << RR_duino_message.SUBADD_TURNOUT_RELAY_PINS_BIT) != 0:
            #relay pins are present
            pulse_pin_1 = self.raw_message[index+4] & (1 << RR_duino_message.PIN_PULSE_BIT) != 0
            pulse_pin_2 = self.raw_message[index+5] & (1 << RR_duino_message.PIN_PULSE_BIT) != 0
            return (subadd,self.raw_message[index+1],
                    self.raw_message[index+2],self.raw_message[index+3],
                    self.raw_message[index+4] & 0x7F,self.raw_message[index+5] & 0x7F,
                    pulse_pin_1,pulse_pin_2)
        
        else:
            return (subadd,self.raw_message[index+1],
                    self.raw_message[index+2],self.raw_message[index+3])
        
    def get_list_of_turnouts_config(self):
        #return a list of tuples (subaddress,pin,type)
        #only valid for a config sensor list command or a show sensor command answer
        l = []
        index = 3 #beginning of list
        while index<len(self.raw_message)-1:  #end of list
            turnout_cfg = self.get_turnout_config(index)
            l.append(turnout_cfg)
            if len(turnout_cfg)==4:#next turnout config index depends on relay pins present or not
                index+=4  
            else:
                index+=6
        return l

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

    @staticmethod
    def build_rw_cmd_header(address,read,for_sensor,is_list,is_all=False):
        """
        build the command and address bytes for a rw command
        """
        #set write bit if needed
        if read:
            command = 0
        else:
            command = 1 << RR_duino_message.CMD_RW_BIT
        #set turnout bit if needed
        if not for_sensor:
            command |= 1 << RR_duino_message.CMD_SENSOR_TURNOUT_BIT
        #set "all" bit if needed
        if is_all:
            command |= 1 << RR_duino_message.CMD_ALL_BIT
        final_add = address
        if is_list or is_all:
            final_add |= 1 << RR_duino_message.ADD_LIST_BIT
        m = RR_duino_message()
        m.set_header(command,final_add)
        return m

    @staticmethod
    def encode_subadd_value(pair):
        if pair[1]==0:
            return bytes((pair[0],))
        else:
            return bytes((pair[0] | (1 << RR_duino_message.SUBADD_VALUE_BIT),))

    @staticmethod
    def encode_sensor_config(config):
        subadd,pin,sensor_type = config
        if sensor_type == RR_duino_message.OUTPUT_SENSOR:
            subadd |= (1 << RR_duino_message.SUBADD_SENSOR_IO_BIT)
        elif sensor_type == RR_duino_message.INPUT_SENSOR_PULLUP:
            pin |= (1 << RR_duino_message.PIN_PULLUP_BIT)
        return bytes((subadd,pin))

    @staticmethod
    def encode_turnout_config(config):
        #config = (subadd,servo_pin,straight_pos,thrown_pos [,relay_pin_1,relay_pin2,pulse pin 1,pulse pin 2])
        subadd = config[0]
        if len(config)>4:
            subadd |= 1 << SUBADD_TURNOUT_RELAY_PINS_BIT
        res = bytearray()
        res.extend((subadd,config[1],config[2],config[3]))
        if len(config)>4:
            relay_pins = [config[4]]
            if config[6]:
                relay_pins[0] |= 1 << PIN_PULSE_PIN_BIT
            relay_pin.append(config[5])
            if config[7]:
                relay_pins[1] |= 1 << PIN_PULSE_PIN_BIT
            res.extend((relay_pins))
        return res

    @staticmethod
    def build_load_from_eeprom(add):
        return RR_duino_message(bytes((0xFF,0b10111001,add)))

    @staticmethod
    def build_save_to_eeprom(add):
        return RR_duino_message(bytes((0xFF,0b10101001,add)))

    @staticmethod
    def build_version_cmd(add):
        return RR_duino_message(bytes((0xFF,0b10001001,add)))

    @staticmethod
    def build_show_cmd(add, on_turnout=False):
        c = 0b11001001
        if on_turnout:
            c |= (1 << RR_duino_message.CMD_SENSOR_TURNOUT_BT)
        return RR_duino_message(bytes((0xFF,c,add)))
    
    @staticmethod
    def is_complete_message(msg):
        #msg is a bytes array
        #returns True if the message is complete, False if msg is incomplete but valid
        #returns None if message is invalid

        def is_cmd_add_message(msg):
            #checks if the message is only 3 bytes: start,command,address
            if msg.is_answer():
                return False
            #it is not an answer
            if msg.is_special_config_cmd():
                #it is a special config, check the codes
                return msg.get_special_cfg()!=CMD_TURNOUT_FINE_TUNE
            elif msg.is_read_cmd() and msg.is_all(): #read all command
                return True
            return False
                
        
        def sensors_config_list_complete(msg):
            #sensors config are 2 bytes long, so check if we have a full number of config plus one byte
            if (len(msg.raw_message)-1-3) % 2 == 0:
                #yes so check that the last byte, if it is 0x8x it is complete
                return msg.raw_message[-1] & 0x80 != 0

        def next_turnout_config_pos(msg,index):
            #return the position of the next turnout config
            #index is the position of the current turnout config
            if msg.raw_message[index] & (1 << SUBADD_TURNOUT_RELAY_PINS_BIT) != 0:
                return index+6
            else:
                return index+4
            
        def turnouts_config_list_complete(msg):
            last = current = 3 #skip start,command and address byte
            while current < len(msg.raw_message):
                last = current
                current = next_turnout_config_pos(msg,last)
            return msg.raw_message[last] & 0x80 != 0
                                
        if len(msg)==0:
            return False
        #length>0
        if msg[0]!=RR_duino.RR_duino_message.START:
            return None
        if len(msg)<3:
            return False
        message = RR_duino_message(msg)
        if len(msg)==3:
            return is_cmd_add_message(message)

        #length is > 3
        special_config = None
        if message.is_special_config_cmd():
            special_config = message.get_config_cmd()
        
        #treat the answer cases (must finish by 0x8x)
        if message.is_answer():
            #exceptions: the show and version commands can have bytes with MSB!=0 before the end
            if special_config is None or (special_config!=CMD_VERSION and special_config!=CMD_SHOW_SENSORS
                                          and special_config!=CMD_SHOW_TURNOUTS):
                return msg[-1] & 0x80 != 0
            #Treat the case of CMD_VERSION
            if special_config == CMD_VERSION:
                return len(msg)>=5 and (msg[-1] & 0x80 != 0)
            #Treat the CMD_SHOW_SENSORS:
            if special_config == CMD_SHOW_SENSORS:
                return sensors_config_list_complete(message)
            return turnouts_config_list_complete(message)
        #it is a command of length >=4
        #sensors and turnouts config
        if message.is_config_cmd() and special_config is None and message.raw_message[1] & (1 << CMD_CONFIG_DEL_BIT)==0:
            if message.on_turnout():
                if message.is_list():
                    return turnouts_config_list_complete(message)
                else:
                    return next_turnout_config_pos(message,3)==len(message.raw_message)-1
            else:
                if message.is_list():
                    return sensors_config_list_complete(message)
                else:
                    return len(message.raw_message)==5
            
        if message.is_list():  #list commands must finish by 0x8x (all special cases have been dealt with before
            return message.raw_message[-1] & 0x80!=0

        if special_config== CMD_TURNOUT_FINE_TUNE:
            return len(message.raw_message)==5
        #here only simple commands remain: r/w on one device, delete config of one device
        #so it must be complete (they are all 4 bytes commands)
        return True
    
class RR_duino_node:
    """
    represents a RR_duino node
    """
    def __init__(self,address,client=None):
        self.address = address
        self.client = client

    def __str__(self):
        res = "RR-duino Node,client="+str(self.client.name)+",add="+str(self.address)
        return res

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

def find_node_from_add(add,nodes):
    for n in nodes:
        if n.RR_duino_node.address == add:
            return n
    return None

    
