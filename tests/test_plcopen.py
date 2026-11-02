"""Tests for the PLCopen checker.

The three demo programs in plc/ must pass. Each failure mode is then
reproduced on a copy, so the checker is proven to catch what it claims.

Run with: python3 -m unittest discover -s tests -v
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLCDIR = ROOT / "plc"

loader = importlib.machinery.SourceFileLoader("plcopen", str(ROOT / "tools" / "plcopen.py"))
spec = importlib.util.spec_from_loader("plcopen", loader)
assert spec is not None
plcopen = importlib.util.module_from_spec(spec)
loader.exec_module(plcopen)


class DemoProgramTests(unittest.TestCase):
    def report(self, name):
        return plcopen.check_root(plcopen.load(PLCDIR / name), name)

    def test_structured_text_passes(self):
        report = self.report("level_control_st.xml")
        self.assertEqual([str(p) for p in report.problems], [])
        self.assertEqual(report.languages, ["ST"])

    def test_instruction_list_passes(self):
        report = self.report("level_control_il.xml")
        self.assertEqual([str(p) for p in report.problems], [])
        self.assertEqual(report.languages, ["IL"])

    def test_ladder_passes(self):
        report = self.report("level_control_ld.xml")
        self.assertEqual([str(p) for p in report.problems], [])
        self.assertEqual(report.languages, ["LD"])

    def test_ladder_nodes_and_connections_are_complete(self):
        root = plcopen.load(PLCDIR / "level_control_ld.xml")
        pou = plcopen.children(plcopen.child(plcopen.child(root, "types"), "pous"), "pou")[0]
        ladder = plcopen.child(plcopen.body_of(pou), "LD")

        ids = plcopen.local_ids(ladder)
        self.assertEqual(
            sorted(ids, key=int),
            ["1", "2", "3", "4", "5", "6", "10", "11", "12", "13", "14"],
        )
        self.assertEqual(ids["1"], "leftPowerRail")
        self.assertEqual(ids["5"], "coil")
        for referenced in plcopen.referenced_ids(ladder):
            self.assertIn(referenced, ids)

    def test_ladder_declares_every_signal_it_uses(self):
        root = plcopen.load(PLCDIR / "level_control_ld.xml")
        pou = plcopen.children(plcopen.child(plcopen.child(root, "types"), "pous"), "pou")[0]
        declared = plcopen.declared_variables(pou)
        self.assertEqual(
            sorted(declared),
            ["interlock", "level_high", "pump_run", "run_latch", "start_cmd"],
        )
        self.assertEqual(declared["level_high"], "BOOL")

    def test_structured_text_derives_the_discrete_signals(self):
        root = plcopen.load(PLCDIR / "level_control_st.xml")
        pou = plcopen.children(plcopen.child(plcopen.child(root, "types"), "pous"), "pou")[0]
        text = plcopen.body_text(plcopen.body_of(pou), "ST")
        self.assertIn("level_high := level >= 70;", text)
        self.assertIn("interlock", text)


class FailureModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="plcopen-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def mutate(self, name, old, new):
        text = (PLCDIR / name).read_text()
        self.assertIn(old, text, "the fixture changed, update this test")
        target = self.tmp / name
        target.write_text(text.replace(old, new, 1))
        return plcopen.check_root(plcopen.load(target), name)

    def messages(self, report):
        return " ".join(str(p) for p in report.errors)

    def test_dangling_connection_is_an_error(self):
        report = self.mutate("level_control_ld.xml", 'refLocalId="4"', 'refLocalId="99"')
        self.assertIn("localId 99, which does not exist", self.messages(report))

    def test_undeclared_variable_is_an_error(self):
        report = self.mutate(
            "level_control_ld.xml", "<variable>start_cmd</variable>", "<variable>start_button</variable>"
        )
        self.assertIn("start_button", self.messages(report))

    def test_duplicate_local_id_is_an_error(self):
        report = self.mutate("level_control_ld.xml", 'localId="3"', 'localId="2"')
        self.assertIn("localId 2 is used more than once", self.messages(report))

    def test_empty_structured_text_is_an_error(self):
        text = (PLCDIR / "level_control_st.xml").read_text()
        start = text.index("<xhtml:p><![CDATA[")
        end = text.index("]]></xhtml:p>")
        target = self.tmp / "level_control_st.xml"
        target.write_text(text[:start] + "<xhtml:p><![CDATA[]]></xhtml:p>" + text[end + len("]]></xhtml:p>"):])
        report = plcopen.check_root(plcopen.load(target), "level_control_st.xml")
        self.assertIn("ST body has no text", self.messages(report))

    def test_missing_namespace_is_an_error(self):
        report = self.mutate(
            "level_control_il.xml",
            'xmlns="http://www.plcopen.org/xml/tc6_0201"',
            'xmlns="http://example.com/not-plcopen"',
        )
        self.assertIn("namespace is not", self.messages(report))

    def test_ladder_without_a_power_rail_is_an_error(self):
        # Every left power rail goes, so the rungs have nothing to start from
        # and the connections that pointed at them dangle.
        text = (PLCDIR / "level_control_ld.xml").read_text()
        stripped = re.sub(r'\s*<leftPowerRail[^>]*>.*?</leftPowerRail>', "", text, flags=re.S)
        target = self.tmp / "level_control_ld.xml"
        target.write_text(stripped)
        report = plcopen.check_root(plcopen.load(target), "level_control_ld.xml")
        self.assertIn("no leftPowerRail", self.messages(report))
        self.assertIn("does not exist", self.messages(report))

    def test_warning_for_an_unused_variable(self):
        report = self.mutate(
            "level_control_il.xml",
            '<variable name="pump_run"><type><BOOL/></type></variable>',
            '<variable name="pump_run"><type><BOOL/></type></variable>'
            '<variable name="spare_signal"><type><BOOL/></type></variable>',
        )
        self.assertTrue(report.ok)
        self.assertIn("spare_signal", " ".join(str(p) for p in report.warnings))


class CommandLineTests(unittest.TestCase):
    def test_lint_returns_zero_for_the_demos(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = plcopen.lint_paths(sorted(PLCDIR.glob("*.xml")), quiet=True)
        self.assertEqual(code, 0)
        self.assertIn("0 error(s)", out.getvalue())

    def test_lint_returns_one_for_a_broken_file(self):
        tmp = Path(tempfile.mkdtemp(prefix="plcopen-cli-"))
        try:
            broken = tmp / "broken.xml"
            broken.write_text("<project>")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = plcopen.lint_paths([broken], quiet=True)
            self.assertEqual(code, 1)
            self.assertIn("not well formed", out.getvalue())
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
