"""Tests for the SCADA poller.

The Modbus side runs against the real tank process model, so the frames the
poller builds are checked by the server that will answer them in the lab.

Run with: python3 -m unittest discover -s tests -v
"""

import importlib.machinery
import importlib.util
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


poller = load("poller", ROOT / "scada-hmi" / "poller" / "poller.py")
tank_plant = load("tank_plant", ROOT / "modbus-tcp" / "tank_plant.py")


class StubInflux(BaseHTTPRequestHandler):
    """Records what the poller posts and answers 204 like InfluxDB."""

    received = []

    def do_POST(self):  # noqa: N802 - the base class names it
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        StubInflux.received.append(
            {
                "path": self.path,
                "auth": self.headers.get("Authorization", ""),
                "content_type": self.headers.get("Content-Type", ""),
                "body": body,
            }
        )
        self.send_response(204)
        self.end_headers()

    def log_message(self, format, *args):
        """Keep the test output clean."""


class PollerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        threading.Thread(target=tank_plant.tank.run, daemon=True).start()
        cls.server = tank_plant.ModbusServer(("127.0.0.1", 0), tank_plant.ModbusHandler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_reads_the_level_register(self):
        level = poller.read_value("127.0.0.1", self.port, poller.HOLDING_REGISTER, 0)
        self.assertIsInstance(level, int)
        self.assertGreaterEqual(level, 0)
        self.assertLessEqual(level, 100)

    def test_reads_the_pump_coil(self):
        tank_plant.tank.pump = True
        self.assertIs(poller.read_value("127.0.0.1", self.port, poller.COIL, 0), True)
        tank_plant.tank.pump = False
        self.assertIs(poller.read_value("127.0.0.1", self.port, poller.COIL, 0), False)

    def test_unmapped_address_raises(self):
        with self.assertRaises(poller.ModbusError):
            poller.read_value("127.0.0.1", self.port, poller.HOLDING_REGISTER, 5)

    def test_unsupported_function_is_refused_locally(self):
        with self.assertRaises(ValueError):
            poller.read_value("127.0.0.1", self.port, 4, 0)

    def test_line_protocol_format(self):
        line = poller.format_line(42, True, 1000, site="lab")
        self.assertEqual(
            line, "process,site=lab,device=tank level_percent=42i,pump=1i 1000"
        )
        self.assertTrue(poller.format_line(7, 0, 1000, site="plant").endswith(",pump=0i 1000"))

    def test_write_line_sends_token_and_line_protocol(self):
        StubInflux.received.clear()
        server = HTTPServer(("127.0.0.1", 0), StubInflux)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            poller.write_line(
                "process,site=lab,device=tank level_percent=42i,pump=1i 1000",
                url="http://127.0.0.1:%d" % port,
                org="lab",
                bucket="process",
                token="tok",
            )
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(len(StubInflux.received), 1)
        sent = StubInflux.received[0]
        self.assertEqual(
            sent["path"], "/api/v2/write?org=lab&bucket=process&precision=s"
        )
        self.assertEqual(sent["auth"], "Token tok")
        self.assertTrue(sent["content_type"].startswith("text/plain"))
        self.assertEqual(
            sent["body"], "process,site=lab,device=tank level_percent=42i,pump=1i 1000"
        )

    def test_poll_once_reads_and_writes_one_point(self):
        StubInflux.received.clear()
        server = HTTPServer(("127.0.0.1", 0), StubInflux)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()

        original = (
            poller.TANK_HOST,
            poller.TANK_PORT,
            poller.INFLUX_URL,
            poller.INFLUX_TOKEN,
        )
        setattr(poller, "TANK_HOST", "127.0.0.1")
        setattr(poller, "TANK_PORT", self.port)
        setattr(poller, "INFLUX_URL", "http://127.0.0.1:%d" % port)
        setattr(poller, "INFLUX_TOKEN", "tok")
        try:
            line = poller.poll_once(now=1000)
        finally:
            setattr(poller, "TANK_HOST", original[0])
            setattr(poller, "TANK_PORT", original[1])
            setattr(poller, "INFLUX_URL", original[2])
            setattr(poller, "INFLUX_TOKEN", original[3])
            server.shutdown()
            server.server_close()

        self.assertTrue(line.endswith(" 1000"))
        self.assertEqual(len(StubInflux.received), 1)
        self.assertEqual(StubInflux.received[0]["body"], line)

    def test_historian_credentials_are_fixed_lab_values(self):
        # The topology, the Grafana datasource and the README must agree, or
        # the dashboard comes up empty on a fresh deploy.
        topology = (ROOT / "scada-hmi" / "scada-hmi.clab.yml").read_text()
        datasource = (
            ROOT / "scada-hmi" / "grafana" / "provisioning" / "datasources" / "influxdb.yml"
        ).read_text()
        self.assertIn("lab-token-not-a-secret", topology)
        self.assertIn("lab-token-not-a-secret", datasource)
        self.assertIn("INFLUX_ORG: lab", topology)
        self.assertIn("organization: lab", datasource)


if __name__ == "__main__":
    unittest.main()
