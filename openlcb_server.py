import socket,select
from openlcb_protocol import *
import openlcb_server
import openlcb_buses
from openlcb_debug import *

class Client:
    """
    Basic client class: receives the msg from the server and "cut" them using the provided msg_separator
    """
    def __init__(self,sock,add,msg_separator):
        self.sock = sock
        self.address = add
        self.msgs = ""
        self.msg_separator = msg_separator

    def receive(self):
        return self.sock.recv(200).decode('utf-8')
    
    def new_msg(self,msg):
        #debug("add ",msg," to client at ",self.address)
        self.msgs += msg

    #return the next msg (with the separator)
    #and erase it from the buffer
    def next_msg(self):
        msg,sep,end = self.msgs.partition(self.msg_separator)
        if not sep:
            #print("sep!!")
            return ""
        #debug("next message from ",self.address,msg+sep)
        self.msgs = end
        #debug("remaining messages",end)
        return msg+sep

    def queue(self,cmd):
        #debug("client sending",cmd)
        self.sock.send(cmd+";".encode('utf-8'))

class Client_bus(Client):
    """
    Same as Client plus the fact that the first line must be a "bus" descriptor plus the client name(cf openlcb_buses.py)
    """
    def __init__(self,sock,add,path_to_nodes_files = None):
        super().__init__(sock,add,openlcb_buses.Bus.BUS_MSG_SEPARATOR)
        self.bus = None
        self.managed_nodes=[]
        self.path_to_nodes_files=path_to_nodes_files

    def check_bus_name(self):
        """
        check if the client has sent the bus name to connect it to the correct bus object
        returns True if client has been connected to a bus, False otherwise
        """
        msg = self.next_msg()
        if msg:
            bus_name,sep,end = msg.partition(" ")
            name = end[:-1]      #get rid of the separator
            self.name = name
            #create a bus corresponding to the received bus name
            bus= openlcb_buses.Bus_manager.create_bus(self,bus_name,self.path_to_nodes_files)
            self.bus=bus
            return bus is not None
        
def get_client_from_socket(clients,sock):
    for c in clients:
        if c.sock == sock:
            return c
    return None
        
class Openlcb_server:
    """
    This class gives all the tools to handle openlcb connections to the gateway
    """

    def __init__(self, address, port):
        self.address = address
        self.port = port
        self.clients = []
        self.internal_sock = None
        
    def start(self):
        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serversocket.bind((self.address, self.port))
        debug("gateway listening on ",self.address," at port ",self.port)

        # queue up to 5 requests
        self.serversocket.listen(5)

        #this socket enables us to send openlcb packets to everyone (buses or exterior openlcb network
        self.internal_sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.internal_sock.connect((self.address,self.port))
        
    def stop(self):
        self.serversocket.close()

    def connections(self):
        return len(self.clients)

    def add_new_client(self):
        """
        A new client is connecting to the server
        """

        clientsocket,addr = self.serversocket.accept()
        address = (str(addr).split("'"))[1]
        debug("Got a connection from", address)
        self.clients.append(Client(clientsocket,address,";"))
        
    def deconnect_client(self,c):
        """
        deconnects the client
        """
        debug("Client at ", c.address," is now deconnected!")

        #FIXME: need to clean up all clients connected via this client
        self.clients.remove(c)
        c.sock.close()
        
    def wait_for_clients(self,timeout=0):
        #wait for data to be received
        #if there is a new connection, will take care of it
        #returns a list of sockets ready to be read
        
        to_read = [c.sock for c in self.clients]
        to_read.append(self.serversocket)
        ready_to_read,ready_to_write,in_error = select.select(to_read,[],[],timeout)
        if self.internal_sock in ready_to_read:
            debug("received from internal sock!!")

        if self.serversocket in ready_to_read:
            self.add_new_client()
            ready_to_read.remove(self.serversocket)

        return ready_to_read

    def process_reads(self,ready_to_read):
        for s in ready_to_read:
            m=""
            c = get_client_from_socket(self.clients,s)
            try:
                m = s.recv(200).decode('utf-8')
            except socket.error:
                debug("recv error")
            #debug(len(m)," => ",m)
            if not m:
                #ready to read and empty msg means deconnection
                self.deconnect_client(c)
            else:
                #debug("new msg=",m)
                c.new_msg(m)

    #send a frame (CID or event for ex) to all clients of the server but the emitter (if not None)
    def send(self,ev_or_frame,cli_emitter=None):
        self.transfer(ev_or_frame.to_gridconnect(),cli_emitter)

    #transfer a frame (same as send but here we take the gridconnect encoded string
    #instead of the Frame/Event object
    def transfer(self,frame_gridconnect,cli_emitter=None):
        for c in self.clients:   #FIXME we may need to buffer this instead of just sending right away??
            if c!=cli_emitter:
                c.sock.send(frame_gridconnect)
                debug("event/frame transferred by server = ",frame_gridconnect)
        

class Buses_server(Openlcb_server):
    """
    buses server are registering the buses when a connection is made and the bus name is sent
    """
    def __init__(self,ip,port,path_to_nodes_files):
        super().__init__(ip,port)
        self.unconnected_clients = []
        self.path_to_nodes_files = path_to_nodes_files
    
    def add_new_client(self):
        """
        A new client is connecting to the server
        """

        clientsocket,addr = self.serversocket.accept()
        address = (str(addr).split("'"))[1]
        debug("Got a connection to bus from", address)
        c = Client_bus(clientsocket,address,self.path_to_nodes_files)
        self.clients.append(c)
        self.unconnected_clients.append(c)

    def deconnect_client(self,c):
        """
        deconnects the client
        """
        debug("Client at ", c.address," is now deconnected!")

        #FIXME: need to clean up all clients connected via this client
        self.clients.remove(c)
        if c in self.unconnected_clients:
            self.unconnected_clients.remove(c)
            #nothing else to do, no node has been attached via this client yet
            return
        #clean the corresponding bus
        c.bus.clients.remove(c)
        c.sock.close()
