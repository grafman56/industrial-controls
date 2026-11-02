# Roadmap

A planned lab is not a claim. Only the labs in `labs.toml` exist.

Order is chosen so that each lab answers a question the previous one raised.

## 1. `modbus-tcp` (exists)

Proves: a soft PLC and a process model exchange real Modbus/TCP frames, and an
IEC 61131-3 program can be built, uploaded and debugged from a desktop editor.

Known gaps: one process variable, a counter instead of a process model, no
HMI, no historian.

## 2. `modbus-rtu`

Proves: a serial Modbus link behaves differently from TCP, and an RTU
addressing scheme has its own failure modes.

Needs: a pty pair inside one container, or `ser2net` between two containers.
An RS-485 multi-drop layout with three slaves teaches unit addressing.

Question it answers: why does a technician say "the bus is quiet" and what do
you check first.

## 3. `opc-ua`

Proves: a value can be modelled with a type and a quality, not only an address.

Needs: `open62541` server container, a simulated device, an `asyncua` client,
and FUXA as the OPC UA client.

Question: what does an integrator gain from information modelling, and what
does it cost in setup time.

## 4. `ethernet-ip`

Proves: a CIP explicit message and an implicit I/O connection are different
things.

Needs: an adapter implementation in a container (`cpppo` or `OpENer`), a
`pycomm3` client, and a FUXA driver.

Question: why an I/O connection drops when a switch floods, and what
`pycomm3` shows at that moment.

## 5. `s7comm`

Proves: a Siemens device model, and the difference between a rack/slot
addressed read and a symbolic one.

Needs: a `snap7` server in a container, FUXA's S7 driver, and optionally the
S7comm plugin built from the OpenPLC runtime source.

Question: what a controls technician means by "the PLC is reachable but the
DB read fails".

## 6. `scada-hmi`

Proves: an operator interface, an alarm list and a trend over a real
historian.

Needs: FUXA, Telegraf or a Modbus poller, InfluxDB, Grafana. The house stack
already runs InfluxDB and Grafana on VM 201, so this lab can feed the existing
monitoring instead of duplicating it.

Question: which tag a trend must carry so that a dispute about an outage can
be settled with data.

## 7. `purdue-zones`

Proves: zones and conduits with evidence. A denied flow stays denied, and the
capture shows it.

Needs: an FRR or nftables router between control zone and supervisory zone, a
DMZ hop for the historian, and a documented conduit list. This lab may contain
routing, because the router is the OT boundary. It must not become a routing
lab.

Question: what breaks when you close a port that somebody needed, and how do
you find that out before production.

## 8. `ot-visibility`

Proves: passive detection on OT traffic with evidence an analyst can use.

Needs: Zeek with the Modbus and DNP3 analyzers, Suricata, and pcap in the
topology. Output to the existing Grafana when possible.

Question: how do you detect a write to a PLC coil that no operator made.

## 9. `drills`

Proves: the incident process, not only the tools.

Needs: the `break-tests` layout from the network labs. Each drill has a NOC
ticket with full command output and rationale, then a runbook.

Question: can another engineer follow the runbook and reach the same result.

## 10. `historian` (maybe)

Proves: a process historian keeps quality and timestamps, and that a bad tag
does not silently become a trend line.

Do not build this until the SCADA lab produces data worth keeping.

## Cross-cutting work

- One shared `ics-tools` image with `pymodbus`, `pycomm3`, `asyncua`,
  `python-snap7`, `tshark` and `zeek`. Pinned, built once, reused by every
  lab. It removes the per-lab Dockerfile drift.
- A Semaphore path for ICS labs, following the fixed template pattern in
  `network/automation`. Each template stays scoped to one topology and one
  action, with overrides disabled.
- A capacity note before the second ICS lab is deployed. The current lab host
  is 3 GB and 2 vCPU, which fits one small lab at a time.
