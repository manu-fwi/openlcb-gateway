import socket,select
import openlcb_cmri_cfg as cmri

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
        
class cmri_test_bus:
    def __init__(self,ip,port):
        self.ip = ip
        self.port = port
        self.server = None
        self.msg_queue =  []
        self.wait_answer = False
        self.recv_msgs = []
        self.last_recv_complete=True

    def start(self):  #careful this is blocking until a test program connects to it
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((self.ip,self.port))
        self.server.listen(5)
        self.client,addr= self.server.accept()
        print("client (",addr,") connected to cmri_test_bus")

    def __str__(self):
        return "test-cmri-bus ("+str(self.ip)+","+str(self.port)+")"
    
    def stop(self):
        if self.server is not None:
            self.server.close()

    def pop_next_msg(self):
        if not self.recv_msgs:
            return None
        msg = self.recv_msgs.pop(0)
        self.wait_answer = (len(self.recv_msgs)>0)   #FIXME: crude but should work for cmri as it is one answer per request
        print("pop next recv msg=",msg.message,len(self.recv_msgs))
        return msg
    
    def process_answer(self):
        """
        Process incoming messages
        """
        if not self.wait_answer:
            return

        ready_to_read,dummy,dummy = select.select([self.client],[],[],0)
        if self.client in ready_to_read:
            #if ready to read, read msgs and add them to the msgs list (cut them using ETX)
            msg = self.client.recv(200)
            if len(msg)==0:
                print("empty msg, deconnection")
                self.client.close()
            curr_pos = 0
            while curr_pos<len(msg):
                ETX_pos = cmri.CMRI_message.find_ETX(msg[curr_pos:])

                if self.last_recv_complete:  #last msg complete, so add new msg (up to ETX)
                    self.recv_msgs.append(cmri.CMRI_message.from_raw_message(msg[curr_pos:ETX_pos+1]))
                else:  #last msg incomplete so complete it
                    self.msgs[len(self.msgs)-1]+=msg[curr_pos:ETX_pos]

                self.last_recv_complete= (ETX_pos < len(msg))
                curr_pos=ETX_pos+1
        
    def queue(self,msg,wait_answer):   #msg: cmri msg to queue to send
        self.msg_queue.append((msg,wait_answer))
        print("queued",len(self.msg_queue))
        if not self.wait_answer:
            msg,must_wait = self.msg_queue.pop(0)
            self.client.send(msg.to_raw_message())
            print("test-cmri-bus sending to client:",msg.to_raw_message())
            self.wait_answer = must_wait
        
