import socket,select,threading
from openlcb_gateway import *

#protocols definitions
SPSP   = 0x800000 # Simple Protocol subset
DGP    = 0x400000 # Datagram Protocol
STP    = 0x200000 # Stream Protocol
MCP    = 0x100000 # Memory Configuration Protocol
RP     = 0x080000 # Reservation Protocol
EEP    = 0x040000 # Event Exchange (Producer/Consumer) Protocol
IDP    = 0x020000 # Identification Protocol
TLCP   = 0x010000 # Teaching/Learning Configuration Protocol
RBP    = 0x008000 # Remote Button Protocol
ADCDIP = 0x004000 # Abbreviated Default CDI Protocol
DP     = 0x002000 # Display Protocol
SNIP   = 0x001000 # Simple Node Information Protocol
CDIP   = 0x000800 # Configuration Description Information (CDI)
TCP    = 0x000400 # Traction Control Protocol (Train Protocol)
FDIP   = 0x000200 # Function Description Information (FDI)
DCCCSP = 0x000100 # DCC Command Station Protocol
STNIP  = 0x000080 # Simple Train Node Information Protocol
FCP    = 0x000040 # Function Configuration
FUP    = 0x000020 # Firmware Upgrade Protocol
FUAP   = 0x000010 # Firmware Upgrade Active

memory = {0:mem_space([(128,32),(160,96),(256+128,8),(256+128+8,8),(256+128+2*8,8),(256+128+3*8,8),(256+128+4*8,2)])}
memory[0].set_mem(128,b"gw1"+b"\0"*(32-3))
memory[0].set_mem(160,b"gateway-1"+b"\0"*(96-9))
#memory[0].update_mem(384,b"01234567")
#memory[0].update_mem(392,b"12345678")
#memory[0].update_mem(400,b"23456789")
#memory[0].update_mem(408,b"3456789A")
#memory[0].update_mem(416,b"BC")

print(memory[0].read_mem(128))
if memory[0].read_mem(450) is None:
    print("OK!")

current_write=None

mfg_name_hw_sw_version=["\4python gateway","test","1.0","1.0","\2gw1","gateway-1"]

acdi_xml="""<?xml version="1.0"?>
<?xml-stylesheet type="text/xsl" href="xslt/cdi.xsl"?>
<cdi xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://openlcb.org/trunk/prototypes/xml/schema/cdi.xsd">

<identification>
    <manufacturer>python gateway</manufacturer>
    <model>test</model>
    <hardwareVersion>1.0</hardwareVersion>
    <softwareVersion>1.0</softwareVersion>
    <map>
        <relation><property>Size</property><value>8 cm by 12 cm</value></relation>
    </map>
</identification>

<segment origin="0" space="0">
    <group offset="128">
        <name>User Identification</name>
        <description>Lets the user add his own description</description>
        <string size="32">
            <name>Name</name>
        </string>
    </group>
</segment>
</cdi>\0"""

acdi_xml2="""<?xml version="1.0"?>
<?xml-stylesheet type="text/xsl" href="xslt/cdi.xsl"?>
<cdi xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://openlcb.org/trunk/prototypes/xml/schema/cdi.xsd">

<identification>
    <manufacturer>python gateway</manufacturer>
    <model>test</model>
    <hardwareVersion>1.0</hardwareVersion>
    <softwareVersion>1.0</softwareVersion>
    <map>
        <relation><property>Size</property><value>8 cm by 12 cm</value></relation>
    </map>
</identification>

<segment origin="0" space="0">
    <group offset="128">
        <name>User Identification</name>
        <description>Lets the user add his own description</description>
        <string size="32">
            <name>Name</name>
        </string>
        <string size="96">
            <name>Description</name>
        </string>
    </group>
    <group offset="128" replication="2">
        <name>Produced Events</name>
        <description>The EventIDs for the producers</description>
        <eventid/>
        <eventid/>
    </group>
    <group replication="2">
        <name>Consumed Events</name>
        <description>The EventIDs for the consumers</description>
        <eventid/>
        <eventid/>
    </group>
    <int size="2">
        <name>Sample integer variable</name>
        <description>Doesn't do anything</description>
        <min>1</min>
        <max>999</max>
        <default>12</default>
    </int>
</segment>
</cdi>\0"""

