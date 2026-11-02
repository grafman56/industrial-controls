#!/usr/bin/env python3
"""Poll the tank process over Modbus/TCP and write one point per interval.

No Modbus library is used. The frames are built here, so the frame you see in
a capture is the frame in the code. That is the point of the exercise.

Environment:
  TANK_HOST      Modbus server, default 172.111.20.10
  TANK_PORT      default 5020
  TANK_UNIT      unit id in the MBAP header, default 1
  INFLUX_URL     default http://172.111.20.31:8086
  INFLUX_ORG     default lab
  INFLUX_BUCKET  default process
  INFLUX_TOKEN   default lab-token-not-a-secret
  POLL_INTERVAL  seconds between polls, default 1
  SITE           tag written with every point, default lab

Run once, for a smoke test:

  python poller.py --once
"""

import os
import socket
import struct
import sys
import time
import urllib.error
import urllib.request

TANK_HOST = os.environ.get("TANK_HOST", "172.111.20.10")
TANK_PORT = int(os.environ.get("TANK_PORT", "5020"))
TANK_UNIT = int(os.environ.get("TANK_UNIT", "1"))
INFLUX_URL = os.environ.get("INFLUX_URL", "http://172.111.20.31:8086").rstrip("/")
INFLUX_ORG = os.environ.get("INFLUX_ORG", "lab")
INFLUX_BUCKET = os.environ.get("INFLUX_BUCKET", "process")
INFLUX_TOKEN = os.environ.get("INFLUX_TOKEN", "lab-token-not-a-secret")
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "1"))
SITE = os.environ.get("SITE", "lab")
MEASUREMENT = "process"

HOLDING_REGISTER = 3
COIL = 1


class ModbusError(RuntimeError):
    """The device answered with an exception, or the answer was malformed."""


def recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ModbusError("connection closed after %d of %d bytes" % (len(data), size))
        data.extend(chunk)
    return bytes(data)


def read_value(host, port, function, address, unit=TANK_UNIT, timeout=3.0):
    """Read one value. Function 3 returns an int, function 1 returns a bool."""
    if function not in (HOLDING_REGISTER, COIL):
        raise ValueError("only function 1 and 3 are implemented")
    pdu = struct.pack(">BHH", function, address, 1)
    header = struct.pack(">HHHB", 1, 0, len(pdu) + 1, unit)
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(header + pdu)
        reply_header = recv_exact(sock, 7)
        _transaction, protocol, length, _unit = struct.unpack(">HHHB", reply_header)
        if protocol != 0 or length < 2:
            raise ModbusError("malformed MBAP header")
        body = recv_exact(sock, length - 1)
    if body[0] & 0x80:
        raise ModbusError("exception code %d from unit %d" % (body[1], unit))
    if body[0] != function:
        raise ModbusError("expected function %d, got %d" % (function, body[0]))
    count = body[1]
    if count != (2 if function == HOLDING_REGISTER else 1):
        raise ModbusError("unexpected byte count %d" % count)
    if function == HOLDING_REGISTER:
        return struct.unpack(">H", body[2:4])[0]
    return bool(body[2] & 0x01)


def format_line(level, pump, timestamp, site=None):
    """InfluxDB line protocol. Integer fields carry the i suffix."""
    site = SITE if site is None else site
    return "%s,site=%s,device=tank level_percent=%di,pump=%di %d" % (
        MEASUREMENT,
        site,
        int(level),
        int(bool(pump)),
        int(timestamp),
    )


def write_line(line, url=None, org=None, bucket=None, token=None):
    # Resolved at call time, not at import time, so a test or a caller can
    # point the poller at another historian without reloading the module.
    url = (INFLUX_URL if url is None else url).rstrip("/")
    org = INFLUX_ORG if org is None else org
    bucket = INFLUX_BUCKET if bucket is None else bucket
    token = INFLUX_TOKEN if token is None else token
    target = "%s/api/v2/write?org=%s&bucket=%s&precision=s" % (url, org, bucket)
    request = urllib.request.Request(
        target,
        data=line.encode("utf-8"),
        headers={
            "Authorization": "Token " + token,
            "Content-Type": "text/plain; charset=utf-8",
        },
        method="POST",
    )
    # urlopen raises HTTPError on any non-2xx status, so a returned response
    # means the point was accepted.
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status


def poll_once(now=None):
    """Read the process and write one point. Returns the line that was sent."""
    level = read_value(TANK_HOST, TANK_PORT, HOLDING_REGISTER, 0)
    pump = read_value(TANK_HOST, TANK_PORT, COIL, 0)
    line = format_line(level, pump, time.time() if now is None else now)
    write_line(line)
    return line


def main(argv):
    once = "--once" in argv
    print(
        "polling %s:%d every %ss, writing to %s/%s"
        % (TANK_HOST, TANK_PORT, POLL_INTERVAL, INFLUX_URL, INFLUX_BUCKET),
        flush=True,
    )
    while True:
        try:
            line = poll_once()
            print("wrote %s" % line, flush=True)
        except (ModbusError, OSError, urllib.error.URLError) as error:
            print("poll failed: %s" % error, flush=True)
            if once:
                return 1
        if once:
            return 0
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
