"""Tests for the power meter and its register map.

The word order and scaling tests exist because those two mistakes produce a
plausible number, not an error. A test is the only cheap way to catch them.
"""

import importlib.machinery
import importlib.util
import socket
import struct
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METERDIR = ROOT / "python" / "power-meter"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


registers = load("meter_registers", METERDIR / "registers.py")
meter_module = load("power_meter", METERDIR / "meter.py")
MAP_PATH = METERDIR / "registers.json"


def entry(entries, name):
    for item in entries:
        if item.name == name:
            return item
    raise KeyError(name)


class MapTests(unittest.TestCase):
    def setUp(self):
        self.entries = registers.load_map(MAP_PATH)

    def test_the_map_covers_26_registers(self):
        self.assertEqual(len(self.entries), 15)
        self.assertEqual(max(item.last_address for item in self.entries), 25)
        self.assertEqual(entry(self.entries, "register_count").address, 25)

    def test_the_map_loads_twice_with_the_same_layout(self):
        first = [(item.address, item.name) for item in self.entries]
        second = [(item.address, item.name) for item in registers.load_map(MAP_PATH)]
        self.assertEqual(first, second)

    def test_an_overlapping_map_is_rejected(self):
        import json
        import tempfile

        bad = {
            "registers": [
                {"name": "a", "address": 0, "type": "float32"},
                {"name": "b", "address": 1, "type": "float32"},
            ]
        }
        path = Path(tempfile.mkdtemp(prefix="map-")) / "bad.json"
        path.write_text(json.dumps(bad))
        with self.assertRaises(ValueError):
            registers.load_map(path)

    def test_every_entry_round_trips(self):
        values = {
            "voltage_l1_n": 231.7,
            "voltage_l2_n": 229.4,
            "voltage_l3_n": 230.9,
            "current_l1": 118.2,
            "current_l2": 121.4,
            "current_l3": 119.8,
            "active_power_total": 76.5,
            "reactive_power_total": 27.1,
            "power_factor_total": 0.94,
            "frequency": 50.01,
            "energy_import": 98765.4,
            "demand_present": 76.5,
            "breaker_state": 1,
            "thd_voltage_l1": 2.4,
            "register_count": 26,
        }
        for item in self.entries:
            words = registers.encode(item, values[item.name])
            self.assertEqual(len(words), item.words)
            decoded = registers.decode(item, words)
            if item.kind == "float32":
                self.assertAlmostEqual(decoded, values[item.name], places=2)
            else:
                self.assertAlmostEqual(decoded, values[item.name], places=1)


class WordOrderTests(unittest.TestCase):
    def setUp(self):
        self.entries = registers.load_map(MAP_PATH)

    def test_energy_sent_low_word_first_is_decoded_low_word_first(self):
        item = entry(self.entries, "energy_import")
        words = registers.encode(item, 12345.6)
        self.assertEqual(registers.decode(item, words), 12345.6)

    def test_reading_low_word_first_data_as_high_word_first_gives_a_wrong_number(self):
        item = entry(self.entries, "energy_import")
        words = registers.encode(item, 12345.6)

        high_first = registers.Entry(
            {"name": "energy_import", "address": 20, "type": "uint32", "word_order": "high_first", "scale": 0.1}
        )
        wrong = registers.decode(high_first, words)
        self.assertNotAlmostEqual(wrong, 12345.6, places=1)

    def test_a_signed_reading_of_a_float32_register_pair_is_wrong(self):
        item = entry(self.entries, "voltage_l1_n")
        words = registers.encode(item, 230.0)
        as_integer = struct.unpack(">I", struct.pack(">HH", *words))[0]
        self.assertNotEqual(as_integer, 230)


