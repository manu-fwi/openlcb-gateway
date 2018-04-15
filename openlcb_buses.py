import socket,select
import openlcb_cmri_cfg as cmri
import serial
import openlcb_server
import openlcb_nodes

class Bus:
    def __init__(self,name):
        self.name = name
        self.clients=[]       #client programs connected to the bus

    def __str__(self):
        return "Bus: "+self.name

     
"""
class Cmri_bus(Bus):
    def __init__(self,port):
        super().__init__()
        self.port = port            #port is the way to connect to the bus (here port is the serial port path)
        self.ser_port = serial.Serial()
        self.ser_port.baudrate=9600
        self.write_timeout = None

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
"""        
     
class Cmri_net_bus(Bus):
    """
    message format (messages are separated by a ";", also number is presented as an hexdecimal string):
    - byte = number of bytes for the payload (excluding this number)
    - space separated (only ONE space) word and numbers/CMRI message (distinguished by the 2 SYN chars at the beginning)
    Message types (other than the CMRI message)
    - New node: "new_node" followed by its full ID (FIXME plus other info for the LCB node)
    and the format describing a cmri node (cf openlcb_cmri_cfg.py)
    - to be completed FIXME
    """
    separator = ";"
    def __init__(self):
        super().__init__(Bus_manager.cmri_net_bus_name)
        
    def process(self):
        #check all messages and return a list of events that has been generated in response
        ev_list=[]
        for c in self.clients:
            msg = c.next_msg()
            if not msg:
                continue
            print("received=",msg)
            msg=msg[:len(msg)-1]  #remove the trailing ";"
            if msg:
                msg.lstrip() #get rid of leading spaces
                words_list = msg.split(' ')
                try:
                    first_byte = int(words_list[0],16)
                except:
                    first_byte=None
                if first_byte==cmri.CMRI_message.SYN:
                    #it is a CMRI message, process it
                    node = openlcb_nodes.find_node_from_cmri_add(cmri.CMRI_message.UA_to_add(int(words_list[3],16)),c.managed_nodes)
                    if node is None:
                        print("Unknown node!!")
                    else:
                        node.cp_node.process_receive(cmri.CMRI_message.from_wire_message(msg))
                        ev_list.extend(node.generate_events())
                else:
                    #it is a bus message (new node...)
                    if msg.startswith("new_node"):
                        l = msg.split(' ')
                        cpnode=cmri.decode_cmri_node_cfg(l[2:])
                        if cpnode is not None:
                            cpnode.client = c
                            node = openlcb_nodes.Node_cpnode(int(l[1],16))    #full ID (Hex)
                            node.cp_node = cpnode
                            c.managed_nodes.append(node)
                    else:
                        print("unknown cmri_net_bus command")
                        
            #now poll all nodes
            for node in c.managed_nodes:
                node.poll()
        return ev_list

        
class Bus_manager:
    #buses names as received online
    
    cmri_net_bus_name = "CMRI_NET_BUS"
    cmri_net_bus_separator = ";"

    #list of active buses
    buses = []
    @staticmethod
    def create_bus(client,msg):
        """
        create a bus based on the name provided in the msgs field of the client
        returns True if bus has been found (or created if needed)
        False otherwise
        """
        if msg.startswith(Bus_manager.cmri_net_bus_name):
            #create a cmri_net bus
            bus = Bus_manager.find_bus_by_name(Bus_manager.cmri_net_bus_name)
            if bus == None:
                bus = Cmri_net_bus()
                Bus_manager.buses.append(bus)
                print("creating a cmri net bus")
            bus.clients.append(client)
            return True
        return False

    @staticmethod
    def find_bus_by_name(name):
        for b in Bus_manager.buses:
            if b.name == name:
                return b
        return None
            
