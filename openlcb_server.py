import socket,select
from openlcb_protocol import *
import openlcb_server

class Client:
    """
    Basic client class: receives the msg from the server and "cut" them using the provided msg_separator
    """
    def __init__(self,sock,add,msg_separator):
        self.sock = sock
        self.address = add
        self.msgs = ""
        self.msg_separator = msg_separator
        
    def new_msg(self,msg):
        print("add ",msg," to client at ",self.address)
        self.msgs += msg

    #return the next msg (with the separator)
    #and erase it from the buffer
    def next_msg(self):
        msg,sep,end = self.msgs.partition(self.msg_separator)
        #print(msg, "/",sep,"/",end)
        if not sep:
            #print("sep!!")
            return ""
        print("next message from ",self.address,msg+sep)
        self.msgs = end
        return msg+sep

class Client_bus(Client):
    """
    Same as Client plus the fact that the first 20 characters must be a "bus" descriptor (padded with # if necessary)
    for example:"CMRI_NET_BUS#######"
    """
    BUS_NAME_LEN = 20
    BUS_NAME_PAD='#'

    def __init__(self,sock,add):
        super().__init__(sock,add,None) #initialize separator to None
        self.bus = None

    def next_msg(self):   #redefine to take the bus name
        if self.msg_separator is not None:
            return super().next_msg()
        if len(self.msgs)>=Client_bus.BUS_NAME_LEN:
            self.bus=openlcb_buses.Bus_manager.create(self)  #create a bus corresponding to the received bus name
            #the bus object is responsible for deleting the bus name from the client msgs field
        return ""
        
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
        
    def start(self):
        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serversocket.bind((self.address, self.port))
        print("gateway listening on ",self.address," at port ",self.port)

        # queue up to 5 requests
        self.serversocket.listen(5)

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
        print("Got a connection from", address)
        self.clients.append(client(clientsocket,address,";"))
        
    def deconnect_client(self,c):
        """
        deconnects the client
        """
       
        #Here you can add the name of the client who is deconnecting

        print("Client at ", c.address," is now deconnected!")

        #Here remember to clean the dictionaries
        self.clients.remove(c)
        c.sock.close()
        
    def wait_for_clients(self,timeout=0):
        #wait for data to be received
        #if there is a new connection, will take care of it
        #returns a list of sockets ready to be read
        
        to_read = [c.sock for c in self.clients]
        to_read.append(self.serversocket)
        #print("to_read:",to_read)
        ready_to_read,ready_to_write,in_error = select.select(to_read,[],[],timeout)

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
                print("recv error")
            print(len(m)," => ",m)
            if not m:
                #ready to read and empty msg means deconnection
                self.deconnect_client(c)
            else:
                print("new msg=",m)
                c.new_msg(m)

    def send_event(self,n,ev):
        for c in self.clients:   #FIXME
            c.sock.send(frame.build_PCER(n,ev).to_gridconnect())
            print("event sent by server = ",frame.build_PCER(n,ev).to_gridconnect())


class Buses_server(Openlcb_server):
    """
    buses server are registering the buses when a connection is made and the bus name is sent
    """
    def __init__(self,ip,port):
        super().__init__(ip,port)
        self.buses=[]
    
    def add_new_client(self):
        """
        A new client is connecting to the server
        """

        clientsocket,addr = self.serversocket.accept()
        address = (str(addr).split("'"))[1]
        print("Got a connection from", address)
        self.clients.append(client_bus(clientsocket,address))
