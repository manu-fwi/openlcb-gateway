# openlcb-gateway
Gateway from openlcb to cmri (and more)

The goal (briefly): make the link between nodes which are not openlcb aware (for now the only supported type is CMRI CPNodes) and JMRI and other openlcb aware hardware/software.

What works: the early openlcb transactions (alias negotiation to some extent), the config (CDI), the CMRI translation (tested with a cpnode sketch v1.5) and event handling. NEW: outputs states are saved in files so outputs are set to last known state across power cycles and reboots.

Todo (alot):

-improve the alias negotiation
-correctly handle producer/consumer identify (ied)
-make sure all relevant openlcb traffic is forwarded to all connected clients (works probably already but needs more testing)

-a lot more than that I guess ;-)

If you want to test, see the wiki.
