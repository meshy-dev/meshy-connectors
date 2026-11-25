"""WorkBuddy connector package: connector-meta.json, mcp.json, icon.svg and the skill.

WorkBuddy publishes no schema for these files. The field names and shapes here
are those of Meshy's hand-made 0.1.1 packages (2026-11), so this module is the
reference until it does.
"""

import json

# WorkBuddy spells the transport its own way.
TRANSPORTS = {"streamable-http": "streamableHttp"}


def export(config, sources):
    mcp = config["mcp"]
    workbuddy = config["host"].get("workbuddy")
    if workbuddy is None:
        raise ValueError("the workbuddy exporter needs host.workbuddy (layers/host/workbuddy.yaml)")

    meta = {
        "name": config["display_name"]["en"],
        "name_zh": config["display_name"]["zh"],
        "name_en": config["display_name"]["en"],
        "description": config["description"]["en"],
        "description_zh": config["description"]["zh"],
        "description_en": config["description"]["en"],
        "source": config["id"],
        "type": "mcp",
        # The schema allows only oauth, which WorkBuddy runs on its side.
        "auth_mode": "server-side",
        "version": config["version"],
        "examples_zh": config["examples"]["zh"],
        "examples_en": config["examples"]["en"],
        "minWorkbuddyVersion": workbuddy["min_version"],
        "server_auth": {
            "auth_type": "mcp_oauth",
            "data": {"mcp_oauth": {"server_url": mcp["url"]}},
        },
    }
    servers = {
        "mcpServers": {
            mcp["server_key"]: {
                "type": TRANSPORTS[mcp["transport"]],
                "url": mcp["url"],
                "timeout": mcp["timeout_ms"],
            }
        }
    }
    return {
        "connector-meta.json": _json(meta),
        "mcp.json": _json(servers),
        "icon.svg": sources["icon"],
        f"skills/{config['skill']['name']}/SKILL.md": sources["skill"].encode(),
    }


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
