import socket,select
from openlcb_protocol import *

class client:
    def __init__(self,sock,add):
        self.sock = sock
        self.address = add
        self.msgs = "" 
    def new_msg(self,msg):
        print("add ",msg," to client at ",self.address)
        self.msgs += msg

    #return the next msg (with the separator)
    #and erase it from the buffer
    def next_msg(self,separator):
        msg,sep,end = self.msgs.partition(separator)
        #print(msg, "/",sep,"/",end)
        if not sep:
            #print("sep!!")
            return ""
        print("next message from ",self.address,msg+sep)
        self.msgs = end
        return msg+sep

def get_client_from_socket(clients,sock):
    for c in clients:
        if c.sock == sock:
            return c
    return None
        
class server:
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
        self.clients.append(client(clientsocket,address))
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
                m = s.recv(200).decode('utf+8')
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
