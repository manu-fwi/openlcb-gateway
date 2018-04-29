import openlcb_cmri_cfg as cmri
import openlcb_buses as buses
import openlcb_server
from openlcb_nodes import *
from openlcb_protocol import *
import socket,select,time
from collections import deque
        

def get_alias_neg_from_alias(alias):
    found = None
    for n in list_alias_neg:
        if n.aliasID == alias:
            found = n
            break
    return found

def send_fields(sock,src_node,MTI,fields,dest_node):
    frames = create_addressed_frame_list(src_node,dest_node,MTI,("\0".join(fields)).encode('utf-8'),True)
    for f in frames:
        sock.send(f.to_gridconnect())
        print("--->",f.to_gridconnect().decode('utf-8'))

def send_CDI(s,src_node,dest_node,address,size):
    data = bytearray((0x20,0x53))
    data.extend(address.to_bytes(4,'big'))
    data.extend(bytearray(src_node.get_CDI()[address:address+size],'utf-8'))
    print(src_node.get_CDI())
    dgrams=create_datagram_list(src_node,dest_node,data)
    for d in dgrams:
        s.send(d.to_gridconnect())

def memory_read(s,src,dest,add,msg):   #msg is mem read msg as string
    to_send=bytearray()

    if msg[13:15]=="40":
        mem_sp = int(msg[23:25],16)
        size = int(msg[25:27],16)
        mem_sp_separated = True
    else:
        mem_sp = 0xFC+int(msg[14])
        size=int(msg[23:25],16)
        mem_sp_separated = False
    print("memory read at",mem_sp,"offset",add,"size",size)
    if mem_sp not in src.memory:
        print("memory unknown!!")
        return
    mem = src.read_mem(mem_sp,add)
    print("memory read sends:",mem)
    if mem is None:
        print("memory error")
    else:
        to_send2= bytearray((0x20,int("5"+msg[14],16)))
        to_send2.extend(add.to_bytes(4,'big'))
        if mem_sp_separated:
            to_send2.extend((mem_sp,))
        to_send2.extend(mem[:size])
        print("to_send=",to_send)
        print("to_send2=",to_send2)
        dgrams = create_datagram_list(src,dest,to_send2)
        for d in dgrams:
            s.send(d.to_gridconnect())
            print("sending",d.data,"=",d.to_gridconnect())
            
def memory_write(s,src_node,dest_node,add,buf):  #buf: write msg as string

    print("memory write")
    if buf[3]=="A" or buf[3]=="B":
        if buf[14]=="0":
            mem_sp = int(buf[23:25],16)
            data_beg=25
        else:
            mem_sp = 0xFC+int(buf[14])
            data_beg=23
        src_node.current_write=(mem_sp,add)
        s.send((":X19A28"+hexp(src_node.aliasID,3)+"N0"+hexp(dest_node.aliasID,3)+";").encode("utf-8"))
        print("datagram received ok sent --->",":X19A28"+hexp(src_node.aliasID,3)+"N0"+hexp(dest_node.aliasID,3)+";")
    else:
        data_beg=11
    if src_node.current_write is None:
        print("write error: trying to write but current_write is none!!")
    else:
        res=b""
        for pos in range(data_beg,len(buf)-1,2):
            print(buf[pos:pos+2])
            res+=bytes([int(buf[pos:pos+2],16)])
        print("written:",res)
        print("node:",src_node.ID,"memory write",src_node.current_write[0],"offset",src_node.current_write[1])
        if src_node.current_write[0] not in src_node.memory:
            print("memory unknown!")
            return
        src_node.set_mem_partial(src_node.current_write[0],src_node.current_write[1],res)
    if buf[3]=="A" or buf[3]=="D":
        src_node.current_write = None

def reserve_aliasID(src_id):
    neg=get_alias_neg_from_alias(src_id)
    if neg.reserve():
        if neg.aliasID in reserved_aliases:
            print("Error: trying to reserve alias ",neg.aliasID,"(",neg.fullID,") but its already reserved!")
        else:
            reserved_aliases[neg.aliasID]=neg.fullID
            list_alias_neg.remove(neg)

