# Architecture

The lab models one small plant. It is deliberately smaller than a real site,
and it keeps the same boundaries.

## The plant model

```
Level 4  enterprise      historian query, reporting            (not built)
Level 3  site operations engineering workstation, historian    (planned)
Level 3.5 DMZ            jump host, patch staging              (planned)
Level 2  supervisory     HMI/SCADA server                      (planned)
Level 1  control         PLC, remote I/O                       (modbus-tcp: plc)
Level 0  process         tank, pump, level, limit switches     (modbus-tcp: tank)
```

A modern plant flattens this into zones and conduits rather than clean levels.
The lab uses the level names because engineers still say "level 2" in a
meeting, and it applies the zone rule underneath: a protocol crosses a zone
boundary only through a declared conduit, and every conduit has a written
reason.

## What runs today: `modbus-tcp`

| Node | Address | Role |
|---|---|---|
| `server` | 192.0.2.1 | PyModbus simulator with a web UI, sample registers |
| `client` | 192.0.2.2 | Sample client, capture point |
| `tank` | 172.100.120.10 | Process model, Modbus/TCP server on 5020 |
| `plc` | 172.100.120.11 | OpenPLC Runtime v4.3.1, IEC 61131-3 execution |

Facts that matter when you read a capture:

- Modbus/TCP is used on port 5020 inside this lab, not 502. A capture filter
  of `tcp.port == 502` shows nothing.
- The `server` and `client` pair sits on a point-to-point link with
  documentation addresses. Only `tank` and `plc` are on the management
  network.
- Two published ports exist, both on host loopback: the simulator UI on
  8502 and the PLC editor API on 8443. No Modbus port is published.
- The `plc` container needs `SYS_NICE` and `SYS_RESOURCE`. A PLC runtime
  asks for real-time scheduling. Without those capabilities it still runs,
  and it jitters more.

## Host sizing

The lab host is a VM, not a workstation. Current shape of VM 200 `clab`:
3 GB RAM, 2 vCPU. That is enough for one small lab at a time.

An ICS lab grows faster than a routing lab, because a full stack adds an HMI
server, a historian and an engineering workstation:

| Stack | Containers | Working memory |
|---|---|---|
| Protocol exercise (one PLC, one peer) | 2 to 4 | 2 GB |
| Plant model with HMI and historian | 6 to 9 | 4 to 6 GB |

The lab host module in `server-admin-labhost` defaults to 4 cores, 8 GB RAM
and 40 GB disk, with a hard minimum of 40 GB disk. Two ICS labs at once want
that shape, not the 3 GB host. Do not raise the memory of a running lab host
in the middle of a drill.

## Addressing

- Lab management networks: `172.111.<n>.0/24`, one number per lab.
- Grandfathered: `modbus-tcp` keeps `172.100.120.0/24` so a running
  deployment is not orphaned.
- In-lab process addressing: `192.0.2.0/24` is reserved for links inside a
  lab, where the address is not meant to be reached from outside.
- Nothing in a lab is addressed from the house LAN. A container is reached
  through the lab host, never directly.

## Fidelity limits, stated plainly

- A container PLC has no fixed scan time and no watchdog relay.
- The process model is differential equations or, in the current tank, a
  counter. It has no mass, no friction and no pressure.
- No 24 V loop exists. A wiring fault, a sinking input card and a floating
  analog channel have no representation.
- A virtual PLC cannot show you why a real cabinet trips a breaker.

Use the lab to learn the protocol, the program and the network. Use a real
PLC, a bench supply and a meter to learn the electrical behaviour. Both are
needed, and they teach different things.
