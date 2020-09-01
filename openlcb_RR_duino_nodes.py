from openlcb_cmri_cfg import hex_int
from openlcb_protocol import *
from openlcb_debug import *
import openlcb_config,openlcb_nodes,collections

class RR_duino_message:
    START=0xFF
    #command byte special bits positions
    CMD_ANSW_BIT = 0
    CMD_LAST_ANSW_BIT=1
    CMD_ASYNC_BIT=2
    CMD_SPECIAL_CONFIG_BIT=3
    CMD_RW_BIT=5
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
    PIN_PULSE_BIT = 7
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
        #check if async bit was set in command
        if cmd & (1 << RR_duino_message.CMD_ASYNC_BIT) != 0:
            return (self.raw_message[1] & (1 << RR_duino_message.CMD_ASYNC_BIT)) !=0
        #check base command code
        if (self.raw_message[1] & 0b11111000) != (cmd & 0b11111000):
            return False
        return True
    
    def is_last_answer(self):
        #return True if this message is the last answer (used mainly by show commands/async events reporting)
        return (self.raw_message[1] & (1 << RR_duino_message.CMD_LAST_ANSW_BIT))==0

    def is_read_cmd(self):
        return not self.is_config_cmd() and (self.raw_message[1] & (1 << RR_duino_message.CMD_RW_BIT))==0

    def is_write_cmd(self):
        return not self.is_config_cmd() and (self.raw_message[1] & (1 << RR_duino_message.CMD_RW_BIT))!=0

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

    def get_value(self):
        return (self.raw_message[3] & 0x3F, self.raw_message[3] >> RR_duino_message.SUBADD_VALUE_BIT)
    
    def get_list_of_values(self):
        #return a list of pairs (subaddress,value)
        #only valid for a r/w list command
        l = []
        for c in self.raw_message[3:-1]: #forget last byte (the list stop byte)
            l.append((c & 0x3F,c >> RR_duino_message.SUBADD_VALUE_BIT))
        #debug("list of values",l)
        return l

    def get_all_values(self,nb_values):
        #return a list of values (0/1)
        #only valid for a "read all" sensors or turnouts
        l = []
        byte_index = 3
        b = self.raw_message[byte_index]
        bit_pos = 0
        for i in range(nb_values):
            if bit_pos == 8:
                bit_pos = 0
                byte_index+=1
                b = self.raw_message[byte_index] 
                 #sanity check
                if self.raw_message[byte_index] & 0x80 != 0:
                    #stop: this byte is the error code, not all values are present
                    return l
            l.append((b >> bit_pos) & 0x01) #shift left and keep LSB only
            bit_pos+=1
        #debug("list of all values",l)
        return l
        
    def get_sensor_config(self,index):
        #return a tuple (subaddress,pin,type)
        #only valid for a config sensor list command or a show sensor command answer

        if self.raw_message[index] & (1 << RR_duino_message.SUBADD_SENSOR_IO_BIT) != 0:
            sensor_type = RR_duino_message.OUTPUT_SENSOR
        else:
            if self.raw_message[index+1] & (1 << RR_duino_message.PIN_PULLUP_BIT) != 0:
                sensor_type = RR_duino_message.INPUT_SENSOR_PULLUP
            else:
                sensor_type = RR_duino_message.INPUT_SENSOR
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
        wire_msg=""
        for b in self.raw_message:
            wire_msg += hex_int(b)+" "

        return wire_msg[:-1]

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
        #set command bit
        command = 1
        #set write bit if needed
        if not read:
            command |= 1 << RR_duino_message.CMD_RW_BIT
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
        if pair[1] is None or pair[1]==0:
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
            subadd |= 1 << RR_duino_message.SUBADD_TURNOUT_RELAY_PINS_BIT
        res = bytearray()
        res.extend((subadd,config[1],config[2],config[3]))
        if len(config)>4:
            relay_pins = [config[4]]
            if config[6]:
                relay_pins[0] |= 1 << RR_duino_message.PIN_PULSE_PIN_BIT
            relay_pin.append(config[5])
            if config[7]:
                relay_pins[1] |= 1 << RR_duino_message.PIN_PULSE_PIN_BIT
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
            c |= (1 << RR_duino_message.CMD_SENSOR_TURNOUT_BIT)
        return RR_duino_message(bytes((0xFF,c,add)))

    @staticmethod
    def build_async_cmd(add):
        return RR_duino_message(bytes((0xFF,0b00000101,add)))

    @staticmethod
    def build_simple_rw_cmd(add,subadd,read=True,for_sensor=True,value=None):
        msg = RR_duino_message.build_rw_cmd_header(add,read,for_sensor,False)
        msg.raw_message.extend(RR_duino_message.encode_subadd_value((subadd,value)))
        return msg
    
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
                return msg.get_special_config()!=RR_duino_message.CMD_TURNOUT_FINE_TUNE
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
            if msg.raw_message[index] & (1 << RR_duino_message.SUBADD_TURNOUT_RELAY_PINS_BIT) != 0:
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
        if msg[0]!=RR_duino_message.START:
            return None
        if len(msg)<3:
            #print("len(msg)<3")
            return False
        message = RR_duino_message(msg)
        if len(msg)==3:
            return is_cmd_add_message(message)

        #length is > 3
        special_config = None
        if message.is_special_config_cmd():
            special_config = message.get_special_config()
        
        #treat the answer cases (must finish by 0x8x)
        if message.is_answer():
            #exceptions: the show and version commands can have bytes with MSB!=0 before the end
            if special_config is None or (special_config!=RR_duino_message.CMD_VERSION
                                          and special_config!=RR_duino_message.CMD_SHOW_SENSORS
                                          and special_config!=RR_duino_message.CMD_SHOW_TURNOUTS):
                return msg[-1] & 0x80 != 0
            #Treat the case of CMD_VERSION
            if special_config == RR_duino_message.CMD_VERSION:
                return len(msg)>=5 and (msg[-1] & 0x80 != 0)
            #Treat the CMD_SHOW_SENSORS:
            if special_config == RR_duino_message.CMD_SHOW_SENSORS:
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

        if special_config == RR_duino_message.CMD_TURNOUT_FINE_TUNE:
            return len(message.raw_message)==5
        #here only simple commands remain: r/w on one device, delete config of one device
        #so it must be complete (they are all 4 bytes commands)
        return True

