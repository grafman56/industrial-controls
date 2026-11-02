# Scan cycle

A PLC runs the same program forever. Each pass reads the inputs, runs the
program once, and publishes the outputs. This directory implements that loop in
Python, and two control programs that match the PLC files in `plc/`.

| File | What it is |
|---|---|
| `engine.py` | The scan loop, the input and output images, and a TON timer |
| `programs.py` | `level_control` (the seal-in) and `sequence` (the four-step sequence) |
| `run.py` | Runs a scenario and prints a timing diagram |

## Run a scenario

```bash
python3 python/scan-cycle/run.py level-control
python3 python/scan-cycle/run.py sequence
```

Level control, one row per scan:

```
scan interlock level start_cmd stop_cmd level_high run_latch pump_run
   1         1    10         0        0          0         0        0
   2         1    20         1        0          0         1        1
   3         1    40         0        0          0         1        1
   5         1    72         0        0          1         0        0
```

Scan 2 is the start command. Scan 3 shows the seal-in holding with the button
released. Scan 5 shows the high level switch breaking it, and `run_latch` goes
to zero with it, so the pump does not restart when the level falls.

Read down a column. That is what a timing diagram is, and it is the first thing
to draw when a real machine misbehaves.

## The rules this engine keeps

1. The program runs top to bottom, once per scan.
2. A contact sees the output image as it stands at that point in the scan, not
   as it was at the start.
3. The outside world sees the outputs only when the scan ends.
4. A timer counts scans, not seconds.

Rule 4 is the one to argue about. Counting scans makes the test deterministic,
which is what a test needs. On real hardware the scan time varies, so a timer
built on scan counts drifts, and a drift of a few hundred milliseconds is a
real fault on a machine with a moving part. `plc/sequence_st.xml` shows the
proper form: a TON with a real time preset.

## The one-scan lag

The sequence program has a visible one-scan lag, and that lag is not a bug in
the engine. When a step decides to leave, its outputs were true for that whole
scan, because the step was active. The next scan runs the new step.

So a fault on the scan that moves the sequence to the fault step does not
de-energize an output that the previous step's branch already set. The fix is
in the program, not the engine: check the fault first and energize in the
`else` branch. `programs.py` does that, and one test proves it.

## Prove it

```bash
python3 -m unittest tests.test_scan_cycle
```

Nineteen tests. The ones worth reading:

- `test_pump_holds_itself_in_after_the_button_is_released`
- `test_high_level_stops_the_pump_and_clears_the_latch`
- `test_a_fault_de_energizes_the_pump_in_the_same_scan`
- `test_the_alarm_latches_until_the_operator_acknowledges`
- `test_the_timer_resets_when_the_sequence_leaves_step_one`

## What this is not

This is not a soft PLC and it will not talk to a PLC card. It is a way to test
logic and to explain scan order. For a real runtime use the OpenPLC container
in `scada-hmi`, which compiles an IEC 61131-3 program and runs the actual
scheduler.
