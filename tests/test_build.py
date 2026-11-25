import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build  # noqa: E402


class MergeTest(unittest.TestCase):
    def merge(self, base, layer):
        overrides = []
        return build.merge(base, layer, "layer.yaml", overrides), overrides

    def test_objects_merge_key_by_key(self):
        out, _ = self.merge({"mcp": {"url": "a", "timeout_ms": 1}}, {"mcp": {"url": "b"}})
        self.assertEqual(out, {"mcp": {"url": "b", "timeout_ms": 1}})

    def test_arrays_replace(self):
        out, _ = self.merge({"examples": {"zh": ["a", "b"]}}, {"examples": {"zh": ["c"]}})
        self.assertEqual(out["examples"]["zh"], ["c"])

    def test_null_deletes(self):
        out, overrides = self.merge({"host": {"ui_cards": True, "workbuddy": {}}}, {"host": {"workbuddy": None}})
        self.assertEqual(out, {"host": {"ui_cards": True}})
        self.assertEqual((overrides[0].key, overrides[0].after), ("host.workbuddy", None))

    def test_deleting_what_nothing_set_fails(self):
        with self.assertRaisesRegex(build.BuildError, "deletes host.workbuddy, which nothing set"):
            self.merge({"host": {}}, {"host": {"workbuddy": None}})

    def test_setting_the_same_value_fails(self):
        with self.assertRaisesRegex(build.BuildError, "sets mcp.url to the value it already has"):
            self.merge({"mcp": {"url": "a"}}, {"mcp": {"url": "a"}})

    def test_changes_are_reported_and_first_sets_are_not(self):
        _, overrides = self.merge({"version": "0.1.0"}, {"version": "0.1.1", "id": "meshy"})
        self.assertEqual([(o.key, o.layer, o.before, o.after) for o in overrides],
                         [("version", "layer.yaml", "0.1.0", "0.1.1")])

    def test_the_input_is_left_alone(self):
        base = {"mcp": {"url": "a"}}
        self.merge(base, {"mcp": {"url": "b"}})
        self.assertEqual(base, {"mcp": {"url": "a"}})


class VariableTest(unittest.TestCase):
    def test_a_variable_may_name_another(self):
        config = {"skill": {"name": "{{ mcp.server_key }}-skill"}, "mcp": {"server_key": "meshy-3d"},
                  "title": "{{ skill.name }}"}
        self.assertEqual(build.expand(config, config)["title"], "meshy-3d-skill")

    def test_an_unknown_variable_fails(self):
        with self.assertRaisesRegex(build.BuildError, "names nothing"):
            build.expand_text("{{ mcp.server_key }}", {"mcp": {}})

    def test_a_cycle_fails(self):
        config = {"a": "{{ b }}", "b": "{{ a }}"}
        with self.assertRaisesRegex(build.BuildError, "refer to each other"):
            build.expand(config, config)

    def test_an_object_cannot_be_inlined(self):
        with self.assertRaisesRegex(build.BuildError, "not a string or a number"):
            build.expand_text("{{ mcp }}", {"mcp": {"url": "a"}})


class SchemaTest(unittest.TestCase):
    def test_a_layer_may_hold_any_subset(self):
        build.validate({"mcp": {"url": "https://mcp.meshy.cn/mcp"}}, "layer.yaml", partial=True)

    def test_a_misspelt_key_fails(self):
        with self.assertRaisesRegex(build.BuildError, "'ulr' was unexpected"):
            build.validate({"mcp": {"ulr": "https://x"}}, "layer.yaml", partial=True)

    def test_a_wrong_type_fails_in_a_layer(self):
        with self.assertRaisesRegex(build.BuildError, "mcp.timeout_ms"):
            build.validate({"mcp": {"timeout_ms": "30s"}}, "layer.yaml", partial=True)

    def test_a_merged_target_needs_every_required_field(self):
        config = build.render("workbuddy-cn").config
        del config["version"]
        with self.assertRaisesRegex(build.BuildError, "'version' is a required property"):
            build.validate(config, "workbuddy-cn", partial=False)

    def test_patterns_apply_after_the_merge(self):
        config = build.render("workbuddy-cn").config
        config["mcp"]["url"] = "http://mcp.meshy.cn/mcp"
        with self.assertRaisesRegex(build.BuildError, "mcp.url"):
            build.validate(config, "workbuddy-cn", partial=False)


