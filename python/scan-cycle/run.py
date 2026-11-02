#!/usr/bin/env python3
"""Run a control program in the scan-cycle engine."""
USAGE = """Run a scenario through the scan-cycle engine and print the timing diagram.

    python3 python/scan-cycle/run.py level-control
    python3 python/scan-cycle/run.py sequence

Each row is one scan. Read down a column to see a signal change over time,
which is what a timing diagram shows and what a print statement does not.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import engine
import programs

LEVEL_CONTROL = [
    {"start_cmd": False, "stop_cmd": False, "interlock": True, "level": 10},
    {"start_cmd": True, "stop_cmd": False, "interlock": True, "level": 20},
    {"start_cmd": False, "stop_cmd": False, "interlock": True, "level": 40},
    {"start_cmd": False, "stop_cmd": False, "interlock": True, "level": 60},
    {"start_cmd": False, "stop_cmd": False, "interlock": True, "level": 72},
    {"start_cmd": False, "stop_cmd": False, "interlock": True, "level": 50},
    {"start_cmd": False, "stop_cmd": False, "interlock": True, "level": 74},
    {"start_cmd": False, "stop_cmd": False, "interlock": False, "level": 30},
]

SEQUENCE = [
    {"start_cmd": False, "stop_cmd": False, "fault": False},
    {"start_cmd": True, "stop_cmd": False, "fault": False},
    {"start_cmd": True, "stop_cmd": False, "fault": False},
    {"start_cmd": True, "stop_cmd": False, "fault": True},
    {"start_cmd": True, "stop_cmd": False, "fault": False},
    {"start_cmd": False, "stop_cmd": False, "fault": False},
]


def main(argv):
    if len(argv) != 1 or argv[0] not in ("level-control", "sequence"):
        print(USAGE.strip())
        return 2

    if argv[0] == "level-control":
        plc = engine.Plc(programs.level_control)
        rows = plc.run(LEVEL_CONTROL)
    else:
        plc = engine.Plc(programs.sequence)
        rows = plc.run(SEQUENCE)

    print(engine.format_run(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