def can_control_frame(cli,msg):
    first_b=int(msg[2:4],16)
    var_field = int(msg[4:7],16)
    src_id = int(msg[7:10],16)
    data_needed = False
    if first_b & 0x7>=4 and first_b & 0x7<=7:
        print("CID Frame n°",first_b & 0x7," * ",hex(var_field),end=" * 0x")
        #full_ID = var_field << 12*((first_b&0x7) -4)
        if first_b&0x7==7:
            alias_neg = Alias_negotiation(src_id)
        else:
            alias_neg = get_alias_neg_from_alias(src_id)
        alias_neg.next_step(var_field)
        list_alias_neg.append(alias_neg)

    elif first_b&0x7==0:
        if var_field==0x700:
            print("RID Frame * full ID=")#,hex(full_ID),end=" * ")
            jmri_identified = True   #FIXME
            neg = get_alias_neg_from_alias(src_id)
            reserve_aliasID(src_id)
            new_node(Node(neg.fullID,True,neg.aliasID))

        elif var_field==0x701:
            print("AMD Frame",end=" * ")
            neg = get_alias_neg_from_alias(src_id)
            new_node(Node(neg.fullID,True,neg.aliasID)) #JMRI node only for now
            reserve_aliasID(src_id)
            data_needed = True   #we could check the fullID

        elif var_field==0x702:
            print("AME Frame",end=" * ")
            data_nedded=True
        elif var_field==0x703:
            print("AMR Frame",end=" * ")
            data_nedded=True
        elif var_field>=0x710 and var_field<=0x713:
            print("Unknown Frame",end=" * ")
    print(hexp(src_id,3))
    if data_needed and not data_present:
        print("Data needed but none is present!")
        return

def global_frame(cli,msg):
    first_b=int(msg[2:4],16)
    var_field = int(msg[4:7],16)
    src_id = int(msg[7:10],16)
    s = cli.sock
    
    if var_field==0x490:  #Verify node ID (global) FIXME
        for b in buses.Bus_manager.buses:
            for c in b.clients:
                for n in c.managed_nodes:
                    s.send((":X19170"+hexp(n.aliasID,3)+"N"+hexp(n.ID,12)+";").encode('utf-8'))
                    print("Sent---> :X19170"+hexp(n.aliasID,3)+"N"+hexp(n.ID,12)+";")

    elif var_field==0x828:#Protocol Support Inquiry
        dest_node_alias = int(msg[12:15],16)
        dest_node = find_managed_node(dest_node_alias)

        if dest_node is not None:
            #FIXME: set correct bits
            s.send((":X19668"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+hexp(SPSP|SNIP|CDIP,6)+"000000;").encode("utf-8"))
            print("sent--->:X19668"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+hexp(SPSP|SNIP|CDIP,6)+"000000;")

    elif var_field == 0xDE8:#Simple Node Information Request
        dest_node_alias = int(msg[12:15],16)
        dest_node = find_managed_node(dest_node_alias)
        if dest_node is not None:
            print("sent SNIR Reply")
            #s.send((":X19A08"+hexp(gw_add.aliasID,3)+"N1"+hexp(src_id,3)+"04;").encode("utf-8"))#SNIR header
            #print(":X19A08"+hexp(gw_add.aliasID,3)+"N1"+hexp(src_id,3)+"04;")
            #FIXME:
            src_node = find_node(src_id)
            send_fields(s,dest_node,0xA08,mfg_name_hw_sw_version,src_node)

            #s.send((":X19A08"+hexp(gw_add.aliasID,3)+"N3"+hexp(src_id,3)+"02;").encode("utf-8"))#SNIR header
            #print(":X19A08"+hexp(gw_add.aliasID,3)+"AAAN3"+hexp(src_id,3)+"02;")
            #send_fields(0xA08,username_desc,src_id,True)

    elif var_field == 0x5B4: #PCER (event)
        ev_id = bytes([int(msg[11+i*2:13+i*2],16) for i in range(8)])
        print("received event:",ev_id)
        for b in buses.Bus_manager.buses:
            for c in b.clients:
                for n in c.managed_nodes:
                    n.consume_event(Event(ev_id))