class LayerOrderTest(unittest.TestCase):
    def test_site_host_env(self):
        build.check_layer_order(["site/ai", "host/workbuddy", "env/staging"], "t.yaml")

    def test_out_of_order_fails(self):
        with self.assertRaisesRegex(build.BuildError, "must run site, host, env"):
            build.check_layer_order(["host/workbuddy", "site/ai"], "t.yaml")

    def test_two_of_a_dimension_fail(self):
        with self.assertRaisesRegex(build.BuildError, "must run site, host, env"):
            build.check_layer_order(["site/ai", "site/cn"], "t.yaml")

    def test_an_unknown_dimension_fails(self):
        with self.assertRaisesRegex(build.BuildError, "is not site"):
            build.check_layer_order(["region/cn"], "t.yaml")


class TargetsTest(unittest.TestCase):
    def test_every_target_matches_its_snapshot(self):
        for path in sorted(build.TARGETS.glob("*.yaml")):
            with self.subTest(target=path.stem):
                self.assertEqual(build.snapshot_diff(build.render(path.stem)), [])

    def test_the_skill_takes_the_server_key(self):
        self.assertIn("skills/meshy-3d-skill/SKILL.md", build.render("workbuddy-cn").files)
        self.assertIn("skills/meshy-skill/SKILL.md", build.render("workbuddy-ai").files)


class WorkBuddyExporterTest(unittest.TestCase):
    # Every shipped target has the same zh and en names, and an id equal to its
    # server key, so their snapshots cannot tell those apart; this config can.
    CONFIG = {
        "id": "meshy-x", "version": "1.2.3", "published": False,
        "display_name": {"zh": "名字", "en": "Name"},
        "description": {"zh": "描述", "en": "Description"},
        "examples": {"zh": ["例子"], "en": ["Example"]},
        "skill": {"name": "meshy-x-skill", "source": "skill/SKILL.md"},
        "mcp": {"url": "https://mcp.example/mcp", "transport": "streamable-http", "auth": "oauth",
                "timeout_ms": 1500, "server_key": "meshy-key"},
        "assets": {"icon": "assets/icon.svg"},
        "host": {"ui_cards": True, "workbuddy": {"min_version": "9.9.9"}},
    }

    def export(self, config=None):
        import json
        from exporters import workbuddy
        files = workbuddy.export(config or self.CONFIG, {"skill": "skill text", "icon": b"<svg/>"})
        return files, json.loads(files["connector-meta.json"]), json.loads(files["mcp.json"])

    def test_fields_land_where_workbuddy_reads_them(self):
        files, meta, servers = self.export()
        self.assertEqual(
            {k: meta[k] for k in ("name", "name_zh", "name_en", "description", "description_zh",
                                  "description_en", "source", "version", "examples_zh", "examples_en",
                                  "minWorkbuddyVersion")},
            {"name": "Name", "name_zh": "名字", "name_en": "Name", "description": "Description",
             "description_zh": "描述", "description_en": "Description", "source": "meshy-x",
             "version": "1.2.3", "examples_zh": ["例子"], "examples_en": ["Example"],
             "minWorkbuddyVersion": "9.9.9"})
        self.assertEqual(meta["server_auth"]["data"]["mcp_oauth"]["server_url"], "https://mcp.example/mcp")
        self.assertEqual(servers, {"mcpServers": {"meshy-key": {"type": "streamableHttp",
                                                              "url": "https://mcp.example/mcp", "timeout": 1500}}})
        self.assertEqual(files["skills/meshy-x-skill/SKILL.md"], b"skill text")
        self.assertEqual(files["icon.svg"], b"<svg/>")

    def test_it_needs_the_workbuddy_host_layer(self):
        config = dict(self.CONFIG, host={"ui_cards": True})
        with self.assertRaisesRegex(ValueError, "needs host.workbuddy"):
            self.export(config)


class ZipTest(unittest.TestCase):
    FILES = {"mcp.json": b"{}\n", "skills/meshy-skill/SKILL.md": b"skill\n", "connector-meta.json": b"{}\n"}

    def test_the_same_files_zip_to_the_same_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp, "a.zip"), Path(tmp, "b.zip")
            build.write_zip(self.FILES, first)
            build.write_zip(dict(reversed(list(self.FILES.items()))), second)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_entries_are_sorted_with_their_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "a.zip")
            build.write_zip(self.FILES, path)
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(archive.namelist(), ["connector-meta.json", "mcp.json", "skills/",
                                                      "skills/meshy-skill/", "skills/meshy-skill/SKILL.md"])
                self.assertEqual({i.filename: i.external_attr >> 16 for i in archive.infolist()}["mcp.json"],
                                 0o100644)


if __name__ == "__main__":
    unittest.main()
