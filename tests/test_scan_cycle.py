"""Tests for the scan-cycle engine and the two Python control programs.

These tests are the point of `python/scan-cycle/`. Each one states a rule that
the PLC program in `plc/` must obey, and proves it in a millisecond.
"""

import importlib.machinery
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANDIR = ROOT / "python" / "scan-cycle"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


engine = load("scan_engine", SCANDIR / "engine.py")
programs = load("scan_programs", SCANDIR / "programs.py")


class TimerTests(unittest.TestCase):
    def test_counts_only_while_enabled(self):
        timer = engine.Timer(3)
        self.assertFalse(timer.update(True))
        self.assertFalse(timer.update(True))
        self.assertTrue(timer.update(True))
        self.assertEqual(timer.elapsed, 3)

    def test_resets_when_the_enable_falls(self):
        timer = engine.Timer(3)
        timer.update(True)
        timer.update(True)
        timer.update(False)
        self.assertEqual(timer.elapsed, 0)
        self.assertFalse(timer.done)
        self.assertFalse(timer.update(True))
        self.assertEqual(timer.elapsed, 1)

    def test_a_zero_preset_is_rejected(self):
        with self.assertRaises(ValueError):
            engine.Timer(0)


class LevelControlTests(unittest.TestCase):
    def plc(self):
        return engine.Plc(programs.level_control)

    def base(self, **changes):
        inputs = {"start_cmd": False, "stop_cmd": False, "interlock": True, "level": 10}
        inputs.update(changes)
        return inputs

    def test_pump_starts_on_the_start_command(self):
        plc = self.plc()
        self.assertTrue(plc.scan(self.base(start_cmd=True))["pump_run"])

    def test_pump_holds_itself_in_after_the_button_is_released(self):
        plc = self.plc()
        plc.scan(self.base(start_cmd=True))
        self.assertTrue(plc.scan(self.base())["pump_run"])
        self.assertTrue(plc.scan(self.base())["pump_run"])

    def test_high_level_stops_the_pump_and_clears_the_latch(self):
        plc = self.plc()
        plc.scan(self.base(start_cmd=True))
        self.assertFalse(plc.scan(self.base(level=75))["pump_run"])
        # The latch is gone, so the pump stays off when the level falls.
        self.assertFalse(plc.scan(self.base(level=40))["pump_run"])

    def test_an_open_interlock_stops_the_pump(self):
        plc = self.plc()
        plc.scan(self.base(start_cmd=True))
        self.assertFalse(plc.scan(self.base(interlock=False))["pump_run"])

    def test_the_stop_command_stops_the_pump(self):
        plc = self.plc()
        plc.scan(self.base(start_cmd=True))
        self.assertFalse(plc.scan(self.base(stop_cmd=True))["pump_run"])

    def test_the_returned_image_is_a_copy(self):
        plc = self.plc()
        image = plc.scan(self.base(start_cmd=True))
        image["pump_run"] = False
        self.assertTrue(plc.outputs["pump_run"])

    def test_the_latch_is_visible_in_memory(self):
        plc = self.plc()
        plc.scan(self.base(start_cmd=True))
        self.assertTrue(plc.memory["run_latch"])
        self.assertFalse(plc.memory["level_high"])