def process_datagram(cli,msg):
    src_id = int(msg[7:10],16)
    s = cli.sock
    address = int(msg[15:23],16)
    print("datagram!!")
    #for now we assume a one frame datagram
    dest_node_alias = int(msg[4:7],16)
    dest_node = find_managed_node(dest_node_alias)
    if dest_node is None:   #not for us
        print("Frame is not for us!!")
        #FIXME: we have to transmit it ??
        return
    src_node = find_node(src_id)

    if dest_node.current_write is not None:
        #if there is a write in progress then this datagram is part of it
        memory_write(s,dest_node,src_node,address,msg)
    elif msg[11:15]=="2043": #read command for CDI
        print("read command, address=",int(msg[15:23],16))
        s.send((":X19A28"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+";").encode('utf-8'))
        print("datagram received ok sent --->",(":X19A28"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+";").encode("utf-8"))
        send_CDI(s,dest_node,src_node,address,int(msg[23:25],16))
    elif msg[11:13]=="20": #read/write command
        s.send((":X19A28"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+";").encode('utf-8'))
        print("datagram received ok sent --->",(":X19A28"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+";").encode("utf-8"))
        if msg[13]=="4":
            memory_read(s,dest_node,src_node,address,msg)
        elif msg[13]=="0":
            memory_write(s,dest_node,src_node,address,msg)
    
def process_grid_connect(cli,msg):
    if msg[:2]!=":X":
        print("Error: not an extended frame!!")
        return
    if msg[10]!="N":
        print("Error: not a normal frame!!")
        return
    first_b = int(msg[2:4],16)
    can_prefix = (first_b & 0x18) >> 3
    if can_prefix & 0x1==0:
        #Can Control frame
        can_control_frame(cli,msg)

    else:
        if (first_b & 0x7)==1:  #global or addressed frame msg
            global_frame(cli,msg)
                            
        elif (first_b & 0x7)>=2 and (first_b & 0x7)<=5: #Datagram
            process_datagram(cli,msg)

#globals: fixme

mfg_name_hw_sw_version=["\4python gateway","test","1.0","1.0","\2gw1","gateway-1"]

list_alias_neg=[]  #list of ongoing alias negotiations
reserved_aliases = {}  #dict alias--> fullID of reserved aliases

OLCB_serv = openlcb_server.Openlcb_server("127.0.0.1",50000)
OLCB_serv.start()
buses_serv = openlcb_server.Buses_server("127.0.0.1",50001)
buses_serv.start()

# queue up to 5 requests

done = False
while not done:
    reads = OLCB_serv.wait_for_clients()
    OLCB_serv.process_reads(reads)
    for c in OLCB_serv.clients:
        msg = c.next_msg()
        if msg and msg != ";":
            process_grid_connect(c,msg)
    reads=buses_serv.wait_for_clients()
    buses_serv.process_reads(reads)
    #check all clients who haven't sent the bus name yet
    to_delete=deque()
    for i in range(len(buses_serv.unconnected_clients)):
        if buses_serv.unconnected_clients[i].check_bus_name():
            to_delete.appendleft(i)
    #remove the clients who just connected from the unconnected list
    for index in to_delete:
        buses_serv.unconnected_clients.pop(index)
    #process any incoming messages for each bus
    ev_list=[]
    for bus in buses.Bus_manager.buses:
        ev_list.extend(bus.process())
    #and send the events generated in response
    for ev in ev_list:
        OLCB_serv.send_event(ev[0],ev[1])
        buses_serv.send_event(ev[0],ev[1])
