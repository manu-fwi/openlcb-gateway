import openlcb_cmri_cfg as cmri
import openlcb_buses as buses
import openlcb_server
from openlcb_nodes import *
from openlcb_protocol import *
import socket,select,time
from collections import deque
import openlcb_nodes_db
import openlcb_config

def send_fields(sock,src_node,MTI,fields,dest_node):
    frames = create_addressed_frame_list(src_node,dest_node,MTI,("\0".join(fields)).encode('utf-8'),True)
    for f in frames:
        sock.send(f.to_gridconnect())
        debug("--->",f.to_gridconnect().decode('utf-8'))

def send_CDI(s,src_node,dest_node,address,size):
    data = bytearray((0x20,0x53))
    data.extend(address.to_bytes(4,'big'))
    data.extend(bytearray(src_node.get_CDI()[address:address+size],'utf-8'))
    #debug(src_node.get_CDI())
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
    debug("memory read at",mem_sp,"offset",add,"size",size)
    if mem_sp not in src.memory:
        debug("memory unknown!!")
        return
    mem = src.read_mem(mem_sp,add)
    debug("memory read sends:",mem)
    if mem is None:
        debug("memory error")
    else:
        to_send2= bytearray((0x20,int("5"+msg[14],16)))
        to_send2.extend(add.to_bytes(4,'big'))
        if mem_sp_separated:
            to_send2.extend((mem_sp,))
        to_send2.extend(mem[:size])
        dgrams = create_datagram_list(src,dest,to_send2)
        for d in dgrams:
            s.send(d.to_gridconnect())
            debug("sending",d.data,"=",d.to_gridconnect())
            
def memory_write(s,src_node,dest_node,add,buf):  #buf: write msg as string
    #return True when write has completed (a full write is generally split in several chunks

    debug("memory write")
    if buf[3]=="A" or buf[3]=="B":
        if buf[14]=="0":
            mem_sp = int(buf[23:25],16)
            data_beg=25
        else:
            mem_sp = 0xFC+int(buf[14])
            data_beg=23
        src_node.current_write=(mem_sp,add)
        s.send((":X19A28"+hexp(src_node.aliasID,3)+"N0"+hexp(dest_node.aliasID,3)+";").encode("utf-8"))
        debug("datagram received ok sent --->",":X19A28"+hexp(src_node.aliasID,3)+"N0"+hexp(dest_node.aliasID,3)+";")
    else:
        data_beg=11
    if src_node.current_write is None:
        debug("write error: trying to write but current_write is none!!")
    else:
        res=b""
        for pos in range(data_beg,len(buf)-1,2):
            debug(buf[pos:pos+2])
            res+=bytes([int(buf[pos:pos+2],16)])
        debug("written:",res)
        debug("node:",src_node.ID,"memory write",src_node.current_write[0],"offset",src_node.current_write[1])
        if src_node.current_write[0] not in src_node.memory:
            debug("memory unknown!")
            return False
        src_node.set_mem_partial(src_node.current_write[0],src_node.current_write[1],res)
    if buf[3]=="A" or buf[3]=="D":
        src_node.current_write = None
        return True
    return False

def reserve_aliasID(src_id):
    neg=get_alias_neg_from_alias(src_id)
    if neg.reserve():
        if neg.aliasID in reserved_aliases:
            debug("Error: trying to reserve alias ",neg.aliasID,"(",neg.fullID,") but its already reserved!")
        else:
            reserved_aliases[neg.aliasID]=neg.fullID
            list_alias_neg.remove(neg)
            debug("reserved alias",neg.aliasID)
                        

def check_alias(alias):
    """
    Checks if the alias is used by one of our nodes
    if yes transition the node to inhibited state, send AMR frame
    and reset alias negotiation for the node
    """

    node_cli = find_managed_node(alias)
    if node_cli is None:
        return None
    node = node_cli[0]
    node.permitted = False
    #reset the alias negotiation
    alias_neg = node.create_alias_negotiation()
    #loop while we find an unused alias
    while (alias_neg.aliasID in reserved_aliases) or (get_alias_neg_from_alias(alias_neg.aliasID) is not None):
        alias_neg = node.create_alias_negotiation()
    #register to the bus alias neg list
    node_cli[1].bus.nodes_in_alias_negotiation.append((node,alias_neg))
    #also add it to the list of aliases negotiation
    list_alias_neg.append(alias_neg)
    #send AMR to all openlcb nodes
    OLCB_serv.send(Build_AMR(node))

