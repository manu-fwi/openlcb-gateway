# openlcb-gateway
Gateway from openlcb to cmri (and more)

The goal (briefly): make the link between nodes which are not openlcb aware (for now the only supported type is CMRI CPNodes) and JMRI and other openlcb aware hardware/software.

What works: the early openlcb transactions (even alias negotiation to some extent), the config (CDI) and the CMRI translation (tested with a cpnode sketch v1.5)

Todo (alot):

-improve the alias negotiation
-make sure all relevant openlcb traffic is forwarded to all connected clients (works probably already but needs more testing)

-a lot more than that I guess ;-)

If you want to test, see the wiki.