class SequenceTests(unittest.TestCase):
    def plc(self):
        return engine.Plc(programs.sequence)

    def base(self, **changes):
        inputs = {"start_cmd": False, "stop_cmd": False, "fault": False}
        inputs.update(changes)
        return inputs

    def test_the_pump_starts_one_scan_after_the_start_command(self):
        plc = self.plc()
        self.assertFalse(plc.scan(self.base(start_cmd=True))["pump_run"])
        self.assertEqual(plc.memory["step"], 1)
        self.assertTrue(plc.scan(self.base(start_cmd=True))["pump_run"])

    def test_a_fault_de_energizes_the_pump_in_the_same_scan(self):
        plc = self.plc()
        plc.scan(self.base(start_cmd=True))
        plc.scan(self.base(start_cmd=True))
        self.assertTrue(plc.outputs["pump_run"])
        outputs = plc.scan(self.base(start_cmd=True, fault=True))
        self.assertFalse(outputs["pump_run"])

    def test_the_alarm_latches_until_the_operator_acknowledges(self):
        plc = self.plc()
        plc.scan(self.base(start_cmd=True))
        plc.scan(self.base(start_cmd=True))
        # The fault scan moves to step 2 but the alarm shows from the next scan.
        self.assertFalse(plc.scan(self.base(start_cmd=True, fault=True))["alarm"])
        self.assertEqual(plc.memory["step"], 2)

        # Fault clears: the alarm stays on and the step moves to 3.
        self.assertTrue(plc.scan(self.base(start_cmd=True))["alarm"])
        self.assertEqual(plc.memory["step"], 3)

        # Still latched while the operator holds the start button.
        self.assertTrue(plc.scan(self.base(start_cmd=True))["alarm"])
        self.assertEqual(plc.memory["step"], 3)

        # Releasing the start button acknowledges the alarm. The step moves to
        # 0 during that scan, and the alarm output drops on the scan after it,
        # because the output was still true while step 3 was active.
        plc.scan(self.base(start_cmd=False))
        self.assertEqual(plc.memory["step"], 0)
        self.assertFalse(plc.scan(self.base(start_cmd=False))["alarm"])

    def test_the_sequence_returns_to_idle_when_the_start_is_released(self):
        plc = self.plc()
        plc.scan(self.base(start_cmd=True))
        plc.scan(self.base(start_cmd=True, fault=True))
        plc.scan(self.base(start_cmd=True))   # step 2, alarm
        plc.scan(self.base(start_cmd=True))   # step 3, alarm latched
        plc.scan(self.base(start_cmd=False))  # step 0, alarm still true
        self.assertEqual(plc.memory["step"], 0)
        plc.scan(self.base(start_cmd=False))
        self.assertFalse(plc.outputs["alarm"])

    def test_a_pump_that_runs_too_long_forces_a_fault(self):
        plc = self.plc()
        plc.scan(self.base(start_cmd=True))
        for _ in range(programs.RUN_TOO_LONG_SCANS):
            plc.scan(self.base(start_cmd=True))
        self.assertTrue(plc.memory["fault_seen"])
        # The fault is seen on the next scan, because the timer sets it after
        # the case statement runs, exactly as the structured text does.
        plc.scan(self.base(start_cmd=True))
        self.assertEqual(plc.memory["step"], 2)

    def test_an_unknown_step_goes_to_the_fault_step(self):
        plc = self.plc()
        plc.memory["step"] = 99
        outputs = plc.scan(self.base(start_cmd=True))
        self.assertEqual(plc.memory["step"], 2)
        self.assertFalse(outputs["pump_run"])

    def test_the_timer_resets_when_the_sequence_leaves_step_one(self):
        plc = self.plc()
        plc.scan(self.base(start_cmd=True))
        plc.scan(self.base(start_cmd=True))
        plc.scan(self.base(start_cmd=True))
        self.assertGreater(plc.timers["step_timer"].elapsed, 0)
        plc.scan(self.base(start_cmd=True, stop_cmd=True))
        self.assertEqual(plc.timers["step_timer"].elapsed, 0)


class TableTests(unittest.TestCase):
    def test_the_table_has_one_row_per_scan_and_a_header(self):
        plc = engine.Plc(programs.level_control)
        rows = plc.run(
            [
                {"start_cmd": False, "stop_cmd": False, "interlock": True, "level": 10},
                {"start_cmd": True, "stop_cmd": False, "interlock": True, "level": 10},
            ]
        )
        table = engine.format_run(rows).splitlines()
        self.assertEqual(len(table), 3)
        self.assertIn("pump_run", table[0])
        self.assertTrue(table[2].split()[-1] == "1")

    def test_an_empty_run_prints_nothing(self):
        self.assertEqual(engine.format_run([]), "")


if __name__ == "__main__":
    unittest.main()