class RR_duino_node_desc:
    #default dict to add new nodes to the DB when they have no description
    DEFAULT_JSON = { "fullID":None }

    def __init__(self,desc_dict):
        self.desc_dict = dict(desc_dict)  #(shallow) copy the dict containing the node description
        if not "sensors_ev_dict" in self.desc_dict:
            self.desc_dict["sensors_ev_dict"]={}
        if not "turnouts_ev_dict" in self.desc_dict:
            self.desc_dict["turnouts_ev_dict"]={}
        self.ID = self.desc_dict["fullID"]

    def to_json(self):
        return self.desc_dict

class Deferred_read:
    DEFER_TIME = 0.5 #seconds
    def __init__(self,add,turnouts = False):
        self.turnouts = turnouts  #type of peripherals
        self.subadds = []  #list of subaddresses
        self.clock = None
        self.address = add
        
    def add(self,subadd):
        if subadd in self.subadds:
            #do not add it twice
            return
        self.subadds.append(subadd)
        if self.clock is None:
            self.clock = time.time()

    def build_msg(self):
        if self.subadds.is_empty():
            return None
        if len(self.subadds)==1:
            #special case, only one reading
            return RR_duino_message.build_simple_rw_cmd(add,subadds[0],True,not turnouts)
        else:
            msg = RR_duino_message.build_rw_cmd_header(add,True,not turnouts,True)  #get the header ready
            msg.raw_message.extend(self.subadds)
            msg.raw_message.append(0x80) #list termination
            return msg
        
    def check_time(self):
        if self.clock is None:
            return None
        if time.time()>self.clock+Deferred_read.DEFER_TIME:
            return self.build_msg()
        return None
    
    def reset(self):
        self.clock = None
        self.subadds = []

