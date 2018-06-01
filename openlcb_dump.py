from openlcb_debug import *
from openlcb_protocol import *
import openlcb_config
import socket

config_dict = openlcb_config.load_config("openlcb_gateway.cfg")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect((config_dict["server_ip"], config_dict["server_base_port"]))

debug("Connected to openlcb_gateway [",config_dict["server_ip"],":", config_dict["server_base_port"],"]")
msgs=""
while True:
    msgs+=sock.recv(200).decode('utf-8')
    msg,sep,end = msgs.partition(";")
    if sep:
        debug("next message= ",msg+sep)
        msgs = end
