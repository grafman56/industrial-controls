# Python projects

Two projects that turn control knowledge into code you can test. Both use the
standard library only, so neither needs a virtual environment, a container, or
a network to run its tests.

| Project | What it is | What it teaches |
|---|---|---|
| `scan-cycle/` | A PLC scan engine and two control programs | Control logic becomes unit-testable, and the scan-order rules become visible |
| `power-meter/` | A three-phase meter that answers Modbus/TCP | Register maps, word order, scaling, and frame handling |

## Why these two

The scan engine answers a question that comes up in every interview: can you
prove a control program is correct before you energize anything? In Python the
answer is a test file, and the program in `plc/` has a twin here.

The meter answers the question an electrician asks first: what is actually on
the wire? A meter sends 26 raw 16-bit registers. Everything you care about
happens between those registers and the number on the screen.

## Run the tests

From the repository root:

```bash
python3 -m unittest tests.test_scan_cycle tests.test_power_meter
```

## Run the demos

```bash
python3 python/scan-cycle/run.py level-control
python3 python/scan-cycle/run.py sequence

python3 python/power-meter/meter.py --print
python3 python/power-meter/meter.py --port 15020 --scenario phase-loss
python3 python/power-meter/read_meter.py --port 15020
```

The meter binds to loopback by default. Pass `--host 0.0.0.0` only inside a
lab network you control.