class MeterTests(unittest.TestCase):
    def setUp(self):
        self.entries = registers.load_map(MAP_PATH)

    def test_the_balanced_scenario_is_three_phase_and_symmetric(self):
        meter = meter_module.Meter(self.entries)
        snapshot = meter.snapshot()
        self.assertEqual(snapshot["voltage_l1_n"], snapshot["voltage_l2_n"])
        self.assertAlmostEqual(snapshot["active_power_total"], 77.8, places=1)
        self.assertGreater(snapshot["reactive_power_total"], 0)

    def test_phase_loss_zeroes_one_line_and_drops_the_power(self):
        balanced = meter_module.Meter(self.entries).snapshot()
        meter = meter_module.Meter(self.entries, "phase-loss")
        snapshot = meter.snapshot()
        self.assertEqual(snapshot["voltage_l2_n"], 0.0)
        self.assertEqual(snapshot["current_l2"], 0.0)
        self.assertLess(snapshot["active_power_total"], balanced["active_power_total"])
        self.assertGreater(snapshot["thd_voltage_l1"], balanced["thd_voltage_l1"])

    def test_overload_raises_the_current(self):
        snapshot = meter_module.Meter(self.entries, "overload").snapshot()
        self.assertAlmostEqual(snapshot["current_l1"], 168.0, places=2)

    def test_an_unknown_scenario_is_rejected(self):
        with self.assertRaises(ValueError):
            meter_module.Meter(self.entries, "melted")

    def test_the_register_image_is_the_size_the_map_says(self):
        image = meter_module.Meter(self.entries).register_image()
        self.assertEqual(len(image), 26)
        count = entry(self.entries, "register_count")
        self.assertEqual(image[count.address], 26)


class ServerTests(unittest.TestCase):
    def setUp(self):
        entries = registers.load_map(MAP_PATH)
        self.meter = meter_module.Meter(entries)
        self.server = meter_module.MeterServer(("127.0.0.1", 0), self.meter)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def read(self, function, address, quantity):
        pdu = struct.pack(">BHH", function, address, quantity)
        request = struct.pack(">HHHB", 0x1234, 0, len(pdu) + 1, 1) + pdu
        with socket.create_connection(("127.0.0.1", self.port), timeout=5) as client:
            client.sendall(request)
            header = client.recv(7)
            transaction, protocol, length, unit = struct.unpack(">HHHB", header)
            body = b""
            while len(body) < length - 1:
                body += client.recv(length - 1 - len(body))
        return transaction, unit, body

    def test_a_read_of_the_whole_map_returns_the_voltage(self):
        transaction, unit, body = self.read(3, 0, 26)
        self.assertEqual(transaction, 0x1234)
        self.assertEqual(unit, 1)
        self.assertEqual(body[0], 3)
        self.assertEqual(body[1], 52)
        words = list(struct.unpack(">26H", body[2:]))
        entries = registers.load_map(MAP_PATH)
        self.assertAlmostEqual(registers.decode(entry(entries, "voltage_l1_n"), words[0:2]), 230.0)
        self.assertAlmostEqual(registers.decode(entry(entries, "energy_import"), words[20:22]), 12345.6, places=1)

    def test_function_4_reads_the_same_registers(self):
        _, _, body = self.read(4, 12, 2)
        self.assertEqual(body[0], 4)

    def test_a_read_past_the_end_is_an_exception_two(self):
        _, _, body = self.read(3, 20, 10)
        self.assertEqual(body, bytes((0x83, 2)))

    def test_an_unsupported_function_is_an_exception_one(self):
        _, _, body = self.read(6, 0, 1)
        self.assertEqual(body, bytes((0x86, 1)))

    def test_a_partial_block_is_not_decoded(self):
        entries = registers.load_map(MAP_PATH)
        image = self.meter.register_image()
        values = registers.decode_block(entries, image, 0, 1)
        self.assertEqual(values, {})

    def test_the_example_poller_reads_the_whole_map(self):
        poller = load("power_meter_reader", METERDIR / "read_meter.py")
        words = poller.read_holding("127.0.0.1", self.port, 0, 26)
        entries = registers.load_map(MAP_PATH)
        values = registers.decode_block(entries, words, 0, 26)
        self.assertAlmostEqual(values["voltage_l1_n"], 230.0, places=1)
        self.assertAlmostEqual(values["active_power_total"], 77.8, places=1)


if __name__ == "__main__":
    unittest.main()