acdi_xml2="""<?xml version="1.0"?>
<cdi>
<identification>
    <manufacturer>python gateway</manufacturer>
    <model>test</model>
    <hardwareVersion>1.0</hardwareVersion>
    <softwareVersion>1.0</softwareVersion>
</identification>
<segment space=\"0\">
    <group>
        <name>Produced Events</name>
        <description>The EventIDs for the producers</description>
        <eventid>
        <name>Test 1</name>
        </eventid>
    </group>
    <group>
        <name>Consumed Events</name>
        <description>The EventIDs for the consumers</description>
        <eventid>
        <name>Test 2</name>
        </eventid>
    </group>
</segment>
</cdi>
\0"""

def broadcast(orig_sock, msg):
    """
    Send msg to all clients of the clients list but orig_sock
    """
    for s in clients_read_list:
        if s!=orig_sock and s!=serversocket:
            try:
                s.send(msg.encode('utf-8'))
            except socket.error:
                print("error while sending")

def get_clients_ready():
    """
    return a list of clients who have sent something, needing to be read then
    """

    ready_to_read,ready_to_write,in_error = select.select(clients_read_list,[],[],0)
    return ready_to_read

def add_new_client():
    """
    A new client is connecting to the server
    """

    clientsocket,addr = serversocket.accept()
    address = (str(addr).split("'"))[1]
    print("Got a connection from %s" % address)
    clients_read_list.append(clientsocket)

    #Here remember to update the dictionary (ies)
    clients_sockets[clientsocket] = address

def deconnect_client(sock):
    """
    deconnects the client
    """
    global clients_read_list,clients_sockets,clients_names

    for s,a in clients_sockets.items():
        if s==sock:

            #Here you can add the name of the client who is deconnecting

            deconn = "Client at " + a+ " is now deconnected!"
            print(deconn)
            broadcast(sock, deconn)
            break

    #Here remember to clean the dictionaries
    del clients_sockets[sock]
    clients_read_list.remove(sock)
    sock.close()

timeouts = []
def timeout_end(index):

    timeouts[index]=2 #2 means it has expired
    
def set_timeout(value):
    global timeouts

    i=0
    for i in range(len(timeouts)):
        if timeouts[i]==0: #unused, use it
            break
    if i==len(timeouts):
        timeouts.append(1)  #1 means timeout is running
    t = threading.Timer(value,timeout_end,[i])
    t.start()
    return i

def check_timeout(index):
    if timeouts[index]==2:
        timeouts[index]=0
        return True
    return False

def send_fields(MTI,fields,dest):
    fields_bytes = [i.encode("utf-8") for i in fields]
    send_long_message(MTI,b"\0".join(fields_bytes),dest)

def send_long_message(MTI,text,dest): #text must be a byte array
    s=list(clients_sockets.keys())[0]
    pos = 0
    last=False
    first=True
    while not last:
        msg = b":X19A08AAAN"
        if pos+6>len(text):
            last=True
            if not first:
                msg+=b"2"  #last frame
            else:
                msg+=b"0"  #only one frame
        else:
            if not first:
                msg+=b"3"  #middle frame
            else:
                msg+=b"1"  #first frame
            first = False
        msg+=hexp(dest,3).encode("utf-8")
        #print("pos=",pos,"len=",len(text),"txt=",text[pos:min(pos+6,len(text))])
        for c in text[pos:min(pos+6,len(text))]:
            msg+=hexp(c,2).encode("utf-8")
        if last:
            msg+=hexp(0,2*(pos+6-len(text))).encode("utf-8") #pad with zero bytes
        msg+=b";"
        print("sent SNRI-->",msg)
        s.send(msg)
        pos+=6

