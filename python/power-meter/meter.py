#!/usr/bin/env python3
"""A three-phase power meter that answers Modbus/TCP.

This is the meter a building management system or an EPMS polls. It is not a
simulation of electrical behaviour: the numbers are chosen, not calculated from
a network model. What is real is the register map, the word order, the scaling,
and the Modbus framing. That is the part a poller has to get right.

    python3 meter.py --print
    python3 meter.py --port 15020 --scenario phase-loss

Scenarios exist so a drill has something to see:

    balanced     a healthy feeder
    phase-loss   line 2 at zero volts, current unbalanced, power down
    overload     current at 1.4 times the balanced value
"""

import argparse
import math
import socketserver
import struct
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import registers as reg

MAP_PATH = Path(__file__).resolve().parent / "registers.json"

NOMINAL_VOLTAGE = 230.0
NOMINAL_CURRENT = 120.0
NOMINAL_POWER_FACTOR = 0.94
NOMINAL_FREQUENCY = 50.0


class Meter:
    """The electrical values, and the register image built from them."""

    def __init__(self, entries, scenario="balanced"):
        self.entries = entries
        self.lock = threading.Lock()
        self.scenario = scenario
        self.voltage = [NOMINAL_VOLTAGE] * 3
        self.current = [NOMINAL_CURRENT] * 3
        self.power_factor = NOMINAL_POWER_FACTOR
        self.frequency = NOMINAL_FREQUENCY
        self.energy = 12345.6
        self.breaker = 1
        self.thd = 2.4
        self.apply(scenario)

    def apply(self, scenario):
        """Set the electrical values for a named scenario."""
        with self.lock:
            self.scenario = scenario
            self.voltage = [NOMINAL_VOLTAGE] * 3
            self.current = [NOMINAL_CURRENT] * 3
            self.power_factor = NOMINAL_POWER_FACTOR
            self.thd = 2.4
            if scenario == "balanced":
                return
            if scenario == "phase-loss":
                self.voltage = [NOMINAL_VOLTAGE, 0.0, NOMINAL_VOLTAGE]
                self.current = [NOMINAL_CURRENT * 1.15, 0.0, NOMINAL_CURRENT * 1.15]
                self.power_factor = 0.71
                self.thd = 11.8
                return
            if scenario == "overload":
                self.current = [NOMINAL_CURRENT * 1.4] * 3
                self.thd = 4.9
                return
            raise ValueError("unknown scenario %r" % scenario)

    def power_kw(self):
        watts = sum(v * i for v, i in zip(self.voltage, self.current)) * self.power_factor
        return watts / 1000.0

    def reactive_kvar(self):
        angle = math.acos(max(0.0, min(1.0, self.power_factor)))
        return self.power_kw() * math.tan(angle)

    def snapshot(self):
        """The engineering values, as a dictionary."""
        with self.lock:
            return {
                "voltage_l1_n": self.voltage[0],
                "voltage_l2_n": self.voltage[1],
                "voltage_l3_n": self.voltage[2],
                "current_l1": self.current[0],
                "current_l2": self.current[1],
                "current_l3": self.current[2],
                "active_power_total": self.power_kw(),
                "reactive_power_total": self.reactive_kvar(),
                "power_factor_total": self.power_factor,
                "frequency": self.frequency,
                "energy_import": self.energy,
                "demand_present": self.power_kw(),
                "breaker_state": self.breaker,
                "thd_voltage_l1": self.thd,
                "register_count": 0,
            }

    def register_image(self):
        """The raw 16-bit registers, zero filled where the map is silent."""
        values = self.snapshot()
        size = max(entry.last_address for entry in self.entries) + 1
        image = [0] * size
        for entry in self.entries:
            value = values[entry.name]
            if entry.name == "register_count":
                value = size
            for offset, word in enumerate(reg.encode(entry, value)):
                image[entry.address + offset] = word
        return image


def receive_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


class MeterHandler(socketserver.BaseRequestHandler):
    """One Modbus/TCP connection. Read-only, functions 3 and 4."""

    def meter(self):
        server = self.server
        assert isinstance(server, MeterServer), "the handler needs a MeterServer"
        return server.meter

    def handle(self):
        while True:
            header = receive_exact(self.request, 7)
            if header is None:
                return
            transaction, protocol, length, unit = struct.unpack(">HHHB", header)
            if protocol != 0 or not 2 <= length <= 254:
                return
            pdu = receive_exact(self.request, length - 1)
            if pdu is None:
                return
            response = self.process(pdu)
            reply = struct.pack(">HHHB", transaction, 0, len(response) + 1, unit) + response
            self.request.sendall(reply)

    def process(self, pdu):
        function = pdu[0]
        if function not in (3, 4) or len(pdu) != 5:
            return bytes((function | 0x80, 1))

        address, quantity = struct.unpack(">HH", pdu[1:5])
        if not 1 <= quantity <= 125:
            return bytes((function | 0x80, 3))

        image = self.meter().register_image()
        if address + quantity > len(image):
            return bytes((function | 0x80, 2))

        payload = b"".join(struct.pack(">H", word) for word in image[address:address + quantity])
        return bytes((function, len(payload))) + payload


class MeterServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, meter):
        self.meter = meter
        super().__init__(address, MeterHandler)


def main(argv):
    parser = argparse.ArgumentParser(description="A Modbus/TCP three-phase power meter.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15020)
    parser.add_argument("--scenario", default="balanced", choices=["balanced", "phase-loss", "overload"])
    parser.add_argument("--print", dest="show", action="store_true", help="print the decode and exit")
    args = parser.parse_args(argv)

    entries = reg.load_map(MAP_PATH)
    meter = Meter(entries, args.scenario)

    if args.show:
        image = meter.register_image()
        print("register image: %d registers" % len(image))
        for entry in entries:
            offset = entry.address
            raw = image[offset:offset + entry.words]
            value = reg.decode(entry, raw)
            print(
                "  %-22s %2d %-8s %-10s raw=%s value=%g %s"
                % (entry.name, entry.address, entry.kind, entry.word_order, raw, value, entry.unit)
            )
        return 0

    with MeterServer((args.host, args.port), meter) as server:
        print(
            "power meter listening on %s:%d, scenario %s, %d registers"
            % (args.host, args.port, args.scenario, len(meter.register_image())),
            flush=True,
        )
        server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
