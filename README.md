# openlcb-gateway
Gateway from openlcb to cmri (and more)

The goal (briefly): run a server that JMRI will connect to and fake openlcb nodes (for now only one).
This "faked" node will connect to a real cpNode and do the translation openlcb <-> CMRI.

What works: the early openlcb transactions (but not really the alias negotiation), the config (CDI) and the CMRI translation (tested with a cpnode sketch v1.5)

Todo (alot):

-improve (I first need to understand it better) the alias negotiation

-allow to auto discover (or read from a config file) most of the nodes

If you want to test:

first setup your IP address by changing the one in this line (towards the end of the openlcb-gateway.py file):

serv = openlcb_server.server("127.0.0.1",50000)

save and then just run

python3 openlcb-gateway.py

Then setup an openlcb node with gridconnect protocol (port is 50000) and it will talk to your openlcb gateway!

For now it only has one cmri cpnode (8IN/8OUT) with address 1

To setup the serial communication: change the serial device in the cmri_net_serial.py file (ser = serial_bus("/dev/ttyUSB1",9600)) and also the gateway ip if you changed it: gateway_ip = "127.0.0.1"

Save and run:

python3 cmri_net_serial.py

And voila.