# PLC programs and languages

Three versions of one control program, written in three of the five IEC
61131-3 languages. The point is to compare them, not to pick a favourite.

| File | Language | What it shows |
|---|---|---|
| `level_control_ld.xml` | Ladder diagram | Seal-in circuit, normally closed stop contact, interlock |
| `level_control_st.xml` | Structured text | Analog scaling, comparisons, the same seal-in as text |
| `level_control_il.xml` | Instruction list | The accumulator model, which explains what a compiler does with the others |

The logic is the same in all three: a pump starts on a pushbutton, holds itself
in, stops at high level, and stops when the interlock opens.

## The control logic

```
start_cmd    operator start, normally open
level_high   high level switch, closed at high level
interlock    pump protection, closed means the pump may run
run_latch    internal, the seal-in state
pump_run     output to the pump contactor
```

Ladder and instruction list take the discrete signals as they are, because
that is what a float switch gives a PLC card. The structured text version
derives them from an analog `level`, because that is what a level transmitter
gives you. Both are real patterns, and the difference is the point.

## Open them

OpenPLC Editor 4 reads PLCopen TC6 XML through its import path. For each file:

1. Open the editor.
2. Choose the PLCopen import, then the `.xml` file.
3. Confirm the import and check that the POU appears with its variables.
4. Assign the variables to addresses in the editor. The files declare no
   addresses on purpose, so they import into any project.

The ladder file is the one to import first. If a rung arrives with a missing
connection, the editor's own save will show the layout it expects, and the XML
is easy to adjust.

## Check them before you import

The files are plain XML, so the common mistakes are visible without a PLC.

```bash
python3 tools/plcopen.py lint plc/*.xml
```

The checker reports an error for a connection that points at a node which does
not exist, a contact or coil that names an undeclared variable, a duplicate
node id, a ladder with no power rail, an empty text body, and a wrong
namespace. It reports a warning for a declared variable that nothing uses.

It does not compile the program. A compiler catches the rest, and the first
import into the editor is the real test.

## What is not here, and why

Function block diagram and sequential function chart have no demo file yet.

- FBD is a block library and a connection graph. The block names depend on the
  library the project loads, so a hand-written file is a guess until one
  exported project shows the exact shape.
- SFC is not in the editor's XML writer. The generator directory holds
  `ladder-xml.ts`, `fbd-xml.ts`, `il-xml.ts` and `st-xml.ts` only, so a
  sequential chart is not part of the interchange path this repository targets.

Both are worth learning. The honest route is to build one of each in the
editor once, export it, and compare the result with the files here. That
exported pair becomes the reference for the next two demos.

## Which language to use

| Situation | Language | Reason |
|---|---|---|
| Discrete logic an electrician will maintain | Ladder | It is a schematic. A technician can read it without training. |
| Scaling, calculations, string handling, state machines | Structured text | Faster to write and to review, and it fits version control. |
| Existing vendor code, old projects | Instruction list | You will read it, not write it. Deprecated since the 2013 edition. |
| Reusable control modules, process blocks | Function block diagram | The block is the unit of reuse, and it draws the data flow. |
| A sequence with steps and transitions | Sequential function chart | It documents the process, not only the logic. |

Most real programs mix two of them. A plant that says "ladder only" still has
a scaling routine in structured text somewhere.
