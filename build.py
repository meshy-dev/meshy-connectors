#!/usr/bin/env python3
"""Render every connector package from base/, layers/ and targets/, then zip it.

usage:
  build.py [TARGET ...]              build into dist/ (all targets by default)
  build.py --check [TARGET ...]      compare the rendered files with snapshots/, write nothing
  build.py --write-snapshots [...]   rewrite snapshots/ from the rendered files

A target is base/connector.yaml, then its layers in site, host, env order, then
the target file itself. Objects merge key by key, arrays replace, and null
deletes a key. Setting a key to the value it already has is an error. Variables
({{ a.b }}) expand after the merge, in the config and in the skill text.
"""

import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema
import yaml

from exporters import EXPORTERS

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "base"
LAYERS = ROOT / "layers"
TARGETS = ROOT / "targets"
SNAPSHOTS = ROOT / "snapshots"
DIST = ROOT / "dist"
SCHEMA = json.loads((ROOT / "schema" / "connector.schema.json").read_text())

LAYER_ORDER = ("site", "host", "env")
TARGET_META = ("exporter", "layers")
VARIABLE = re.compile(r"\{\{\s*([a-z0-9_.]+)\s*\}\}")
# A fixed timestamp, so the same tree zips to the same bytes.
ZIP_TIME = (1980, 1, 1, 0, 0, 0)


class BuildError(Exception):
    pass


@dataclass
class Override:
    key: str
    layer: str
    before: object
    after: object


@dataclass
class Rendered:
    name: str
    exporter: str
    layers: list
    config: dict
    files: dict
    overrides: list = field(default_factory=list)


def load_yaml(path):
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise BuildError(f"{path.relative_to(ROOT)}: not a mapping")
    return data


def _layer_schema(schema):
    # A layer sets any subset, and its strings may still hold variables, so it is
    # held to keys and types only; patterns apply once the target is merged.
    if isinstance(schema, dict):
        return {k: _layer_schema(v) for k, v in schema.items() if k not in ("required", "pattern")}
    if isinstance(schema, list):
        return [_layer_schema(v) for v in schema]
    return schema


PARTIAL_SCHEMA = _layer_schema(SCHEMA)


def validate(data, source, partial):
    validator = jsonschema.Draft202012Validator(PARTIAL_SCHEMA if partial else SCHEMA)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        lines = [f"  {'.'.join(map(str, e.path)) or '(top)'}: {e.message}" for e in errors]
        raise BuildError(f"{source} does not match schema/connector.schema.json:\n" + "\n".join(lines))


def merge(base, layer, source, overrides, path=()):
    out = dict(base)
    for key, value in layer.items():
        where = path + (key,)
        dotted = ".".join(where)
        if value is None:
            if key not in out:
                raise BuildError(f"{source}: deletes {dotted}, which nothing set")
            overrides.append(Override(dotted, source, out.pop(key), None))
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge(out[key], value, source, overrides, where)
        else:
            if key in out:
                if out[key] == value:
                    raise BuildError(f"{source}: sets {dotted} to the value it already has")
                overrides.append(Override(dotted, source, out[key], value))
            out[key] = copy.deepcopy(value)
    return out


def _lookup(config, dotted):
    value = config
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise BuildError(f"variable {{{{ {dotted} }}}} names nothing in the config")
        value = value[part]
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise BuildError(f"variable {{{{ {dotted} }}}} is not a string or a number")
    return value


def expand_text(text, config, stack=()):
    def replace(match):
        dotted = match.group(1)
        if dotted in stack:
            raise BuildError("variables refer to each other: " + " -> ".join(stack + (dotted,)))
        value = _lookup(config, dotted)
        return expand_text(value, config, stack + (dotted,)) if isinstance(value, str) else str(value)

    return VARIABLE.sub(replace, text)


def expand(value, config):
    if isinstance(value, dict):
        return {k: expand(v, config) for k, v in value.items()}
    if isinstance(value, list):
        return [expand(v, config) for v in value]
    if isinstance(value, str):
        return expand_text(value, config)
    return value


def check_layer_order(layers, source):
    rank = -1
    for name in layers:
        dimension = name.split("/", 1)[0]
        if dimension not in LAYER_ORDER or "/" not in name:
            raise BuildError(f"{source}: layer {name!r} is not site/…, host/… or env/…")
        if LAYER_ORDER.index(dimension) <= rank:
            raise BuildError(f"{source}: layers must run site, host, env, one of each at most; got {layers}")
        rank = LAYER_ORDER.index(dimension)


