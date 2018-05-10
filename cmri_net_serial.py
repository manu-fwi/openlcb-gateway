import openlcb_cmri_cfg as cmri
import socket,time
import serial

class serial_bus:
    def __init__(self,port,baudrate):
        self.ser_port = serial.Serial()
        self.ser_port.port = port
        self.ser_port.bnaudrate = baudrate
        self.ser_port.timeout=0
        self.ser_port.write_timeout = 0
        self.to_send=b""
        self.to_send_pos=0
        self.rcv_buffer = b""

    def start(self):
        if not self.ser_port.is_open:
            self.ser_port.open()
    def stop(self):
        if self.ser_port.is_open:
            self.ser_port.close()

    def send(self,msg): #msg must be bytes array
        if len(self.to_send)>0:
            print("overrun of the sending buffer")
        self.to_send=msg

    def sending(self):
        return len(self.to_send)>0

    def read(self):
        if len(self.rcv_buffer)>0:
            res = self.rcv_buffer
            self.rcv_buffer = b""
            return res
        else:
            return None

    def available(self):
        return len(self.rcv_buffer)
    
    def process_IO(self):
        global count
        if self.to_send:  #still sending
            print("sending msg=",self.to_send[self.to_send_pos:])
            if self.to_send_pos < len(self.to_send):
                try:
                    nb = self.ser_port.write(self.to_send[self.to_send_pos:])
                    self.to_send_pos += nb
                except BaseException:
                    pass
            else:
                self.to_send = b""
                self.to_send_pos = 0
        else:   #see if we have received something
            try:
                self.rcv_buffer +=  self.ser_port.read()
            except BaseException:
                pass

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
    
#connection to the gateway
ser = serial_bus("/dev/ttyUSB0",9600)
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
gateway_ip = "127.0.0.1"
gateway_port = 50001
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
s.send(("CMRI_NET_BUS cmri bus 1;").encode('utf-8'))
s.send(("start_node 20112AAAAAA;").encode('utf-8'))
while True:
    buf=b""
    rcv_msg_list=[]
    try:
        buf=s.recv(200).decode('utf-8') #byte array: the raw cmri message
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