def convert_to_hex(buf): #return bytes array
    res=b""
    for c in buf.encode("utf-8"):
        res+=hexp(c,2).encode("utf-8")
    return res

def convert_to_hex_b(buf): #return bytes array
    res=b""
    for c in buf:
        res+=hexp(c,2).encode("utf-8")
    return res

def send_datagram_multi(s,src_id,reply,buf,first_payload):
    #exaclty send the byte buffer buf: must be null terminated if it is a string

    msg = b":X1"
    if len(buf)<=first_payload:
        msg+=b"A"
    else:
        msg+=b"B"
    msg+=hexp(src_id,3).encode('utf-8')+b"AAAN"+reply
    msg+=convert_to_hex_b(buf[:first_payload])+b";"
    print("datagram sent >>",msg," = ",buf[:first_payload])
    s.send(msg)
    #Now the rest of the data

    pos = first_payload
    while pos<len(buf) and pos<64:
        if pos+8<len(buf) and pos+8<64: #more than enough remaining
            msg=b":X1C"
            end=pos+8
        else:
            msg=b":X1D"  #last frame
            end = min(64,len(buf))
                
        msg+=hexp(src_id,3).encode("utf-8")+b"AAAN"
        msg+=convert_to_hex_b(buf[pos:end])+b";"
        msg2=buf[pos:end]
        pos+=8
        s.send(msg)
        print("datagram sent >>",msg," = ",msg2)
    
def send_CDI(s,src_id,address):
    msg = b":X1"
    msg+=b"B"+hexp(src_id,3).encode("utf-8")+b"AAAN2053"
    msg+=hexp(address,8).encode("utf-8")
    msg+=convert_to_hex(acdi_xml[address:address+2])+b";"
    print("datagram sent >>",msg," = ",acdi_xml[address:address+2])
    s.send(msg)
    #Now the rest of the data

    pos = 2
    while address+pos<len(acdi_xml) and pos<64:
        if address+pos+8<len(acdi_xml) and pos+8<64: #more than enough remaining
            msg=b":X1C"
            end=address+pos+8
        else:
            msg=b":X1D"  #last frame
            end = min(address+64,len(acdi_xml))
                
        msg+=hexp(src_id,3).encode("utf-8")+b"AAAN"
        msg+=convert_to_hex(acdi_xml[address+pos:end])+b";"
        msg2=acdi_xml[address+pos:end]
        pos+=8
        s.send(msg)
        print("datagram sent >>",msg," = ",msg2)

def memory_read(s,src_id,add,buf):
    global memory

    s.send(b":X19A28AAAN8"+hexp(src_id,3).encode("utf-8")+b";")
    print("datagram received ok sent --->",b":X19A28AAAN8"+hexp(src_id,3).encode("utf-8")+b";")

    if buf[13:15]=="40":
        mem_sp = int(float.fromhex(buf[23:25]))
        size = int(float.fromhex(buf[25:27]))
        m = hexp(mem_sp,2).encode('utf-8')
        first_payload=1
    else:
        mem_sp = 0xFC+int(buf[14])
        size=int(float.fromhex(buf[23:25]))
        m = b""
        first_payload=2
    to_send= memory[mem_sp].read_mem(add)
    if to_send is None:
        print("error memory unknown")
    else:
        send_datagram_multi(s,src_id,b"205"+buf[14].encode('utf-8')+hexp(add,8).encode('utf-8')+m,
                            to_send[:size],first_payload)

