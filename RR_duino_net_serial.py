import socket,time
from openlcb_serial_bus import *
import json,sys
from openlcb_debug import *
import openlcb_RR_duino_nodes as RR_duino

#constants
ANSWER_TIMEOUT=1  #time out for an answer

class RR_duino_node:
    PING_TIME_OUT = 10   # 10s between pings
    def __init__(self,address,version):
        self.address=address
        self.version=version
        self.sensors = []  #list of sensors config (subaddress,pin,type)
        self.turnouts = [] #list of turnouts config (subaddress,servo_pin,straight pos,thrown pos [,relay pin 1, relay pin 2,pulse pin 1, pulse pin 2])
        self.last_ping = 0

    def get_config(self):
        #get list of sensors and turnouts
        debug("Getting config from node at ",self.address)
        command = build_show_cmd(self.address)
        i=0
        error = False
        while (i<2) and not error:
            answer = []
            done = False
            while not done:
                answer.append(send_msg(command))
                if answer[-1] is None or not answer[-1].is_answer_to_cmd(command.get_cmd()):
                    debug("Bad answer when loading config from node at ",self.address)
                    done = True
                    error = True
                else:
                    done = answer[-1].is_last_answer()
                    for m in answer:
                        if i==0:
                            self.sensors.extend(m.get_list_of_sensors_config())
                            debug("Sensors list=",self.sensors)
                        else:
                            self.turnouts.extend(m.get_list_of_turnouts_config())
                            debug("Turnouts list=",self.turnouts)

            command = build_show_cmd(self.address,True) #for turnouts now
            i+=1
            
def decode_messages():
    global rcv_messages,rcv_RR_messages

    sep = ";"
    print(rcv_messages)
    while sep==";":
        first,sep,end = rcv_messages.partition(";")
        print(first,"/",sep,"/",end)
        if sep!="":
            rcv_RR_messages.append(RR_duino.RR_duino_message.from_wire_message(first))
            rcv_messages = end

def process():
    global rcv_RR_messages,ser,must_wait_answer

    if ser.sending() or must_wait_answer:  #if we are already sending or waiting for an answer
        #not much we can do, let's wait for IO to proceed
        return
    #no IO occuring let's begin a new one if there is any

    if not rcv_RR_messages:
        return
    print("start IO")
    msg = rcv_RR_messages.pop(0)
    ser.send(msg.raw_message)
    must_wait_answer = True

def load_config(filename):
    #Load config file (json formatted dict config, see below)

    with open(filename) as cfg_file:
        config = json.load(cfg_file)
    #plug reasonable default values for secondary parameters
    if "serial_speed" not in config:
        config["serial_speed"]=19200
    if "openlcb_gateway_ip" not in config:
        config["openlcb_gateway_ip"]="127.0.0.1"
    if "openlcb_gateway_port" not in config:
        config["openlcb_gateway_port"]=50001
    if "nodes_ID_filename" not in config:
        config["nodes_ID_filename"]="RR_duino_net_serial_nodes_DB.cfg"
    
    return config

def send_msg(msg):
    #send a message to the serial port and wait for the answer (or timeout)
    #return answer or None if timed out
    #this should be called when no message is processed on the serial bus

    ser.send(msg.raw_message)
    answer = bytearray()
    begin = time.time()
    while not RR_duino.RR_duino_message.is_complete_message(message_to_send) and time.time()<begin+ANSWER_TIMEOUT: #not complete yet
        ser.process_IO()
        r = ser.read()
        if r is not None:
            begin = time.time()
            answer.extend(r)
    #check time out and answer begins by START and is the answer to the command we have sent
    if time.time()<begin+ANSWER_TIMEOUT:
        answer_msg =  RR_duino.RR_duino_message(answer)
        if answer_msg.is_valid() and answer_msg.is_answer_to_cmd(msg.raw_message[1]):
            return answer_msg
        else:
            debug("Broken protocol: command was:", msg.to_wire_message()," answer : ",answer_msg.to_wire_message())
    return None
    
