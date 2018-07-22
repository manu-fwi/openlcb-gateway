import openlcb_cmri_cfg as cmri
import socket,time
from openlcb_serial_bus import *
import json,sys
from openlcb_debug import *


def decode_messages():
    global rcv_messages,rcv_cmri_messages

    sep = ";"
    print(rcv_messages)
    while sep==";":
        first,sep,end = rcv_messages.partition(";")
        print(first,"/",sep,"/",end)
        if sep!="":
            rcv_cmri_messages.append(cmri.CMRI_message.from_wire_message(first))
            rcv_messages = end

def process():
    global rcv_cmri_messages,ser,must_wait_answer

    if ser.sending() or must_wait_answer:  #if we are already sending or waiting for an answer
        #not much we can do, let's wait for IO to proceed
        return
    #no IO occuring let's begin a new one if there is any

    if not rcv_cmri_messages:
        return
    print("start IO")
    msg = rcv_cmri_messages.pop(0)
    ser.send(msg.to_raw_message())
    must_wait_answer = (msg.type_m == cmri.CMRI_message.POLL_M)

def load_config(filename):
    #Load config file (json formatted dict config, see below)
    #
    #
    #
    #
    with open(filename) as cfg_file:
        config = json.load(cfg_file)
    #plug reasonable default values for secondary parameters
    if "serial_speed" not in config:
        config["serial_speed"]=9600
    if "openlcb_gateway_ip" not in config:
        config["openlcb_gateway_ip"]="127.0.0.1"
    if "openlcb_gateway_port" not in config:
        config["openlcb_gateway_port"]=50001
    if "nodes_ID_filename" not in config:
        config["nodes_ID_filename"]="cmri_net_serial_nodes_ID.cfg"
    
    return config

if len(sys.argv)>=2:
    config = load_config(sys.argv[1])
else:
    config = load_config("cmri_net_serial.cfg")
#connection to the gateway
ser = serial_bus(config["serial_port"],config["serial_speed"])
debug("cmri_net_serial started on serial port",config["serial_port"])
connected = False
while not connected:
    try:
        ser.start()
        connected=True
    except serial.serialutil.SerialException:
        pass
rcv_messages=""  #last received messages ready to be cut and decoded
rcv_cmri_messages = []  #decoded cmri messages received from the gateway, waiting to be sent
message_to_send=b""   #last incomplete message from the serial port
must_wait_answer = False  #this is True when the last message sent or being sent needs an answer (like Poll message)

time.sleep(1) #time for arduino serial port to settle down
gateway_ip = config["openlcb_gateway_ip"]
gateway_port = config["openlcb_gateway_port"]
s =socket.socket(socket.AF_INET,socket.SOCK_STREAM)
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
s.send(("CMRI_NET_BUS cmri bus 1;").encode('utf-8'))
#read and add the nodes we want to manage
for fullID in config["nodes_ID_list"]:
    s.send(("start_node "+str(fullID)+";").encode('utf-8'))
    
while True:
    buf=b""
    rcv_msg_list=[]
    try:
        buf=s.recv(200).decode('utf-8') #byte array: the raw cmri message
        print(buf)
    except BlockingIOError:
        pass
    if len(buf)>0:
        rcv_messages+=buf
        print("raw message=",buf)
        decode_messages()
        
    ser.process_IO()
    process()
    if ser.available():     # we are receiving an answer
        message_to_send += ser.read()

        ETX_pos=cmri.CMRI_message.find_ETX(message_to_send)
        if ETX_pos<len(message_to_send):
            #answer complete, send it to server
            print("received from serial and sending it to the server:",(cmri.CMRI_message.raw_to_wire_message(message_to_send[:ETX_pos+1])+";").encode('utf-8'))
            s.send((cmri.CMRI_message.raw_to_wire_message(message_to_send[:ETX_pos+1])+";").encode('utf-8'))
            #discard the part we just sent
            message_to_send=message_to_send[ETX_pos+1:]
            must_wait_answer = False
        
ser.close()
