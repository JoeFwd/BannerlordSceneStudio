"""Settlement placement feature — light hexagonal split.

* ``model``      — pure domain: settlement types, footprint radius resolution,
                   land/water rule. No I/O, no Bannerlord, no HTTP.
* ``config``     — per-map footprint configuration persisted as a sidecar JSON.
* ``repository`` — byte-surgical adapter that reads/writes settlements.xml and
                   scene.xscene.

The web/MCP delivery layers depend on these; nothing here depends on them.
"""
