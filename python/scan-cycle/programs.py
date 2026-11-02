"""Two control programs, written in Python, with PLC semantics.

`level_control` is the pump seal-in that `plc/level_control_ld.xml` draws.
`sequence` is the four-step sequence that `plc/sequence_st.xml` writes in
structured text.

Read them beside the PLC versions. The Python is not the deliverable; the
comparison is. Every line here has a counterpart in one of the PLC files.
"""

HIGH_LEVEL_PERCENT = 70
RUN_TOO_LONG_SCANS = 5


def level_control(plc):
    """Pump holds itself in until the level is high or the interlock opens."""
    start = plc.inputs.get("start_cmd", False)
    stop = plc.inputs.get("stop_cmd", False)
    interlock = plc.inputs.get("interlock", False)
    level = plc.inputs.get("level", 0)

    level_high = level >= HIGH_LEVEL_PERCENT
    held = plc.memory.get("run_latch", False)

    # (start OR run_latch) AND NOT level_high AND interlock, and a stop that
    # is not drawn in the ladder because it interrupts the rung.
    pump = (start or held) and not level_high and interlock and not stop

    plc.memory["level_high"] = level_high
    plc.memory["run_latch"] = pump
    plc.outputs["pump_run"] = pump


def sequence(plc):
    """Four steps, a timer, and a latched alarm, as in sequence_st.xml.

    Step 0 idle, 1 running, 2 fault latched, 3 fault cleared.
    """
    fault = plc.inputs.get("fault", False) or plc.memory.get("fault_seen", False)
    start = plc.inputs.get("start_cmd", False)
    stop = plc.inputs.get("stop_cmd", False)

    step = plc.memory.get("step", 0)
    pump = False
    alarm = False

    # Every step clears the outputs it does not own. Without this, an output
    # keeps the value it had in the previous step.
    if step == 0:
        if fault:
            step = 2
        elif start and not stop:
            step = 1
    elif step == 1:
        # De-energize first and energize only in the else branch. Checking the
        # fault after the output is set leaves the pump on for one scan with a
        # fault present.
        if fault:
            step = 2
        elif stop:
            step = 0
        else:
            pump = True
    elif step == 2:
        # The alarm latches here and stays on in step 3 until the operator
        # acknowledges it by releasing the start button.
        alarm = True
        if not fault:
            step = 3
    elif step == 3:
        alarm = True
        if not start:
            step = 0
    else:
        # An unknown step is a fault in itself.
        step = 2

    plc.memory["step"] = step

    # The timer belongs to step 1, so it resets whenever the sequence leaves.
    timer = plc.timer("step_timer", RUN_TOO_LONG_SCANS)
    timer.update(step == 1)
    plc.memory["step_timer_elapsed"] = timer.elapsed

    if timer.done:
        plc.memory["fault_seen"] = True

    plc.outputs["pump_run"] = pump
    plc.outputs["alarm"] = alarm
