# meshy-connectors

Builds the packages that connect a host to Meshy's hosted MCP server (`mcp.meshy.ai`, `mcp.meshy.cn`) from one source: WorkBuddy and MiniMax today, then GPT and Kimi. Each package is the server's connection settings (on MiniMax, the App that holds them), one hosted-MCP skill, and the name, description, examples and icon a host shows.

Not built here: the CLI and its skills (meshy-3d-agent), the local MCP server, the Codex Plugin Directory bundle, and the Antigravity plugin, which keeps its own repo.

## How a package is built

```
base/                    what a Meshy connector is: names, examples, MCP settings, the skill, the icon
  + layers/site/<site>   the server address (ai, cn)
  + layers/host/<host>   what the host can do and the fields only it reads (workbuddy, minimax)
  + layers/env/<env>     a test package's server (staging)
  + targets/<target>     identity, version, and the few fields only this package has
  → exporters/<platform> the platform's files, zipped into dist/<target>-<version>.zip
```

A target lists its layers, which apply in site, host, env order, one of each at most; the target file applies last.

- Objects merge key by key, arrays replace, and `null` deletes a key. Setting a key to the value it already has is an error.
- `{{ a.b }}` variables expand after the merge, in the config and in the skill text. The skill's name is `{{ mcp.server_key }}-skill`, so `meshy` ships `meshy-skill` and `meshy-3d` ships `meshy-3d-skill` from one file.
- Every layer is checked against `schema/connector.schema.json` for keys and types; the merged target is checked in full.
- Every change a layer makes to a value set before it is printed and kept in the build report.
- Exporters only map fields to a platform's files and names; they decide no content.

## Targets

| Target | Layers | Server | Version | Published |
|---|---|---|---|---|
| `workbuddy-ai` | site/ai, host/workbuddy | `mcp.meshy.ai` | 0.1.2 | yes |
| `workbuddy-cn` | site/cn, host/workbuddy | `mcp.meshy.cn` | 0.1.2 | yes |
| `workbuddy-ai-staging` | site/ai, host/workbuddy, env/staging | `mcp.staging.meshy.ai` | 0.1.1 | no, test only |
| `minimax-ai` | site/ai, host/minimax | `mcp.meshy.ai` | 0.1.1 | no, waiting for MiniMax |

At 0.1.1, `workbuddy-ai` and `workbuddy-cn` rendered file for file the hand-made 0.1.1 packages they replaced; since 0.1.2 every package takes `workbuddy-cn`'s description from base, under its own name. There is no China staging package: meshy.cn has no staging server, and its network cannot reach `*.meshy.ai`.

`minimax-ai` is the US region's MiniMax Plugin. It holds no server address: MiniMax allows no OAuth in a plugin's `*.mcp.json`, so MiniMax's Connector connects to `mcp.meshy.ai` and signs users in, and the package's `meshy.app.json` names that App by its provider. MiniMax confirms the provider only after it has connected and tested the server (MiniMax's App (MCP Server) Integration Guide); until then `host.minimax.provider` holds the one Meshy proposes, and the package is not submitted. Submit the zip on MiniMax's form with the US region and the `name` from `plugin.json` (MiniMax's Plugin Development and Submission Guide, §9).

## Usage

Python 3.11 or later.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python build.py                    # every target into dist/
.venv/bin/python build.py workbuddy-cn       # one target
.venv/bin/python build.py --check            # rendered files against snapshots/, writes nothing
.venv/bin/python build.py --write-snapshots  # after a change, then commit snapshots/
.venv/bin/python -m unittest discover -s tests
```

`dist/` (not committed) holds the zips, `SHA256SUMS` and `build-report.json`: the source commit, and per target its layers, version, zip digest, every file's digest and the overrides. The same tree zips to the same bytes.

## Changing a package

1. Edit `base/` to change every package, a layer to change the packages that use it, or a target to change one.
2. Bump `version` in every target whose files change.
3. Run `build.py --write-snapshots` and commit `snapshots/` with the change, so the PR shows exactly what each package will contain.
4. After the merge, build from `main`. The holder of the platform account uploads the zip from `dist/`; paste the build report into the ticket.

Once a target is `published: true`, its `id`, `mcp.server_key` and skill name stay as they are: hosts file installs and sign-ins under them.

## Not here yet

- CI: snapshots, the skill's tool names against each site's hosted `tools/list`, frozen identities, version bumps, no internal hosts in public packages.
- One hosted-MCP skill merged from today's WorkBuddy, GPT and Kimi texts. `base/skill/SKILL.md` is WorkBuddy's 0.1.1 skill, unchanged.
- The GPT and Kimi exporters.
- `minimax-cn`, the China region's MiniMax package.
- The submodule in meshy-integrations.
