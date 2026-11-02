# BACnet/IP lab

Two BACnet/IP devices on one network, and a client that finds them and reads
every point. Three containers, standard library Python, no vendor licence.

This is the protocol of building management. If the work is a data centre, the
BMS speaks BACnet to the air handlers and the chillers, and the EPMS speaks
Modbus to the meters. This lab is the BACnet half.

## Nodes

| Node | Address | What it is |
|---|---|---|
| `ahu` | 172.111.30.10 | Air handling unit, device 1001, on UDP 47808 |
| `vav` | 172.111.30.11 | VAV terminal box, device 1002, on UDP 47808 |
| `supervisor` | 172.111.30.20 | Workstation: discovery, point reads, captures |

The AHU publishes `127.0.0.1:47808/udp` on the host, so a BACnet tool on a
laptop can unicast to device 1001. Discovery from outside needs a BBMD, which
this lab does not have. See `ARCHITECTURE.md`.

## The point schedule

A BACnet device is a table of objects. This is the AHU:

| Object | Name | Value | Units |
|---|---|---|---|
| analog-input,1 | supply-air-temp | 13.4 | degC |
| analog-input,2 | return-air-temp | 22.8 | degC |
| analog-input,3 | mixed-air-temp | 18.1 | degC |
| analog-input,4 | duct-static-pressure | 312 | Pa |
| analog-input,5 | filter-differential-pressure | 48 | Pa |
| analog-output,1 | chilled-water-valve | 42 | % |
| analog-output,2 | fan-speed | 68 | % |
| analog-value,1 | supply-air-setpoint | 13.0 | degC |
| analog-value,2 | static-pressure-setpoint | 300 | Pa |
| binary-input,1 | fan-status | active | |
| binary-input,2 | filter-alarm | inactive | |
| binary-output,1 | supply-fan-command | active | |

The VAV box has seven points: zone temperature, airflow, damper position,
reheat valve, zone setpoint, occupancy, and a reheat enable.

## What the client does

1. Sends Who-Is as a broadcast, and collects the I-Am replies. That is
   discovery, and there is no device list in a configuration file.
2. Reads the device object's `object-list`, which is how a client learns which
   objects exist. The lab reads the list instead of assuming it.
3. Sends ReadPropertyMultiple for each point: name, present value, units.

Nineteen points across two devices come back in the verification run.

## Lifecycle

```bash
./labctl doctor
./labctl up bacnet-ip
./labctl verify bacnet-ip
./labctl down bacnet-ip
```

Read every point by hand:

```bash
docker exec clab-bacnet-ip-supervisor python3 /lab/supervisor.py \
  --broadcast 172.111.30.255 --target 172.111.30.10 --target 172.111.30.11 --timeout 3
```

Watch the frames:

```bash
docker exec clab-bacnet-ip-ahu tcpdump -n -i eth1 udp port 47808 -c 20
```

## What is real

- BACnet/IP framing: the BVLC header, the NPDU, and the APDU.
- Who-Is and I-Am discovery, ReadProperty, ReadPropertyMultiple.
- BACnet object identifiers, property identifiers, application tags, and the
  engineering-unit enumeration.
- Broadcast discovery on a single subnet, which is what a flat BMS network is.
- A capture you can read without a vendor tool.

## What is simulated, and what is missing

- The values are chosen numbers, not a psychrometric model. Nothing responds to
  a setpoint.
- There is no write path. `write-property`, the priority array, and relinquish
  defaults are absent, so nothing here can command a fan.
- No confirmed COV subscriptions. A real BMS subscribes and gets notifications
  instead of polling every point.
- No segmentation, no BBMD, no foreign device registration, no routing. A device
  on another subnet cannot be reached from this one.
- No `protocol-services-supported` or `protocol-object-types-supported`
  property. Those are what a BTL test tool reads first, and their absence is the
  clearest difference between this lab and a certified device.
- No alarm and event services, no schedule, no trend log.

That list is the gap between a device that answers what a poller needs and a
device that passes a BTL test. The lab teaches the first. `ARCHITECTURE.md`
explains what each missing piece does in a real building.

## The comparison worth making

The Modbus lab has registers. This lab has objects with names, units, and
status. Ask yourself, for the same physical point:

- Which one tells you the engineering unit without a spreadsheet?
- Which one lets a client discover the point list?
- Which one lets you add a point without changing the client?
- Which one is easier to secure, given that BACnet/IP broadcasts on the
  building network?

Those four answers are the reason building management uses BACnet and metering
uses Modbus, and both answers are in this repository now.
