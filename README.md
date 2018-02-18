# openlcb-gateway
Gateway from openlcb to cmri (and more)

The goal (briefly): run a server that JMRI will connect to and fake openlcb nodes (for now only one).
This "faked" node will connect to a real cpNode and do the translation openlcb <-> CMRI.

What works: the early openlcb transactions (but not really the alias negotiation), the config (CDI).

Todo (alot):

-memory reads/writes to finish config

-improve (I first need to understand it better) the alias negotiation

-real cmri<->openlcb translation

-and more

To test:

first setup your IP address by changing the one in this line (towards the end of the openlcb-gateway.py file):

serv = openlcb_server.server("192.168.0.14",50000)

save and then just run

python3 openlcb-gateway.py

hit enter when you see "waiting" on the console

Then setup an openlcb node with gridconnect protocol (port is 50000) and it will talk to your openlcb gateway!