def memory_write(s,src_id,add,buf):
    global memory,current_write

    print("memory write")
    if buf[3]=="A" or buf[3]=="B":
        if buf[14]=="0":
            mem_sp = int(float.fromhex(buf[23:25]))
            data_beg=25
        else:
            mem_sp = 0xFC+int(buf[14])
            data_beg=23
        current_write=(mem_sp,add)
        s.send(b":X19A28AAAN0"+hexp(src_id,3).encode("utf-8")+b";")
        print("datagram received ok sent --->",b":X19A28AAAN8"+hexp(src_id,3).encode("utf-8")+b";")
    else:
        data_beg=11
    if current_write is None:
        print("write error: current_write is none!!")
    else:
        res=b""
        for pos in range(data_beg,len(buf)-1,2):
            print(buf[pos:pos+2])
            res+=bytes([int(float.fromhex(buf[pos:pos+2]))])
        print("written:",res)
        memory[current_write[0]].set_mem_partial(current_write[1],res)
    if buf[3]=="A" or buf[3]=="D":
        current_write = None

def debug_frame(buf):
    print("Frame=",buf)
    if buf[:2]!=":X":
        print("not extended can frame!!")
        return False
    if buf[10]!="N":
        print("Not a normal frame!!")
    data_present = buf[11]!=";"

    print("Header:",end=" ")
    print(buf[2:10],end=" ")
    first_b = int(float.fromhex(buf[2:4]))
    can_prefix = (first_b & 0x18) >> 3
    print("CAN Prefix=",can_prefix," * Frame type =",first_b & 0x07,end=" * ")
    var_field = int(float.fromhex(buf[4:7]))
    print("MTI/Dest nodeID Alias=",hex(var_field),end="  * ")
    src_id = int(float.fromhex(buf[7:10]))
    print("sourceID=",hex(src_id))

def can_control(s,buf):
    first_b = int(float.fromhex(buf[2:4]))
    var_field = int(float.fromhex(buf[4:7]))
    if first_b & 0x7>=4 and first_b & 0x7<=7:
        print("CID Frame n°",first_b & 0x7," * ",hex(var_field),end=" * 0x")
        full_ID |= var_field << 12*((first_b&0x7) -4)
    elif first_b&0x7==0:
        if var_field==0x700:
            print("RID Frame * full ID=",hex(full_ID),end=" * ")
        elif var_field==0x701:
            print("AMD Frame",end=" * ")
            data_needed = True
        elif var_field==0x702:
            print("AME Frame",end=" * ")
            data_nedded=True
        elif var_field==0x703:
            print("AMR Frame",end=" * ")
            data_nedded=True
        elif var_field>=0x710 and var_field<=0x713:
            print("Unknown Frame",end=" * ")
            src_id = int(float.fromhex(buf[7:10]))
            print(hexp(src_id,3))

def frame_msg(s,buf):
    if var_field==0x490:  #Verify node ID
        s.send((":X19170AAAN"+hexp(gatewayID,12)+";").encode("utf-8"))
        print("Sent---> :X19170AAAN"+hexp(gatewayID,12)+";")
    elif var_field==0x828:#Protocol Support Inquiry
        dest_node = int(float.fromhex(buf[12:15]))
        if dest_node==alias:
            s.send((":X19668AAAN0"+hexp(src_id,3)+hexp(SPSP|SNIP|CDIP,6)+"000000;").encode("utf-8"))
            print("sent--->:X19668AAAN0"+hexp(src_id,3)+hexp(SPSP|SNIP|CDIP,6)+"000000;")

    elif var_field == 0xDE8:#Simple Node Information Request

        dest_node = int(float.fromhex(buf[12:15]))
        if dest_node==alias:
            print("sent SNIR Reply")
            #s.send((":X19A08AAAN1"+hexp(src_id,3)+"04;").encode("utf-8"))#SNIR header
            #print(":X19A08AAAN1"+hexp(src_id,3)+"04;")
            send_fields(0xA08,mfg_name_hw_sw_version,src_id)

            #s.send((":X19A08AAAN3"+hexp(src_id,3)+"02;").encode("utf-8"))#SNIR header
            #print(":X19A08AAAN3"+hexp(src_id,3)+"02;")
            #send_fields(0xA08,username_desc,src_id,True)

