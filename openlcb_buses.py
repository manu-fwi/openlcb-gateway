import socket,select
import openlcb_cmri_cfg as cmri
import serial

class can_segment:
    def __init__(self,name):
        self.name = name
        self.nodes = []

    def push_datagram(self,dgram):
        if dgram.dest_node is None and dgram.dest_node in self.nodes:
            self.send_frame(dgram.to_can())

    def push_event(self,ev):
        for n in self.nodes:
            if ev in n.consumed_ev:
                self.send_frame(ev.to_can())
                return
            
    def send_frame(self,can_frame):
        #fixme to do!
        print("sending can frame",can_frame)

class cmri_bus:
    def __init__(self,port):
        self.port = port
        self.msg_queue =  []
        self.wait_answer = False
        self.recv_msgs = []
        self.ser_port = serial.Serial()
        self.ser_port.baudrate=9600
        self.write_timeout = None
        self.recv_buffer = b""

    def start(self,baudrate):
        self.ser_port.port = self.port
        self.ser_port.baudrate=baudrate
        if not self.ser_port.is_open:
            self.ser_port.open()

    def __str__(self):
        return "CMRI bus on port"+self.port

    def stop(self):
        if self.ser_port.is_open:
            self.ser_port.close()

    def send(self,msg):
        self.ser_port.write(msg)
        print("Written to serial port(",self.port,"):",msg)

    def recv(self): #return the msg of None if nothing is ready
        pass
        
    def pop_next_msg(self):
        if not self.recv_msgs:
            return None
        msg = self.recv_msgs.pop(0)
        self.wait_answer = False   #FIXME
        self.process_queue()
        print("pop next recv msg=",msg,len(self.recv_msgs))
        return cmri.CMRI_message.from_raw_message(msg)

    def process_queue(self):
        if not self.wait_answer and self.msg_queue:
            msg,must_wait = self.msg_queue.pop(0)
            print("unqueued=",msg.message,must_wait,self.msg_queue)
            self.send(msg.to_raw_message())
            print("test-cmri-bus sending to client:",msg.to_raw_message())
            self.wait_answer = must_wait
        
    def queue(self,msg,wait_answer):   #msg: cmri msg to queue to send
        self.msg_queue.append((msg,wait_answer))
        print("queued=",msg.to_raw_message(),wait_answer,self.msg_queue)
        self.process_queue()
        
    def process_answer(self):
        """
        Process incoming messages
        """

        msg = self.recv()
        if msg is not None:
            curr_pos = 0
            #print("msg=",msg,len(msg),end=" ")
            self.recv_buffer+=msg
            ETX_pos = cmri.CMRI_message.find_ETX(self.recv_buffer)
            while ETX_pos<len(self.recv_buffer):
                print(curr_pos,"ETX=",ETX_pos,end="/")
                self.recv_msgs.append(self.recv_buffer[:ETX_pos+1])
                print("appended new msg",self.recv_buffer)
                self.recv_buffer = self.recv_buffer[ETX_pos+1:]  #remove part already used
                ETX_pos = cmri.CMRI_message.find_ETX(self.recv_buffer)
            #print("after",self.recv_buffer,self.recv_msgs)
        
        
class cmri_net_bus(cmri_bus):
    def __init__(self,ip,port):
        super().__init__(port)
        self.ip = ip
        self.server = None

    def start(self):  #careful this is blocking until a test program connects to it
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((self.ip,self.port))
        self.server.listen(5)
        self.client,addr= self.server.accept()
        print("client (",addr,") connected to cmri_test_bus")

    def __str__(self):
        return "cmri_net_bus ("+str(self.ip)+","+str(self.port)+")"
    
    def stop(self):
        if self.server is not None:
            self.server.close()

    def send(self,msg):
        self.client.send(msg)

    def recv(self): #reads from socket: return msg or None if nothing is ready or deconnection occured
        ready_to_read,dummy,dummy = select.select([self.client],[],[],0)
        if self.client in ready_to_read:
            #if ready to read, read msgs and add them to the msgs list (cut them using ETX)
            msg = self.client.recv(200)
            print("cmri_net_bus rcv=",msg)
            if len(msg)==0:
                print("empty msg, deconnection")
                self.client.close()
                return None
            else:
                return msg
        
