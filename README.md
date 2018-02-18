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
