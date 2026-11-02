# Roadmap

A planned lab is not a claim. Only the labs in `labs.toml` exist.

The order follows the chosen focus: data centre and building controls, where
electrical distribution, power metering and monitoring meet the network. That
market is large in Northern Virginia, and it pays for the combination of
electrical work, protocols and network design.

Each lab answers a question the previous one raised.

## 1. `modbus-tcp` (exists)

Proves: a soft PLC and a process model exchange real Modbus/TCP frames, and an
IEC 61131-3 program can be built, uploaded and debugged from a desktop editor.

## 2. `scada-hmi` (exists)

Proves: an operator interface and a historian over one process, with the
historian able to settle a question about what happened.

Known gaps: one process variable, a counter instead of a process model, no
alarms to a real notification path.

## 3. `bacnet`

Proves: a building automation protocol with objects, properties and services,
not registers. A BACnet point has a name, a unit and a status, and that changes
how an HMI is built.

Needs: a BACnet/IP device simulator in a container (`bacnet-stack` demo server
or a Python `BACpypes` device, both to be verified at build time), a client,
and FUXA or Grafana for the view.

Question it answers: why a BMS integrator asks for a point list instead of a
register map.

## 4. `epms`

Proves: an electrical distribution model. Branch meters over Modbus, a UPS and
a PDU over SNMP, and one mimic that shows load against capacity per branch.

Needs: a power meter simulator (Modbus holding registers for kW, kWh, volts,
amps), an SNMP agent (`snmpsim` or `net-snmp` with a fixed MIB walk), and a
dashboard that treats an overload as an alarm rather than a number.

Question: how do you know a branch is close to its rating before it trips.

This is the lab where an electrician's judgement has the most value and where
a pure network engineer is weakest.

## 5. `purdue-zones`

Proves: zones and conduits with evidence. A denied flow stays denied, and the
capture shows it.

Needs: a router between the control zone and the supervisory zone, a DMZ hop
for the historian, and a documented conduit list. This lab may contain routing,
because the router is the OT boundary. It must not become a routing lab.

Question: what breaks when you close a port that somebody needed, and how do
you find that out before production.

## 6. `ot-visibility`

Proves: passive detection on industrial traffic with evidence an analyst can
use.

Needs: Zeek with the Modbus and DNP3 analyzers, Suricata, and captures in the
topology. Output to the existing Grafana when possible.

Question: how do you detect a write to a coil that no operator made.

## 7. `drills`

Proves: the incident process, not only the tools.

Needs: the `break-tests` layout from the network labs. Each drill has a ticket
with full command output and rationale, then a runbook.

Question: can another engineer follow the runbook and reach the same result.

## 8. `opc-ua`

Proves: a value can be modelled with a type and a quality, not only an address.

Needs: an `open62541` server, an `asyncua` client, and FUXA as the OPC UA
client.

Question: what does an integrator gain from information modelling, and what
does it cost in setup time.

## 9. `modbus-rtu`

Proves: a serial link behaves differently from TCP, and an RTU addressing
scheme has its own failure modes.

Needs: a pty pair inside one container, or `ser2net` between two containers,
plus a three-slave multi-drop layout.

Question: what a technician means by "the bus is quiet", and what you check
first.

## 10. `ethernet-ip`

Proves: a CIP explicit message and an implicit I/O connection are different
things.

Needs: an adapter implementation in a container (`cpppo` or `OpENer`), a
`pycomm3` client, and a FUXA driver.

## 11. `s7comm`

Proves: a Siemens device model, and the difference between a rack/slot
addressed read and a symbolic one.

Needs: a `snap7` server in a container, FUXA's S7 driver, and optionally the
S7comm plugin built from the OpenPLC runtime source.

## Cross-cutting work

- One shared `ics-tools` image with `pymodbus`, `pycomm3`, `asyncua`,
  `python-snap7`, `tshark` and `zeek`. Pinned, built once, reused by every
  lab. It removes the per-lab Dockerfile drift.
- A Semaphore path for ICS labs, following the fixed template pattern in
  `network/automation`. Each template stays scoped to one topology and one
  action, with overrides disabled.
- A second lab host. The current host is 3 GB and 2 vCPU, and `scada-hmi`
  already asks for 4096 MB free. The chosen shape is 8 GB and 4 vCPU, which
  the `server-admin-labhost` Terraform module takes as its default.
