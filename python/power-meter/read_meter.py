#!/usr/bin/env python3
"""Read the meter and print engineering values, using the register map.

    python3 read_meter.py --host 127.0.0.1 --port 15020

This is the smallest useful poller: one Modbus/TCP read of the whole map, then
decode. It uses the map, so a register that moves in the JSON moves here too.
"""

import argparse
import socket
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import registers as reg

MAP_PATH = Path(__file__).resolve().parent / "registers.json"


def read_holding(host, port, address, quantity, unit=1):
    """One Modbus/TCP read of holding registers, function 3."""
    pdu = struct.pack(">BHH", 3, address, quantity)
    request = struct.pack(">HHHB", 1, 0, len(pdu) + 1, unit) + pdu

    with socket.create_connection((host, port), timeout=5) as client:
        client.sendall(request)
        header = client.recv(7)
        if len(header) != 7:
            raise RuntimeError("short header from %s:%d" % (host, port))
        _, _, length, _ = struct.unpack(">HHHB", header)
        body = b""
        while len(body) < length - 1:
            body += client.recv(length - 1 - len(body))

    if body[0] & 0x80:
        raise RuntimeError("Modbus exception %d for function %d" % (body[1], body[0] & 0x7F))
    return list(struct.unpack(">%dH" % quantity, body[2:]))


def main(argv):
    parser = argparse.ArgumentParser(description="Read the power meter through its register map.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15020)
    parser.add_argument("--unit", type=int, default=1)
    args = parser.parse_args(argv)

    entries = reg.load_map(MAP_PATH)
    count = max(item.last_address for item in entries) + 1

    words = read_holding(args.host, args.port, 0, count, args.unit)
    values = reg.decode_block(entries, words, 0, count)

    for item in entries:
        if item.name not in values:
            continue
        value = values[item.name]
        print("%-22s %10.2f %s" % (item.name, value, item.unit))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