def can_control_frame(cli,msg):
    #transfer to all other openlcb clients
    OLCB_serv.transfer(msg.encode('utf-8'),cli)
    first_b=int(msg[2:4],16)
    var_field = int(msg[4:7],16)
    src_id = int(msg[7:10],16)
    data_needed = False
    if first_b & 0x7>=4 and first_b & 0x7<=7:
        debug("CID Frame n°",first_b & 0x7," * ",hex(var_field))
        #full_ID = var_field << 12*((first_b&0x7) -4)
        new = False
        if first_b&0x7==7:
            if get_alias_neg_from_alias(src_id) is not None:
                debug("Alias collision")
                #fixme: what to do here??
                return
            alias_neg = Alias_negotiation(src_id)
            new = True
        else:
            alias_neg = get_alias_neg_from_alias(src_id)
            if alias_neg is None:
                debug("CID frame with no previous alias negotiation!")
                alias_neg = Alias_negotiation(src_id,0,8-(first_b&0x07))
                new = True
        alias_neg.next_step(var_field)
        if new:
            list_alias_neg.append(alias_neg)
        #if we have a node in permitted state we send an AMD frame
        node_cli = find_managed_node(src_id)
        if node_cli is not None:
            OLCB_serv.send(Build_AMD(node_cli[0]))

    elif first_b&0x7==0:
        if var_field==0x700:
            debug("RID Frame * full ID=")
            neg = get_alias_neg_from_alias(src_id)
            if neg is None:
                #no CID before that create the alias_negotiation
                neg = Alias_negotiation(src_id,0,4)
                list_alias_neg.append(neg)
            reserve_aliasID(src_id)
            #create node but not in permitted state
            new_node(Node(neg.fullID,False,neg.aliasID))
            check_alias(src_id)
                
        elif var_field==0x701:
            debug("AMD Frame")
            check_alias(src_id)
            if src_id in reserved_aliases:
                node = find_node(src_id)
                if node is None:
                    debug("AMD frame received (alias=",src_id,") but node does not exist!")
                else:
                    #change to permitted state
                    node.permitted = True
            else:
                debug("AMD frame received (alias=",src_id,") but not reserved before!")
                #create alias, reserve it
                neg = Alias_negotiation(src_id,0,4)
                list_alias_neg.append(neg)
                reserve_aliasID(src_id)
                #create node in permitted state
                new_node(Node(int(msg[11:23],16),True,src_id))
            data_needed = True   #we could check the fullID

        elif var_field==0x702:
            debug("AME Frame")
            for b in buses.Bus_manager.buses:
                for c in b.clients:
                    for n in c.managed_nodes:
                        if n.permitted:
                            f=Frame.build_AMD(n)
                            OLCB_serv.send(f)
                            debug("sent---->:",f.to_gridconnect())
                            debug("Sent---> :X19170"+hexp(n.aliasID,3)+"N"+hexp(n.ID,12)+";")
        elif var_field==0x703:
            #FIXME!
            debug("AMR Frame")
            data_nedded=True
        elif var_field>=0x710 and var_field<=0x713:
            debug("Unknown Frame")
    debug(hexp(src_id,3))
    if data_needed and not data_present:
        debug("Data needed but none is present!")
        return

def process_id_prod_consumer(cli,msg):
    var_field = int(msg[4:7],16)
    if var_field == 0x914: #identify producer
        ev_id = bytes([int(msg[11+i*2:13+i*2],16) for i in range(8)])
        debug("identify producer received for event:",ev_id)
        for b in buses.Bus_manager.buses:
            for c in b.clients:
                for n in c.managed_nodes:
                    if n.permitted:
                        res = n.check_id_producer_event(Event(ev_id))
                        if res != None:
                            if res == Node.ID_PRO_CONS_VAL:
                                MTI = Frame.MTI_ID_PROD_VAL
                            elif res == Node.ID_PRO_CONS_INVAL:
                                MTI = Frame.MTI_ID_PROD_INVAL
                            else:
                                MTI = Frame.MTI_ID_PROD_UNK
                            #send it through internal socket
                            openlcb_server.internal_sock.send(build_from_event(n,ev_id,MTI).to_gridconnect())                            
                            #advertised mode
                            n.advertised = True
