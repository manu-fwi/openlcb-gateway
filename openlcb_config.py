from openlcb_debug import *
import json

#load config file, content: config dict in json format (see code)
def load_config(filename):
    try:
        with open(filename,"r") as cfg_file:
            config = json.load(cfg_file)
    except:
        debug("Error reading config file:",filename)
        config = {}
    #fill in missing values with reasonable defaults
    if "server_ip" not in config:
        config["server_ip"]="127.0.0.1"
    if "server_base_port" not in config:
        config["server_base_port"]=50000
    return config