def load_nodes():
    global fullID_add,online_nodes
    debug("loading RR_duino nodes from",config["nodes_ID_filename"])
    with open(config["nodes_ID_filename"]) as cfg_file:
        fullID_add_json = json.load(cfg_file)
    #keys in dict are always str when decoded from json so back to ints
    for ID in fullID_add_json:
        fullID_add[int(ID)]=fullID_add_json[ID]
        
    #try all addresses and ask each responding node to load its config from EEPROM
    for fullID in fullID_add:
        answer = send_msg(RR_duino.RR_duino_message.build_load_from_eeprom(fullID_add[fullID]))
        if answer is not None and answer.get_error_code()==0:
            #new node online, set it up
            answer = send_msg(RR_duino.RR_duino_message.build_save_to_eeprom(fullID_add[fullID]))
            if answer is not None and answer.get_error_code()==0:
                answer = send_msg(RR_duino.RR_duino_message.build_version_cmd(fullID_add[fullID]))
                if answer is not None and answer.get_error_code()==0:
                    #add the node to the online list
                    new_node = RR_duino_node(fullID_add[fullID],answer.get_version())
                    online_nodes[fullID]=new_node
    #for all online nodes, load their config: sensors and turnouts
    for fullID in online_nodes:
        n = online_nodes[fullID]
        n.get_config()
        
if len(sys.argv)>=2:
    config = load_config(sys.argv[1])
else:
    config = load_config("RR_duino_net_serial.cfg")

#connection to the serial bus
ser = serial_bus(config["serial_port"],config["serial_speed"])
debug("RR_duino_net_serial started on serial port",config["serial_port"])
connected = False
while not connected:
    try:
        ser.start()
        connected=True
    except serial.serialutil.SerialException:
        time.sleep(1)
        debug("Waiting to connect to serial port",config["serial_port"])
        pass
debug("Connected to serial port",config["serial_port"])

rcv_messages=""  #last received messages ready to be cut and decoded
rcv_RR_duino_messages = []  #decoded cmri messages received from the gateway, waiting to be sent
message_to_send=b""   #last incomplete message from the serial port
must_wait_answer = False  #this is True when the last message sent or being sent needs an answer (like Poll message)

time.sleep(1) #time for arduino serial port to settle down
gateway_ip = config["openlcb_gateway_ip"]
gateway_port = config["openlcb_gateway_port"]
s =socket.socket(socket.AF_INET,socket.SOCK_STREAM)

#load nodes from files and bring them online
#dict of fullID address correspondances
fullID_add = {}
#dict of fullID online node correspondances
online_nodes = {}
load_nodes()

#connect to gateway
connected = False
while not connected:
    try:
        s.connect((gateway_ip,gateway_port))
        connected = True
    except ConnectionError:
        print("connection error, retrying in 1 sec")
        time.sleep(1)
print("connected to gateway!")
s.settimeout(0)
#create or connect to existing cmri_net_bus
s.send(("RR_DUINO_NET_BUS cmri bus 1;").encode('utf-8'))

#FIXME: send all nodes to gateway

while True:
    buf=b""
    rcv_msg_list=[]
    try:
        buf=s.recv(200).decode('utf-8') #byte array: the raw cmri message
        debug(buf)
    except BlockingIOError:
        pass
    if len(buf)>0:
        rcv_messages+=buf
        debug("raw message=",buf)
        decode_messages()
        
    ser.process_IO()
    process()
    if ser.available():     # we are receiving an answer
        message_to_send += ser.read()

        if RR_duino.RR_duino_message.is_complete_message(message_to_send):
            #answer complete, send it to server
            debug("received from serial and sending it to the server:",(RR_duino.RRduino_message.raw_to_wire_message(message_to_send)+";").encode('utf-8'))
            s.send((RR_duino.RR_duino_message.raw_to_wire_message(message_to_send)+";").encode('utf-8'))
            #discard the part we just sent
            message_to_send=b""
            must_wait_answer = False
        
ser.close()
