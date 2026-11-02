"""Tests for the repository lifecycle driver.

Run with: python3 -m unittest discover -s tests -v
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

loader = importlib.machinery.SourceFileLoader("labctl", str(ROOT / "labctl"))
spec = importlib.util.spec_from_loader("labctl", loader)
assert spec is not None
labctl = importlib.util.module_from_spec(spec)
loader.exec_module(labctl)


class TopologyFactsTests(unittest.TestCase):
    def test_reads_name_and_management_subnet(self):
        facts = labctl.topology_facts(ROOT / "modbus-tcp" / "modbus-tcp.clab.yml")
        self.assertEqual(facts["name"], "modbus-tcp")
        self.assertEqual(facts["mgmt_subnet"], "172.100.120.0/24")

    def test_reads_every_node(self):
        facts = labctl.topology_facts(ROOT / "modbus-tcp" / "modbus-tcp.clab.yml")
        self.assertEqual(
            sorted(facts["nodes"]), ["client", "plc", "server", "tank"]
        )

    def test_node_without_image_resolves_one(self):
        facts = labctl.topology_facts(ROOT / "modbus-tcp" / "modbus-tcp.clab.yml")
        images = {node["image"] for node in facts["nodes"].values()}
        self.assertTrue(all(images), "every node must resolve an image")

    def test_no_runtime_directories_are_declared(self):
        facts = labctl.topology_facts(ROOT / "modbus-tcp" / "modbus-tcp.clab.yml")
        self.assertEqual(labctl.runtime_dirs(facts), [])


class PinTests(unittest.TestCase):
    def test_rejects_floating_and_bare_images(self):
        self.assertFalse(labctl.is_pinned("alpine"))
        self.assertFalse(labctl.is_pinned("alpine:latest"))
        self.assertFalse(
            labctl.is_pinned("ghcr.io/autonomy-logic/openplc-runtime:latest")
        )

    def test_accepts_tag_and_digest(self):
        self.assertTrue(labctl.is_pinned("alpine:3.20"))
        self.assertTrue(
            labctl.is_pinned("ghcr.io/autonomy-logic/openplc-runtime:v4.3.1")
        )
        self.assertTrue(labctl.is_pinned("registry/app@sha256:" + "a" * 64))


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.labs = labctl.load_manifest()

    def test_every_lab_directory_exists(self):
        for name, lab in self.labs.items():
            self.assertTrue((ROOT / lab["dir"]).is_dir(), name)

    def test_management_subnets_are_unique(self):
        subnets = [
            lab["mgmt_subnet"] for lab in self.labs.values() if lab["mgmt_subnet"]
        ]
        self.assertEqual(len(subnets), len(set(subnets)))


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.labs = labctl.load_manifest()

    def test_refuses_unknown_lab(self):
        with self.assertRaises(labctl.LabError):
            labctl.require_containerlab(self.labs, "not-a-lab")

    def test_destroy_is_scoped_to_one_topology(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = labctl.main(["down", "modbus-tcp", "--dry-run"])
        printed = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("destroy -t modbus-tcp.clab.yml", printed)
        self.assertNotIn("--all", printed)

    def test_deploy_is_scoped_to_one_topology(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = labctl.main(["up", "modbus-tcp", "--dry-run", "--no-preflight"])
        printed = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("deploy -t modbus-tcp.clab.yml", printed)
        self.assertNotIn("--all", printed)

    def test_down_requires_a_lab_argument(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                labctl.main(["down", "--all"])


class SubnetTests(unittest.TestCase):
    def test_overlap_is_reported(self):
        labs = {
            "a": {"mgmt_subnet": "172.111.10.0/24"},
            "b": {"mgmt_subnet": "172.111.10.0/24"},
        }
        self.assertEqual(len(labctl.subnet_problems(labs)), 1)

    def test_invalid_cidr_is_reported(self):
        problems = labctl.subnet_problems({"a": {"mgmt_subnet": "not-an-address"}})
        self.assertEqual(len(problems), 1)
        self.assertIn("not valid CIDR", problems[0])


class CheckTests(unittest.TestCase):
    def test_repository_check_passes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = labctl.main(["check"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("no problems", out.getvalue())


if __name__ == "__main__":
    unittest.main()