class Deferred_write(Deferred_read):
    def __init__(self,add,turnouts=False):
        super().__init__(add,turnouts)

    def add(self,subadd,value):
        super().add(RR_duino_message.encode_subbad_value((subadd,value)))

    def build_msg(self):
        msg = super().build_msg()
        if msg is None:
            return None
        msg.raw_message[1] |= 1 << RR_duino_message.CMD_RW_BIT   #set write bit
        return msg
    
class RR_duino_node(openlcb_nodes.Node):
    """
    represents a RR_duino node which means it is an openlcb node (with memory, alias and so on
    and also is linked to the real hardware (via the bus program helper) using the RR_duino protocol
    """
    CDI_header="""<?xml version="1.0"?>
<cdi xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:noNamespaceSchemaLocation="http://openlcb.org/schema/cdi/1/1/cdi.xsd">

<identification>
<manufacturer>RR_duino_node-OLCB-GW</manufacturer>
<model>Test</model>
<hardwareVersion>%hwversion</hardwareVersion>
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

<segment space='0'>
<name>Address of the device: %address</name>
<description>The RR_duino node address (read only)</description>
<group>
<name>This node has %nsensors sensors and %nturnouts turnouts configured</name>
</group>
</segment>"""
    CDI_sensors ="""<segment space='1'>
<group replication="%nsensors">
<name>Sensors</name>
<description>Each sensor on the device.</description>
<repname>Sensor</repname>
<group>
<name>Subaddress</name>
<description>The subaddress of the sensor (read only)</description>
<int size='1'>
<name>Subaddress</name>
</int>
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
</segment>"""
    CDI_turnouts="""<segment space='2'>
<group replication="%nturnouts">
<name>Turnouts</name>
<description>Each sensor on the device.</description>
<repname>Turnout</repname>
<group>
<name>Subaddress</name>
<description>The subaddress of the turnout (read only)</description>
<int size='1'>
<name>Subaddress</name>
</int>
<eventid>
<name>Set turnout in straight position</name>
<description>When this event occurs, the turnout is set to straight position</description>
</eventid>
<eventid>
<name>Set turnout to thrown position</name>
<description>When this event occurs, the turnout is set to thrown position.</description>
</eventid>
<eventid>
<name>Turnout has reached the straight position</name>
<description>When the turnout has reached the straight position, this events is generated.</description>
</eventid>
<eventid>
<name>Turnout has reached thrown position</name>
<description>When the turnout has reached the thrown position, this events is generated.</description>
</eventid>
</group>
</group>
</segment>"""
    CDI_footer="""</cdi>
\0"""
    #memory spaces
    ADDRESS_SEGMENT = 0
    SENSORS_SEGMENT = 1
    TURNOUTS_SEGMENT = 2
    #deferred rw
    DEFER_READ_SENSORS = 0
    DEFER_READ_TURNOUTS = 1
    DEFER_WRITE_SENSORS = 2
    DEFER_WRITE_TURNOUTS = 3
    
        
    def __init__(self,client,ID,address,hwversion,desc):
        super().__init__(ID)
        self.address = address
        self.hwversion = hwversion
        #dict subaddresses <-> config
        self.sensors_cfg={}
        self.turnouts_cfg={}
        #dictionnaries: subaddress <-> corresponding events list
        self.sensors_ev_dict = {}
        self.turnouts_ev_dict= {}
        self.desc = desc
        debug("rr_duino constrcutor, desc=",desc.desc_dict)
        self.client=client
        #deferred reads and writes to offload some messages off the RR_duino bus
        #only used for reads and writes caused by producer identify and consumer identified events
        self.defer_rw = [Deferred_read(address),Deferred_read(address,True),
                         Deferred_write(address),Deferred_write(address,True)]
        #producer identify are answered when the corresponding deferred reads are treated
        #this is a list of (turnout,subadd,value) where turnout is True for a turnout and False for a sensor
        #and value is the value of the sensor correspondig to the event in the identify producer received
        #each read received will be checked to see if a corresponding producer identifier message can be answered
        self.waiting_prod_identified = []

    def __str__(self):
        res = "RR-duino Node, fullID="+str(self.client.name)+",add="+str(self.address)+",version="+str(self.hwversion)
        return res

    def get_CDI(self):
        CDI = RR_duino_node.CDI_header.replace("%address",str(self.address)).replace("%hwversion",str(self.hwversion)).replace("%nsensors",str(len(self.sensors_cfg))).replace("%nturnouts",str(len(self.turnouts_cfg)))
        if len(self.sensors_cfg)>0:
            CDI += RR_duino_node.CDI_sensors.replace("%nsensors",str(len(self.sensors_cfg)))

        if len(self.turnouts_cfg)>0:
            CDI+= RR_duino_node.CDI_turnouts.replace("%nturnouts",str(len(self.turnouts_cfg)))
            
        return CDI+RR_duino_node.CDI_footer

    def load_from_desc(self): #get events from the node desc
        #load address, description
        if "version" in self.desc.desc_dict:
            version = self.desc.desc_dict["version"]
        else:
            version = 0
        self.memory[251].set_mem(0,bytes((version,)))
        if "name" in self.desc.desc_dict:
            name = self.desc.desc_dict["name"]
        else:
            name = ""
        self.memory[251].set_mem(1,openlcb_nodes.normalize(name,63))
        if "description" in self.desc.desc_dict:
            description= self.desc.desc_dict["description"]
        else:
            description = ""
        self.memory[251].set_mem(64,openlcb_nodes.normalize(description,64))
        #load sensors events
        #delete desc which are not related to existing subaddresses (they have been deleted for example)
        debug("before pruning desc",self.desc.desc_dict["sensors_ev_dict"])
        if self.desc.desc_dict["sensors_ev_dict"] is not None:
            subadd_to_del=[]
            for subadd in self.desc.desc_dict["sensors_ev_dict"]:
                if int(subadd) not in self.sensors_cfg:
                    subadd_to_del.append(subadd)
            for subadd in subadd_to_del:
                del self.desc.desc_dict["sensors_ev_dict"][subadd]
        #add missing descriptions if needed
        #this is needed when a node hardware has been reconfigured
        #the nb of turnouts/sensors may have changed, hence the discrepancy
        debug("before missing desc",self.desc.desc_dict["sensors_ev_dict"])
        for subadd in self.sensors_cfg:
            if str(subadd) not in self.desc.desc_dict["sensors_ev_dict"]:
                self.desc.desc_dict["sensors_ev_dict"][str(subadd)]=([str(Event.from_str(None))]*2)

        index = 0
        for subadd in self.desc.desc_dict["sensors_ev_dict"]:
            ev_pair = self.desc.desc_dict["sensors_ev_dict"][subadd]
            #set subaddress (use memory object directly)
            #17 is the size of a record:subadd + 2*8 bytes (an event is 8 bytes)
            self.memory[RR_duino_node.SENSORS_SEGMENT].set_mem(index * 17,bytes((int(subadd),)))
            #set events in memory
            for i in range(2):
                self.memory[RR_duino_node.SENSORS_SEGMENT].set_mem(1+index*(1+8*2)+i*8,
                                                                   Event.from_str(ev_pair[i]).id)
            #and in event dictionnary
            self.sensors_ev_dict[int(subadd)]=[Event.from_str(ev_pair[0]).id,
                                               Event.from_str(ev_pair[1]).id]
            index+=1
            
        debug("before using desc",self.desc.desc_dict["sensors_ev_dict"])
        debug("before using desc",self.sensors_ev_dict)
            
        #load turnouts events
        if self.desc.desc_dict["turnouts_ev_dict"] is not None:
            subadd_to_del=[]
            for subadd in self.desc.desc_dict["turnouts_ev_dict"]:
                if int(subadd) not in self.turnouts_cfg:
                    subadd_to_del.append(subadd)
            for subadd in subadd_to_del:
                del self.desc.desc_dict["turnouts_ev_dict"][subadd]
        #add missing descriptions if needed
        #this is needed when a node hardware has been reconfigured
        #the nb of turnouts may have changed, hence the discrepancy
        debug("before missing desc",self.desc.desc_dict["turnouts_ev_dict"])
        for subadd in self.turnouts_cfg:
            if str(subadd) not in self.desc.desc_dict["turnouts_ev_dict"]:
                self.desc.desc_dict["turnouts_ev_dict"][str(subadd)]=([str(Event.from_str(None))]*4)
        index = 0
        debug("before using desc",self.desc.desc_dict["turnouts_ev_dict"])
        for subadd in self.desc.desc_dict["turnouts_ev_dict"]:
            ev_tuple = self.desc.desc_dict["turnouts_ev_dict"][subadd]
            #set subaddress (use memory object directly)
            #33 is the size of a record:subadd + 4*8 bytes (an event is 8 bytes)
            self.memory[RR_duino_node.TURNOUTS_SEGMENT].set_mem(index * 33,bytes((int(subadd),)))
            #set events
            for i in range(4):
                #set memory, this will set the event structures accordingly
                self.memory[RR_duino_node.TURNOUTS_SEGMENT].set_mem(1+index*(1+8*4)+i*8,
                                                                    Event.from_str(ev_tuple[i]).id)
            #set turnout events dictionnary accordingly
            self.turnouts_ev_dict[int(subadd)]=[Event.from_str(ev_tuple[0]).id,
                                                Event.from_str(ev_tuple[1]).id,
                                                Event.from_str(ev_tuple[2]).id,
                                                Event.from_str(ev_tuple[3]).id]
            index+=1
        
        #self.memory[1].dump()
        #self.memory[2].dump()
        
    def create_memory(self):
        address_mem=openlcb_nodes.Mem_space([(0,1)])  #node address (R) 
        address_mem.set_mem(0,bytes((self.address,)))  #set address
        sensors_mem=openlcb_nodes.Mem_space()
        offset = 0
        #loop over all sensors
        for subadd in self.sensors_cfg:
            print(subadd)
            sensors_mem.create_mem(offset,1)    #subaddress (R)
            sensors_mem.set_mem(offset,bytes((subadd,)))  #set subaddress
            offset+=1
            for j in range(2):
                sensors_mem.create_mem(offset,8)       #event id        (RW)
                offset+=8
        turnouts_mem=openlcb_nodes.Mem_space()
        offset = 0
        #loop over all turnouts
        for subadd in self.turnouts_cfg:
            turnouts_mem.create_mem(offset,1)    #subaddress (R)
            turnouts_mem.set_mem(offset,bytes((subadd,)))  #set subaddress
            offset+=1
            for j in range(4):
                turnouts_mem.create_mem(offset,8)       #event id        (RW)
                offset+=8

        self.memory = {251:openlcb_nodes.Mem_space([(0,1),(1,63),(64,64)]),
                       0:address_mem,1:sensors_mem,2:turnouts_mem}

    def set_mem(self,mem_sp,offset,buf):
        debug("SET MEM",mem_sp,offset,buf)
        if mem_sp == RR_duino_node.ADDRESS_SEGMENT: #address
            if offset == 0:
                debug("Trying to change address")
            else:
                super().set_mem(mem_sp,offset,buf) #will error out
                
        elif mem_sp == RR_duino_node.SENSORS_SEGMENT: #sensors segment
            #compute what is written: 0=> subadd 1=> first event 9=>second event
            pos_entry = offset %17
            if pos_entry==0:
                #fixme: I think we should not do that...
                debug("setting subaddress!")
            else:
                #set memory
                super().set_mem(mem_sp,offset,buf)
                #update node structures accordingly
                #get subaddress
                subadd = self.read_mem(RR_duino_node.SENSORS_SEGMENT,offset-pos_entry,1)[0]
                if pos_entry==1:
                    index=0 #first event
                else:
                    index=1 #second event
                #sync sensor events dictionnary
                debug(subadd,index,buf,self.sensors_ev_dict,self.desc.desc_dict["sensors_ev_dict"])
                self.sensors_ev_dict[subadd][index]=buf
                #sync the description
                self.desc.desc_dict["sensors_ev_dict"][str(subadd)][index]=str(Event(buf))

        elif mem_sp == RR_duino_node.TURNOUTS_SEGMENT:  #turnouts segment
            debug("Set_mem on turnouts")
            #compute what is written: 0=> subadd 1=> first event 9=>second event
            pos_entry = offset % 33
            if pos_entry==0:
                #fixme: I think we should not do that...
                debug("setting subaddress!")
            else:    
                #set memory
                super().set_mem(mem_sp,offset,buf)
                #update node structures accordingly
                #get subaddress
                subadd = self.read_mem(RR_duino_node.TURNOUTS_SEGMENT,offset-pos_entry,1)[0]
                #compute which event we are modifying
                index = (pos_entry - 1)//8
                debug("subadd=",subadd,"off=",offset,"index=",index)
                self.turnouts_ev_dict[subadd][index]=buf #sync event dict
                #sync the description
                self.desc.desc_dict["turnouts_ev_dict"][str(subadd)][index]=str(Event(buf))
 
        elif mem_sp==251:  #identification segment
            super().set_mem(mem_sp,offset,buf)
            if offset == 0:
                self.desc.desc_dict["version"]=buf[0]
            elif offset == 1:
                self.desc.desc_dict["name"]=buf[:buf.find(0)].decode('utf-8')
            elif offset == 64:
                self.desc.desc_dict["description"]=buf[:buf.find(0)].decode('utf-8')


    def check_defer(self):
        for defer in self.defer_rw:
            msg = defer.check_time()
            if msg is not None:
                defer.reset()
                self.client.queue(msg.to_wire_message().encode('utf-8'))            

    def generate_events(self,subadd_values,turnouts = False):
        #debug("generate events",subadd_values,turnouts)
        ev_lst=[]
        #first check for the waiting producer identified
        debug("list of values=",subadd_values,turnouts)
        subadd_val_to_delete=[]
        for (subadd,value) in subadd_values:
            for (ev_turnout,ev_subadd,ev_val) in self.waiting_prod_identified:
                if (ev_turnout,subadd)==(turnouts,subadd):
                    if ev_val-2 == value:  #we only use the position reached events part
                        MTI = Frame.MTI_PROD_ID_VAL
                    else:
                        MTI = Frame.MTI_PROD_ID_INVAL
                    debug("producer identified:",subadd,value,turnouts)
                    if ev_turnout:
                        ev_lst.append(Frame.build_from_event(self,self.turnouts_ev_dict[subadd][ev_val],MTI))
                    else:
                        ev_lst.append(Frame.build_from_event(self,self.sensors_ev_dict[subadd][ev_val],MTI))
                    subadd_val_to_delete.append((subadd,value))
        #delete all read results already used
        for subadd_val in subadd_val_to_delete:
            subadd_values.remove(subadd_val)

        debug("list of values after =",subadd_values,turnouts)
        for (subadd,value) in subadd_values:
            if turnouts:
                if subadd in self.turnouts_cfg:
                    if self.turnouts_ev_dict[subadd][value+2]==b"\0"*8:
                        #do not send 0.0.0.0.0.0.0.0 events
                        continue
                    debug("Event for:",subadd,value,turnouts)
                    #we use value+2 to send the event "turnout has reached position value"
                    ev_lst.append(Frame.build_from_event(self,
                                                         self.turnouts_ev_dict[subadd][value+2],
                                                         0x5B4))
            else:
                debug("sensor",subadd,value,self.sensors_cfg)
                if subadd in self.sensors_cfg:
                    debug("IN!")
                    if self.sensors_ev_dict[subadd][value]==b"\0"*8:
                        #do not send 0.0.0.0.0.0.0.0 events
                        debug("all 0!",self.sensors_ev_dict)
                        continue
                    debug("Event for:",subadd,value,turnouts)
                    ev_lst.append(Frame.build_from_event(self,
                                                         self.sensors_ev_dict[subadd][value],
                                                         0x5B4))
        debug("ev list=",ev_lst)
        return ev_lst
    
    def process_receive(self,msg):
        debug("process receive=",msg.to_wire_message())

        if not msg.is_answer():
            debug("Broken protocol, the bus is receiving a command msg from the slaves!")
            return []
        if msg.get_error_code()!=0:
            debug("Command error!")
            return []
        if msg.is_read_cmd():
            if not msg.is_list():
                debug("unique value")
                return self.generate_events((msg.get_value()),msg.on_turnout())
            elif not msg.is_all():
                debug("list of values")
                return self.generate_events(msg.get_list_of_values(),msg.on_turnout())
            else:
                debug("Read all not implemented yet")
        elif msg.is_write_cmd():
            #just check the error status
            if msg.get_error_code()!=0:
                debug("Last write on node",self.ID,"has failed, error code",msg.get_error_code())
        return []
        
    def consume_event(self,ev,path=None):
        index = 0
        for subadd in self.sensors_ev_dict:
            ev_pair = self.sensors_ev_dict[subadd]
            val = -1
            if ev.id == ev_pair[0]:
                val = 0
            elif ev.id == ev_pair[1]:
                val = 1
            if val>=0:
                if self.sensors_cfg[subadd][1]==RR_duino_message.OUTPUT_SENSOR:
                    debug("RR_duino node",self.desc.desc_dict["fullID"],"sensors consuming event",str(ev))
                    self.client.queue(RR_duino_message.build_simple_rw_cmd(self.address,
                                                                           subadd,
                                                                           False,
                                                                           True,
                                                                           val).to_wire_message().encode('utf-8'))
                else:
                    debug("Error: received an event on an input sensors for RR_duino node",
                          self.desc.desc_dict["fullID"])
        for subadd in self.turnouts_ev_dict:
            ev_quad = self.turnouts_ev_dict[subadd]
            found = False
            for val in range(4):
                print(ev_quad[val],"  ",ev.id)
                if ev.id == ev_quad[val]:
                    found = True
                    break
            debug("turnouts consume event val=",val,found)
            if found:
                if val<2:
                    debug("RR_duino node",self.desc.desc_dict["fullID"],
                          "turnouts consuming event",str(ev))
                    self.client.queue(RR_duino_message.build_simple_rw_cmd(self.address,
                                                                           subadd,
                                                                           False,
                                                                           False,
                                                                           val).to_wire_message().encode('utf-8'))
                else:
                    debug("Error: received an event on an turnouts inputs for RR_duino node",
                          self.desc.desc_dict["fullID"])

    def check_id_producer_event(self,ev):
        """
        check if the event ev is coherent with one input state
        This is used to reply to "identify producer" event
        Return None and will send the answer later
        """
        for subadd in self.sensors_ev_dict:
            ev_pair= sensors_ev_dict[subadd]
            if self.sensors_cfg[subadd][1]!=OUTPUT_SENSOR: #must be an input
                val = -1
                if ev.id == ev_pair[0]:
                    val = 0
                elif ev.id == ev_pair[1]:
                    val = 1
                if val!=-1:
                    #found the input corresponding to the event
                    #place a deferred read and register the event to be answered later
                    self.defer_rw[RR_duino_node.DEFER_READ_SENSORS].add(subadd)
                    self.waiting_prod_identified.append((False,subadd,val))
        for subadd in self.turnouts_ev_dict:
            found = False
            ev_quad = self.turnouts_ev_dict[subadd]
            for val in range(2,4):
                if ev.id == ev_quad[val]:
                    found=True
                    break
            if found:
                #only for the event indicating that the turnout has reached its position
                #place a deferred read and register the event to be answered later
                self.defer_rw[RR_duino_node.DEFER_READ_TURNOUTS].add(subadd)
                self.waiting_prod_identified.append((True,subadd,val))
        return None

    def check_id_consumer_event(self,ev):
        #FIXME
        return openlcb_nodes.Node.ID_PRO_CON_UNKNOWN
def find_node_from_add(add,nodes):
    for n in nodes:
        if n.address == add:
            return n
    return None