def read_base(relative):
    path = (BASE / relative).resolve()
    if BASE not in path.parents:
        raise BuildError(f"{relative} points outside base/")
    return path.read_bytes()


def render(name):
    source = f"targets/{name}.yaml"
    target = load_yaml(TARGETS / f"{name}.yaml")
    exporter = target.pop("exporter", None)
    layers = target.pop("layers", [])
    if exporter not in EXPORTERS:
        raise BuildError(f"{source}: exporter {exporter!r} is not one of {sorted(EXPORTERS)}")
    check_layer_order(layers, source)

    overrides = []
    config = load_yaml(BASE / "connector.yaml")
    validate(config, "base/connector.yaml", partial=True)
    for layer in layers:
        layer_source = f"layers/{layer}.yaml"
        data = load_yaml(LAYERS / f"{layer}.yaml")
        validate(data, layer_source, partial=True)
        config = merge(config, data, layer_source, overrides)
    validate(target, source, partial=True)
    config = merge(config, target, source, overrides)

    config = expand(config, config)
    validate(config, f"{name} after merging", partial=False)

    sources = {
        "skill": expand_text(read_base(config["skill"]["source"]).decode(), config),
        "icon": read_base(config["assets"]["icon"]),
    }
    files = EXPORTERS[exporter](config, sources)
    return Rendered(name, exporter, layers, config, files, overrides)


def write_zip(files, path):
    names = sorted(files)
    dirs = {"/".join(n.split("/")[:i]) + "/" for n in names for i in range(1, n.count("/") + 1)}
    with zipfile.ZipFile(path, "w") as archive:
        for entry in sorted(dirs | set(names)):
            info = zipfile.ZipInfo(entry, ZIP_TIME)
            info.create_system = 3
            if entry.endswith("/"):
                info.external_attr = (0o40755 << 16) | 0x10
                archive.writestr(info, b"")
            else:
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, files[entry], compresslevel=9)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise BuildError(f"{path.name} failed its own integrity check")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def source_commit():
    def git(*args):
        return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True).stdout.strip()

    return git("rev-parse", "HEAD") or None, bool(git("status", "--porcelain"))


def snapshot_diff(rendered):
    directory = SNAPSHOTS / rendered.name
    on_disk = {p.relative_to(directory).as_posix(): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    changed = [p for p in sorted(set(on_disk) | set(rendered.files)) if on_disk.get(p) != rendered.files.get(p)]
    return changed


def write_snapshot(rendered):
    directory = SNAPSHOTS / rendered.name
    shutil.rmtree(directory, ignore_errors=True)
    for path, data in rendered.files.items():
        out = directory / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)


def build(all_rendered):
    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir()
    commit, dirty = source_commit()
    report = {"commit": commit, "dirty": dirty, "targets": {}}
    sums = []
    for r in all_rendered:
        zip_name = f"{r.name}-{r.config['version']}.zip"
        write_zip(r.files, DIST / zip_name)
        digest = sha256((DIST / zip_name).read_bytes())
        sums.append(f"{digest}  {zip_name}")
        report["targets"][r.name] = {
            "exporter": r.exporter,
            "layers": r.layers,
            "id": r.config["id"],
            "version": r.config["version"],
            "zip": zip_name,
            "sha256": digest,
            "files": {p: sha256(d) for p, d in sorted(r.files.items())},
            "overrides": [vars(o) for o in r.overrides],
        }
        print(f"{r.name} {r.config['version']} -> dist/{zip_name} ({len(r.files)} files)")
        for o in r.overrides:
            print(f"  {o.layer} sets {o.key}: {o.before!r} -> {o.after!r}")
    (DIST / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    (DIST / "build-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", help="target names (targets/<name>.yaml); all when omitted")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="compare with snapshots/, write nothing")
    mode.add_argument("--write-snapshots", action="store_true", help="rewrite snapshots/")
    args = parser.parse_args(argv)

    names = args.targets or sorted(p.stem for p in TARGETS.glob("*.yaml"))
    try:
        rendered = [render(name) for name in names]
    except (BuildError, FileNotFoundError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if args.check:
        stale = {r.name: snapshot_diff(r) for r in rendered}
        stale = {name: paths for name, paths in stale.items() if paths}
        for name, paths in stale.items():
            print(f"snapshots/{name}/ is stale: {', '.join(paths)}", file=sys.stderr)
        if stale:
            print("run `python build.py --write-snapshots` and commit the result", file=sys.stderr)
            return 1
        print(f"{len(rendered)} targets match snapshots/")
    elif args.write_snapshots:
        for r in rendered:
            write_snapshot(r)
            print(f"wrote snapshots/{r.name}/")
    else:
        build(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
