"""A PLC scan cycle in Python.

This engine follows the same rules as the programs in `plc/`:

1. Copy the inputs into the input image.
2. Run the program once, top to bottom.
3. Publish the output image. Nothing outside sees the outputs until the scan
   ends.

The value is not that Python is a PLC. The value is that control logic becomes
unit-testable. A seal-in circuit that takes ten seconds to prove by hand on a
soft PLC takes a millisecond here, and the test stays in the repository.

A timer counts scans, not wall clock time. That is deliberate: it makes the
result deterministic. On real hardware the scan time varies, so a timer built
on scan counts drifts. That drift is a real fault, and `sequence_st.xml` shows
where it matters.
"""


class Timer:
    """A TON timer: on-delay, reset every time the enable goes false."""

    def __init__(self, preset):
        if preset < 1:
            raise ValueError("a timer preset is at least one scan")
        self.preset = preset
        self.elapsed = 0
        self.done = False

    def update(self, enable):
        if not enable:
            self.elapsed = 0
            self.done = False
            return False
        if self.elapsed < self.preset:
            self.elapsed += 1
        self.done = self.elapsed >= self.preset
        return self.done

    def __repr__(self):
        return "Timer(elapsed=%d, preset=%d, done=%s)" % (self.elapsed, self.preset, self.done)


class Plc:
    """One program, one input image, one output image, one memory area."""

    def __init__(self, program):
        self.program = program
        self.inputs = {}
        self.outputs = {}
        self.memory = {}
        self.timers = {}
        self.scans = 0

    def timer(self, name, preset):
        """A named timer, created on first use so it survives the scans."""
        if name not in self.timers:
            self.timers[name] = Timer(preset)
        return self.timers[name]

    def scan(self, inputs=None):
        """Run the program once and return the output image."""
        if inputs is not None:
            self.inputs = dict(inputs)
        self.program(self)
        self.scans += 1
        return dict(self.outputs)

    def run(self, steps):
        """Run one scan per input set and return a row per scan."""
        rows = []
        for inputs in steps:
            outputs = self.scan(inputs)
            rows.append(
                {
                    "scan": self.scans,
                    "inputs": dict(self.inputs),
                    "outputs": outputs,
                    "memory": dict(self.memory),
                }
            )
        return rows


def format_run(rows):
    """A fixed-width table, so a scenario reads as a timing diagram."""
    if not rows:
        return ""
    input_names = sorted({name for row in rows for name in row["inputs"]})
    output_names = sorted({name for row in rows for name in row["outputs"]})
    memory_names = sorted(
        {name for row in rows for name in row["memory"] if isinstance(row["memory"][name], bool)}
    )
    columns = ["scan"] + input_names + memory_names + output_names

    widths = {name: max(len(name), 5) for name in columns}
    lines = [" ".join(name.rjust(widths[name]) for name in columns)]
    for row in rows:
        cells = []
        for name in columns:
            if name == "scan":
                value = str(row["scan"])
            elif name in row["inputs"]:
                value = one(row["inputs"][name])
            elif name in row["outputs"]:
                value = one(row["outputs"][name])
            else:
                value = one(row["memory"][name])
            cells.append(value.rjust(widths[name]))
        lines.append(" ".join(cells))
    return "\n".join(lines)


def one(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return "%.2f" % value
    return str(value)
