# PLC programs and languages

Five programs in four of the five IEC 61131-3 languages. The point is to
compare them, not to pick a favourite.

| File | Language | What it shows |
|---|---|---|
| `level_control_ld.xml` | Ladder diagram | Seal-in circuit, normally closed stop contact, interlock |
| `level_control_st.xml` | Structured text | Analog scaling, comparisons, the same seal-in as text |
| `level_control_fbd.xml` | Function block diagram | The same seal-in as a connection graph, with a negated input |
| `level_control_il.xml` | Instruction list | The accumulator model, which explains what a compiler does with the others |
| `sequence_st.xml` | Structured text | A four-step sequence with a timer and a latched alarm |

The first four are one program in four dialects. `sequence_st.xml` is a second
program, because a sequence is where the languages really differ.

## The control logic

```
start_cmd    operator start, normally open
level_high   high level switch, closed at high level
interlock    pump protection, closed means the pump may run
run_latch    internal, the seal-in state
pump_run     output to the pump contactor
```

Pump output is `(start OR run_latch) AND NOT level_high AND interlock`.

Ladder, function block, and instruction list take the discrete signals as they
are, because that is what a float switch gives a PLC card. `level_control_st.xml`
derives them from an analog `level`, because that is what a level transmitter
gives you. Both are real patterns, and the difference is the lesson.

## Open them

OpenPLC Editor 4 reads PLCopen TC6 XML. For each file:

1. Open the editor.
2. Choose the PLCopen import, then the `.xml` file.
3. Confirm the import and check that the POU appears with its variables.
4. Assign the variables to addresses in the editor. The files declare no
   addresses on purpose, so they import into any project.

The ladder file is the one to import first. If a rung arrives with a missing
connection, the editor's own save will show the layout it expects, and the XML
is easy to adjust.

The function block diagram names its blocks `OR` and `AND`, which are the
standard IEC function names. A block type name resolves against the function
block library the project loads. If the import does not resolve those two
names, export one working FBD rung from the editor and copy the name it writes.

## Check them before you import

The files are plain XML, so the common mistakes are visible without a PLC.

```bash
python3 tools/plcopen.py lint plc/*.xml
```

The checker reports an error for:

- a connection that points at a node which does not exist
- a contact, coil, or FBD expression that names an undeclared variable
- a duplicate node id
- a ladder with no power rail
- an FBD block with no type name or no output
- an FBD output variable that nothing feeds
- an empty text body
- a namespace that is not PLCopen

It reports a warning for a declared variable that nothing uses, and for an FBD
block input that is left unconnected.

It does not compile the program. A compiler catches the rest, and the first
import into the editor is the real test.

## Sequential function chart

There is no SFC file here, on purpose.

The editor's importer parses ST, IL, LD, and FBD bodies in full. For SFC it
returns a warning and skips the POU, because the importer targets the
old-editor dialect only. A hand-written SFC file would therefore be a file the
tool declines to open.

`sequence_st.xml` is the working substitute. It is the same structure an SFC
draws, written as a `CASE` over a step variable: one step per state, one
transition block per step, and each step clears the outputs it does not own.
That last rule is the one that matters. A sequence without it is a set of
coils that remember the previous step.

When you build an SFC in a vendor tool, compare it with `sequence_st.xml`. The
chart shows the process; the text shows what the PLC executes.

## Which language to use

| Situation | Language | Reason |
|---|---|---|
| Discrete logic an electrician will maintain | Ladder | It is a schematic. A technician can read it without training. |
| Scaling, calculations, string handling, state machines | Structured text | Faster to write and to review, and it fits version control. |
| Reusable control modules, process blocks | Function block diagram | The block is the unit of reuse, and it draws the data flow. |
| A sequence with steps and transitions | Sequential function chart | It documents the process, not only the logic. |
| Existing vendor code, old projects | Instruction list | You will read it, not write it. Deprecated since the 2013 edition. |

Most real programs mix two of them. A plant that says "ladder only" still has
a scaling routine in structured text somewhere.
