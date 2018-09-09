# openlcb-gateway
Gateway from openlcb to cmri and RR_duino (see my other github repo about it)

The goal (briefly): make the link between nodes which are not openlcb aware (for now the only supported type is CMRI CPNodes) and JMRI and other openlcb aware hardware/software.

The gateway handles all the openlcb protocol from alias negotiations up to CDI and sending/receiving events.

Todo:

-improve the alias negotiation
-better handling producer/consumer identify (ied)
-make sure all relevant openlcb traffic is forwarded to all connected clients (works probably already but needs more testing)

-a lot more than that I guess ;-)

If you want to test, see the wiki.