def global_frame(cli,msg):
    first_b=int(msg[2:4],16)
    var_field = int(msg[4:7],16)
    src_id = int(msg[7:10],16)
    s = cli.sock
    
    if var_field==0x490:  #Verify node ID (global) FIXME: send the response globally
        debug("verify id")
        #forward to all other clients
        OLCB_serv.transfer(msg.encode('utf-8'),cli)
        for b in buses.Bus_manager.buses:
            debug("bus verifiy id:",b.name)
            for c in b.clients:
                debug("verify id client",c.address," managed_nodes",len(c.managed_nodes))
                for n in c.managed_nodes:
                    debug("verified id node",n.ID)
                    if n.permitted:
                        OLCB_serv.transfer(":X19170"+hexp(n.aliasID,3)+"N"+hexp(n.ID,12)+";")
                        debug("Sent---> :X19170"+hexp(n.aliasID,3)+"N"+hexp(n.ID,12)+";")

    elif var_field==0x828:#Protocol Support Inquiry
        dest_node_alias = int(msg[12:15],16)
        dest_node,cli_dest = find_managed_node(dest_node_alias)

        if dest_node is not None:
            #FIXME: set correct bits
            s.send((":X19668"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+hexp(SPSP|SNIP|CDIP,6)+"000000;").encode("utf-8"))
            debug("sent--->:X19668"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+hexp(SPSP|SNIP|CDIP,6)+"000000;")

    elif var_field == 0xDE8:#Simple Node Information Request
        dest_node_alias = int(msg[12:15],16)
        dest_node,cli_dest = find_managed_node(dest_node_alias)
        if dest_node is not None:
            debug("sent SNIR Reply")
            #s.send((":X19A08"+hexp(gw_add.aliasID,3)+"N1"+hexp(src_id,3)+"04;").encode("utf-8"))#SNIR header
            #print(":X19A08"+hexp(gw_add.aliasID,3)+"N1"+hexp(src_id,3)+"04;")
            #FIXME:
            src_node = find_node(src_id)
            send_fields(s,dest_node,0xA08,mfg_name_hw_sw_version,src_node)

    elif var_field == 0x5B4: #PCER (event)
        #transfer to all other openlcb clients
        OLCB_serv.transfer(msg.encode('utf-8'),cli)
        ev_id = bytes([int(msg[11+i*2:13+i*2],16) for i in range(8)])
        debug("received event:",ev_id)
        #FIXME: transfer to other openlcb nodes (outside of our buses)
        for b in buses.Bus_manager.buses:
            for c in b.clients:
                for n in c.managed_nodes:
                    if n.permitted:
                        n.consume_event(Event(ev_id))
    elif var_field == 0x914 or var_field == 0x8F4: #identify producer/consumer
        #transfer to all other openlcb clients
        OLCB_serv.transfer(msg.encode('utf-8'),cli)
        process_id_prod_consumer(cli,msg)
                            

def process_datagram(cli,msg):
    src_id = int(msg[7:10],16)
    s = cli.sock
    #for now we assume a one frame datagram
    dest_node_alias = int(msg[4:7],16)
    dest_node,cli_dest = find_managed_node(dest_node_alias)
    if dest_node is None and node.permitted:   #not for us or the node is not ready yet
        debug("Frame is not for us!!")
        #forward to all other OLCB clients
        OLCB_serv.transfer(msg.encode('utf-8'),cli)
        return
    src_node = find_node(src_id)
    if dest_node.current_write is not None:
        address = int(msg[15:23],16)
        #if there is a write in progress then this datagram is part of it
        if memory_write(s,dest_node,src_node,address,msg):
            debug(cli_dest,cli_dest.bus,cli_dest.bus.nodes_db)
            cli_dest.bus.nodes_db.synced = False
    elif msg[11:15]=="2043": #read command for CDI
        address = int(msg[15:23],16)
        debug("read command, address=",int(msg[15:23],16))
        s.send((":X19A28"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+";").encode('utf-8'))
        debug("datagram received ok sent --->",(":X19A28"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+";").encode("utf-8"))
        send_CDI(s,dest_node,src_node,address,int(msg[23:25],16))
    elif msg[11:14]=="200" or msg[11:14]=="204": #read/write command
        s.send((":X19A28"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+";").encode('utf-8'))
        debug("datagram received ok sent --->",(":X19A28"+hexp(dest_node.aliasID,3)+"N0"+hexp(src_id,3)+";").encode("utf-8"))
        if msg[13]=="4":
            address = int(msg[15:23],16)
            memory_read(s,dest_node,src_node,address,msg)
        elif msg[13]=="0":
            address = int(msg[15:23],16)
            if memory_write(s,dest_node,src_node,address,msg):
                cli_dest.bus.nodes_db.synced = False
        elif msg[11:13]=="20":
            #other commands than read/write
            if msg[13:15]=="A8":
                #CDI update complete, we do not have to reply so we dont for now
                debug("Update complete received from node ",src_node.ID)
            elif msg[13:15]=="80":
                #Get configurations options
                dgram = Datagram_content.build_get_config_opt_reply(dest_node,src_node)
                s.send(dgram.to_gridconnect())
                debug("---> S: config opt reply=",dgram.to_gridconnect())
    
def process_grid_connect(cli,msg):
    if msg[:2]!=":X":
        debug("Error: not an extended frame!!")
        return
    if msg[10]!="N":
        debug("Error: not a normal frame!!")
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

config_dict = openlcb_config.load_config("openlcb_gateway.cfg")

OLCB_serv = openlcb_server.Openlcb_server(config_dict["server_ip"],config_dict["server_base_port"])
OLCB_serv.start()
buses_serv = openlcb_server.Buses_server(config_dict["server_ip"],config_dict["server_base_port"]+1)
buses.Bus_manager.buses_serv=buses_serv
buses_serv.start()

#internal sock used to "reinject" frames on the OLCB server)
openlcb_server.internal_sock.connect((config_dict["server_ip"],config_dict["server_base_port"]))
done = False
while not done:
    ev_list=[]
    frames_list=[]
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
    for bus in buses.Bus_manager.buses:
        new_frames = bus.process()
        frames_list.extend(new_frames)
    #and send the events generated in response
    #we do this by injecting them through our internal sock
    #FIXME: I think this ensures that the frames chronology is OK
    #That is: the server will process these answers after all previous incoming frames
    for frame in frames_list:
        openlcb_server.internal_sock.send(frame.to_gridconnect())
