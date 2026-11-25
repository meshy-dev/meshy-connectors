"""One module per platform. Each exports `export(config, sources) -> {path: bytes}`.

`config` is the merged, schema-checked connector; `sources` holds the files it
names, read from base/ (`skill` as text with its variables expanded, `icon` as
bytes). An exporter only maps fields to the platform's files and names; it never
decides content.
"""

from . import minimax, workbuddy

EXPORTERS = {"minimax": minimax.export, "workbuddy": workbuddy.export}
