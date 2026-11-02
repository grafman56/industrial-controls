# Protocols

Each row states what the protocol is, who runs it, and which tool reads it in
this lab. A row marked planned has no lab yet. See
[roadmap.md](roadmap.md).

The focus is data centre and building controls, so Modbus, BACnet and SNMP
come before the manufacturing and utility protocols.

| Protocol | Transport | Who uses it | Tool that reads it here | State |
|---|---|---|---|---|
| Modbus/TCP | TCP 502 (5020 in this lab) | Water, manufacturing, power meters, almost everything cheap | `pymodbus` client, FUXA driver, Wireshark, Zeek, the poller in `scada-hmi` | Labs exist |
| BACnet/IP | UDP 47808 | Building automation: AHUs, VAV boxes, chillers, BMS head ends | `bacnet-ip/` lab: a device and a client written here, no third-party package | Working |
| SNMP | UDP 161 | UPS, PDU, branch circuit monitors, any device in an EPMS | `snmpsim` for the agent, Telegraf `inputs.snmp`, `snmpwalk` | Planned |
| Modbus RTU | Serial RS-485 | VFDs, power meters, legacy field devices | `pymodbus` RTU, a pty pair or serial bridge | Planned |
| EtherNet/IP (CIP) | TCP 44818, UDP 2222 | US manufacturing, Rockwell/Allen-Bradley | `pycomm3`, FUXA driver, a CIP analyzer add-on for Zeek | Planned |
| S7comm | TCP 102 | Siemens S7-300/400/1200 | `python-snap7`, FUXA S7 driver | Planned |
| OPC UA | TCP 4840 | Everywhere. The IT-to-OT integration protocol | `asyncua` client, `open62541` server, FUXA client | Planned |
| MQTT, Sparkplug B | TCP 1883 | IIoT gateways, newer plant telemetry | `mosquitto`, any MQTT client | Planned |
| DNP3 | TCP 20000 | Electric and water utilities, RTUs | `opendnp3`, Zeek native analyzer | Planned |
| PROFINET | Ethernet layer 2 | European manufacturing, Siemens | none in a container, see below | Not planned |
| IEC 61850, GOOSE | Ethernet layer 2 multicast | Substation automation | none in a container, see below | Not planned |

## Capture and visibility tools

| Tool | What it gives you | Note |
|---|---|---|
| Wireshark / tshark | Frame level detail, request and response decode | Most Modbus and S7 sub-functions are decoded. CIP needs the right dissector preference. |
| Zeek | Connection logs, Modbus and DNP3 function-level events | Modbus and DNP3 are native analyzers. CIP and S7comm need an add-on analyzer. |
| Suricata | Signature alerts on OT traffic | Useful for the drill track. Rule quality varies by protocol. |
| FUXA | Browser HMI with Modbus, S7, OPC UA, EtherNet/IP, MQTT and BACnet drivers | Free, container image `frangoteam/fuxa`. Good for HMI exercises without a licence. |

## Protocols that stay out of this lab

PROFINET and IEC 61850 GOOSE need a real-time Ethernet behaviour that a
container bridged on a hypervisor does not reproduce. A lab that shows them
working slowly is worse than no lab, because it teaches the wrong mental
model. If those protocols matter for the job you want, learn them on hardware
or in a vendor course.

## Why the register map matters more than the protocol

An electrician reads a loop sheet: sensor, range, engineering units, alarm
limits. A PLC program reads a holding register: an integer, a scale factor and
a comment that may be wrong.

The work that transfers between the two is the scaling discipline. A 4-20 mA
transmitter over a 0-100 % range becomes a raw value, a span and an offset.
Write that mapping down before you write logic. Half of the faults in a real
plant are a mapping that nobody checked.
