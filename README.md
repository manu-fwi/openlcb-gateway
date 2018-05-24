# openlcb-gateway
Gateway from openlcb to cmri (and more)

The goal (briefly): make the link between nodes which are not openlcb aware (for now the only supported type is CMRI CPNodes) and JMRI and other openlcb aware hardware/software.

What works: the early openlcb transactions (but not really the alias negotiation), the config (CDI) and the CMRI translation (tested with a cpnode sketch v1.5)

Todo (alot):

-improve (I first need to understand it better) the alias negotiation

-a lot more than that!

If you want to test, see the wiki.
