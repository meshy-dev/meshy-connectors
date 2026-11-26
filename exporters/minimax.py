"""MiniMax Plugin package: .minimax-plugin/plugin.json, the App reference, the icon and the skill.

Field names, paths and limits are those of MiniMax's Plugin Development and
Submission Guide (revision 333) and App (MCP Server) Integration Guide
(revision 62), 2026-11. The package carries no MCP server: the hosted server is
an App, which MiniMax's Connector connects to and signs users in to, so the
package holds only its provider. A package is for one region (CN or US) and
plugin.json has one language.
"""

import json
import re
from pathlib import PurePosixPath

# plugin.json's name: a lowercase machine name of at most 80 characters.
NAME = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
# The image types plugin.json's icon may be, spelt in lowercase.
ICON_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
# exampleQueries holds at most three.
MAX_EXAMPLES = 3


def export(config, sources):
    minimax = config["host"].get("minimax")
    if minimax is None:
        raise ValueError("the minimax exporter needs host.minimax (layers/host/minimax.yaml)")
    if not NAME.match(config["id"]) or len(config["id"]) > 80:
        raise ValueError(f"id {config['id']!r} is not a MiniMax plugin name")
    language = minimax["language"]
    examples = config["examples"][language]
    if len(examples) > MAX_EXAMPLES:
        raise ValueError(f"MiniMax takes at most {MAX_EXAMPLES} examples; examples.{language} has {len(examples)}")
    suffix = PurePosixPath(config["assets"]["icon"]).suffix
    if suffix not in ICON_SUFFIXES:
        raise ValueError(f"MiniMax takes a {', '.join(ICON_SUFFIXES)} icon, not {config['assets']['icon']}")

    icon = f"icon{suffix}"
    app = f"{config['id']}.app.json"
    skill = f"skills/{config['skill']['name']}/SKILL.md"
    manifest = {
        "schemaVersion": 1,
        "name": config["id"],
        "displayName": config["display_name"][language],
        "version": config["version"],
        "description": config["description"][language],
        "author": config["author"],
        "icon": icon,
        "category": minimax["category"],
        "exampleQueries": examples,
        "apps": [app],
        "mcpServers": [],
        "skills": [skill],
    }
    return {
        ".minimax-plugin/plugin.json": _json(manifest),
        app: _json({"schemaVersion": 1, "provider": minimax["provider"]}),
        icon: sources["icon"],
        skill: sources["skill"].encode(),
    }


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
