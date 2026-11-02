# BACnet/IP architecture

## Why there is no link

Every other lab here has a private link between the process model and the
controller. This one has none, and that is the architecture.

BACnet/IP is BACnet messages carried in UDP on port 47808, on the building
network. A device is an IP host with an IP address, not a serial node behind a
gateway. Three consequences follow, and all three matter in a real building:

1. Discovery is a broadcast. Who-Is goes to the subnet broadcast address and
   every device answers I-Am. A flat network finds everything. A routed network
   finds nothing until you add a BBMD.
2. The protocol shares the network with everything else. A capture on that
   network reads the building controls, which is why segmentation is a control
   and not a nicety.
3. Address changes break clients that use addresses instead of device
   instances. A well written client binds to the device instance and re-learns
   the address from an I-Am. That is why step 1 of the client here is discovery.

## The stack, in the order the bytes appear

```
+----------------------------------------+  BVLC
| 81  function  length(2)                |  BACnet Virtual Link Control
+----------------------------------------+  NPDU
| 01  control  [addresses]               |  network layer
+----------------------------------------+  APDU
| type  invoke-id  service  parameters   |  application layer
+----------------------------------------+
```

- BVLC type is `0x81`. Function `0x0A` is original-unicast, `0x0B` is
  original-broadcast. The length covers the whole frame, so a decoder can check
  it against the datagram size, which `bacnet_codec.py` does.
- The NPDU version is 1. The control byte says whether a reply is expected and
  whether the frame is routed. This lab sets the expecting-reply bit and
  refuses routed frames rather than guessing.
- The APDU carries the service. `0x00` is a confirmed request, `0x10` an
  unconfirmed request (Who-Is, I-Am), `0x20` a complex ACK, `0x50` an error,
  `0x70` an abort.

## Tags

BACnet encodes every value with a tag that names its type: 4 is Real, 9 is
Enumerated, 12 is ObjectIdentifier, and so on. A tag where the length bit is
clear is an application tag and the low three bits are the length. A tag where
that bit is set is a context tag, and 6 and 7 in those low bits open and close a
constructed value instead.

Constructed values are how a list is sent. `ReadPropertyMultiple` wraps its
property list in opening tag 1, and the reply wraps each value in opening tag 2
and the whole answer in tag 3.

## The properties a poller asks for

| Property | Identifier | Why |
|---|---|---|
| object-identifier | 75 | what the object is |
| object-name | 77 | the point name in the schedule |
| present-value | 85 | the number |
| units | 117 | what the number means |
| status-flags | 111 | in alarm, faulted, overridden, out of service |
| object-list | 76 | the device's own object inventory |

## What a real building adds

Each item is a real feature with a real cost, and each is a good next exercise.

**BBMD.** A BACnet Broadcast Management Device forwards broadcasts between
subnets. A campus puts one BBMD per subnet and registers the others, because
broadcast does not route. A foreign device registration lets a workstation on
another subnet ask a BBMD to relay for it. Without this, a client on the
corporate network cannot discover a device in the plant network, and that is
exactly the boundary a good design keeps in place.

**COV subscriptions.** Change-of-value subscriptions replace polling. The client
subscribes, the device sends a notification when the value moves, and the
network stops carrying reads that return the same number. A BMS with 20 000
points polls badly and subscribes well.

**The priority array.** A write is not a value, it is a value at one of sixteen
priorities. The effective value is the highest priority that has a value.
Relinquishing a priority lets a lower one take effect. That is how a schedule,
an operator, and a safety interlock can all write the same point without
overwriting each other.

**Segmentation.** A long response is split when the frame will not fit the
maximum APDU. This lab always sends 1476 octets and never segments.

**BTL listing.** A Building Technologies Laboratory test checks several hundred
behaviours, including the two properties this device does not have. A listed
device interoperates with other vendors without a gateway. A device that merely
answers reads is a lab.

## Where this sits

Purdue level 1 for the devices, level 2 for the supervisor, and the same network
as everything else because BACnet/IP has no separate physical layer. The
correction a real design applies is a VLAN and a conduit rule, not a different
protocol. That is why `docs/architecture.md` treats zone and conduit as the
control and the protocol as the traffic inside it.
