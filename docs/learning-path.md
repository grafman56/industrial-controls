# Learning path

Written for a working electrician who already writes Python and designs
networks. The order matters, because each stage uses the vocabulary of the
one before it.

Do not skip stage 0. Instrument technicians and controls engineers lose more
hours to a wrong tag list than to any protocol bug.

## Stage 0: the loop sheet habit

Goal: read a drawing set and produce a tag list you can defend.

Read: any P&ID and instrument index you can get. Ask for a real one from a
site, or build the tank's.

Practice:

- Write `tags.csv` for the tank: tag name, service, type, range, engineering
  unit, alarm limits, PLC address.
- Then mark the two tags in the current lab you cannot fill in, because the
  lab has no transmitter.

Observe: the tank exposes a level as a raw integer and a pump as a coil. There
is no 4-20 mA loop, no impulse line and no damping. You have just written the
first page of the gap analysis between a simulation and a plant.

Enterprise link: an instrument index is the contract between the electrical
scope, the controls scope and the process scope. Every plant has one. Sites
with a bad one have unreliable alarms.

## Stage 1: first program

Goal: write IEC 61131-3 logic and watch it run against a live process.

Run on the lab host:

```bash
./labctl up modbus-tcp
```

Then tunnel the editor port to your PC and follow
`../modbus-tcp/GETTING_STARTED.md`:

```bash
ssh -L 8443:127.0.0.1:8443 -L 8502:127.0.0.1:8502 <user>@<lab-host>
```

Write the program in Ladder Diagram first, then rewrite the same logic in
Structured Text. The rewrite is the lesson: the same seal-in circuit looks
different and behaves the same.

Observe: the scan cycle. Add a timer and watch the level fall between scans,
then explain the result without saying "it is slow".

## Stage 2: the register map

Goal: own the mapping between the wire and the engineering value.

Practice with the sample client already in the lab:

```bash
ssh <user>@<lab-host> \
  'docker exec clab-modbus-tcp-client python /lab/client.py 192.0.2.1'
```

Then write your own client with `pymodbus` against `172.100.120.10:5020`:

- read the level holding register and the pump coil
- write the coil
- scale the raw value to percent with a span and an offset you can defend
- print a table with timestamp, raw, scaled and unit

Observe: the request and response bytes in a capture. Match each field to the
Modbus application protocol. This is the part most people skip, and it is the
part that makes a capture useful during an outage.

## Stage 3: control logic that holds

Goal: make the plant behave, then make it fail safely.

Exercises, in order:

1. Hysteresis level control: pump on below 30 %, off above 70 %. Assert the
   deadband is real with a trend, not with a screenshot.
2. Interlock: the pump must not run when the level is at 0 %. Prove the
   interlock by forcing the condition.
3. First-out alarm: record which condition tripped first, not only the last.
4. PID in Structured Text on the level, with the pump replaced by a
   proportional valve model. Tune it. Show the trend of the response.

Observe: the program is only half the loop. The other half is the process
model, and a model without inertia teaches you to over-tune.

## Stage 4: HMI and SCADA

Blocked on the `scada-hmi` lab in [roadmap.md](roadmap.md).

Goal: build an operator screen that does not lie. A tag shown without a
timestamp is a rumour.

Deliverables: one overview screen, one trend, one alarm list with priority
and a first-out field, and one screen for the engineer rather than the
operator.

## Stage 5: protocol breadth

Blocked on the OPC UA, EtherNet/IP and S7comm labs.

Goal: move one value through four protocols and say what each costs.

The useful comparison is not "which is better". It is which protocol a given
device speaks, and what an integrator does when two devices do not share one.

## Stage 6: the OT network

Blocked on the `purdue-zones` lab.

Goal: put a PLC and an HMI in different zones and make the conduit explicit.

Deliverables: a zone and conduit drawing for your own lab, a firewall rule
set that permits exactly the conduits in the drawing, and a capture that
proves a denied flow stays denied.

This is where an electrician who already does networking moves ahead of a
controls technician who does not. Segmentation arguments are won with a
diagram and a capture.

## Stage 7: visibility and a drill

Blocked on the `ot-visibility` and `drills` labs.

Goal: detect and then explain a change to a PLC from the network side.

Follow the pattern already used in the network labs: break it, write the NOC
ticket with full command output, then write the runbook that repairs it.
Evidence before repair.

## Stage 8: hardware

Goal: close the fidelity gap that containers cannot close.

One used PLC and a bench supply is enough: discrete inputs, a relay output, a
4-20 mA loop with a loop calibrator, and a VFD if the budget allows. Wire it,
break it, meter it.

## What this path does not give you

- Vendor tooling. Rockwell Studio 5000 and Siemens TIA Portal run on Windows
  and need a licence or a trial. Many job adverts name them. A free lab does
  not replace that exposure, and no amount of OpenPLC hides it.
- Certification. For OT security roles, GICSP or the ISA/IEC 62443
  certificate opens doors that a home lab does not.
- Plant experience. A real site has drawings that are wrong, cabinets that
  are undocumented, and operators who know more than the HMI.

## Where the combination is strongest

The rare combination is electrical work plus network design plus code. It
maps to OT network engineer, SCADA integration, controls engineer in a
multi-site company, and industrial cyber defence. It maps poorly to a pure
Rockwell programming role, because that role hires on vendor tooling and
plant floor time.

Build the lab to show the first three. Buy one PLC to show the fourth.