def datagram(s,buf):
    address = int(float.fromhex(buf[15:23]))
    print("datagram!!")
    #for now we assume a one frame datagram
    if var_field!=alias: #not for us
        print("not for us!!")
        return
    print(buf[11:13])
    if current_write is not None:
        memory_write(s,src_id,address,buf)
        if buf[11:15]=="2043": #read command for CDI
            print("read command, address=",int(float.fromhex(buf[15:23])))
            s.send(b":X19A28AAAN8"+hexp(src_id,3).encode("utf-8")+b";")
            print("datagram received ok sent --->",b":X19A28AAAN8"+hexp(src_id,3).encode("utf-8")+b";")
            send_CDI(sock,src_id,address)
        elif buf[11:13]=="20": #read/write command
            if buf[13]=="4":
                memory_read(s,src_id,address,buf)
            elif buf[13]=="0":
                memory_write(s,src_id,address,buf)

def parse(s,buf):
    global full_ID,jmri_identified,snir_step
    
    if not debug_frame(buf):
        return

    can_prefix = (first_b & 0x18) >> 3
    if can_prefix % 2==0:
        #Can Control frame
        can_control(s,buf)
    else:
        if (first_b & 0x7)==1:  #global or addressed frame msg
            frame_msg(s,buf)
            
        elif (first_b & 0x7)>=2 and (first_b & 0x7)<=5: #Datagram
            
def hexp(i,width):
    s=hex(i)[2:].upper()
    return "0"*(width-len(s))+s

def identify(id_step):
    global gatewayID,id_timeout
    s=list(clients_sockets.keys())[0]

    message=":X1"
    if id_step >3:
        message +=str(id_step)+hexp((gatewayID >> (id_step-4)*12)&0x0FFF,3)
    else:
        if id_timeout<0:
            id_timeout = set_timeout(0.2)
            return False
        if not check_timeout(id_timeout):
            return False
        message += "0700"
    message+="AAAN;"
    s.send(message.encode("utf-8"))
    print("Sent ---> ",message)
    return True
    
gatewayID = 0x020112AAAAAA
alias = 0xAAA
snir_step = 4

#create server socket
serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# get local machine name
host = "127.0.0.1" #socket.gethostbyname(socket.gethostname())
port = int(input("port?"))

# bind to the port
serversocket.bind((host, port))
print("gateway listening on ",host," at port ",port)

# queue up to 5 requests
serversocket.listen(5)

#clients_read_list: should contain all clients sockets
#contains also the server socket the clients use to connect to the server
clients_read_list=[serversocket]

#dictionary of pairs:(socket,address)
clients_sockets = {}
full_ID = 0
id_step = 7
identified = jmri_identified = False
id_timeout = -1
print(acdi_xml)
while True:
    if len(clients_sockets)>0:
        if not identified and jmri_identified:
            if identify(id_step):
                id_step-=1
            if id_step == 2:
                #send Initialization complete
                identified = True
                s=list(clients_sockets.keys())[0]
                #send AMD
                s.send((":X10701AAAN"+hexp(gatewayID,12)+";").encode("utf-8"))
                #send INIT completion
                s.send((":X1910AAAN"+hexp(gatewayID,12)+";").encode("utf-8"))
        if identified:
            pass
    ready_to_read = get_clients_ready()
    for sock in ready_to_read:
        #if the serversocket is ready to be read that means someone
        #is trying to connect
        if sock == serversocket:
            add_new_client()
        else:
            #else someone is sending a message
            try:
                buf = sock.recv(200).decode('utf-8')
            except socket.error:
                print("recv error")
                buf = ""
            if not buf:
                #if the message is empty that means the client is deconnecting
                deconnect_client(sock)
            else:
                lines = buf.split(";")
                for l in lines:
                    if l!="":
                        parse(sock,l+";")


