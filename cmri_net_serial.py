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
#connection to the gateway
ser = serial_bus("/dev/ttyUSB0",9600)
ser.start()
time.sleep(1)
gateway_ip = "127.0.0.1"
gateway_port = 50010
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

while True:
    buf=b""
    try:
        buf=s.recv(200) #byte array: the raw cmri message
    except BlockingIOError:
        pass
    if len(buf)>0:
        print("raw message=",buf)
        ser.send(buf)
    ser.process_IO()
    if ser.available():
        m = ser.read()
        print("back=",m)
        s.send(m)
        
ser.close()
