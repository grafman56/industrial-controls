# Getting started with the BACnet/IP lab

## Deploy it

```bash
cd ~/work/industrial-controls
./labctl doctor
./labctl up bacnet-ip
./labctl verify bacnet-ip
```

`verify` reads nineteen points across two devices. If it prints them, the lab
works.

## Read the points yourself

```bash
docker exec clab-bacnet-ip-supervisor python3 /lab/supervisor.py \
  --broadcast 172.111.30.255 --target 172.111.30.10 --target 172.111.30.11 --timeout 3
```

The `--target` options are there because broadcast behaviour depends on the
host network. Passing the addresses directly makes the result independent of it.

## Read one property

Every point read starts as a ReadProperty for one property of one object. On a
real job you do this with a tool, but the frame is the same. Ask for the
present value of the supply air temperature:

```bash
docker exec clab-bacnet-ip-supervisor python3 - <<'PY'
import sys
sys.path.insert(0, "/lab")
import bacnet_codec as codec
from supervisor import Client

client = Client(broadcast="172.111.30.255")
try:
    devices = client.discover(2.0, targets=["172.111.30.10"])
    address = devices[1001]
    object_id, prop, value = client.read_property(
        address, codec.OBJECT_ANALOG_INPUT, 1, codec.PROP_PRESENT_VALUE
    )
    print("object %s property %d value %r" % (
        codec.object_name(*codec.split_object_identifier(object_id)),
        prop,
        value,
    ))
finally:
    client.close()
PY
```

Change `PROP_PRESENT_VALUE` to `PROP_OBJECT_NAME` or `PROP_UNITS` and the same
call returns those instead. That is the whole idea of BACnet reads: an object, a
property, and a value.

## Look at the wire

Start a capture, then read:

```bash
docker exec clab-bacnet-ip-ahu tcpdump -n -i eth1 udp port 47808 -c 30 -w /tmp/bacnet.pcap
docker cp clab-bacnet-ip-ahu:/tmp/bacnet.pcap ./bacnet.pcap
```

Open it in Wireshark. The dissector names the service, the object, and the
property, and the raw bytes match `bacnet_codec.py`. Read the Who-Is first, then
the I-Am, then the confirmed request and its complex ACK.

To capture at the moment of a read, run the capture in the background first:

```bash
docker exec -d clab-bacnet-ip-ahu tcpdump -n -i eth1 udp port 47808 -w /tmp/bacnet.pcap
docker exec clab-bacnet-ip-supervisor python3 /lab/supervisor.py \
  --broadcast 172.111.30.255 --target 172.111.30.10 --timeout 2
docker exec clab-bacnet-ip-ahu pkill tcpdump
docker cp clab-bacnet-ip-ahu:/tmp/bacnet.pcap ./bacnet.pcap
```

## Use a laptop tool

The AHU publishes UDP 47808 on `127.0.0.1`, so a BACnet tool on your machine can
read device 1001 by unicast. Use whatever client you have: a BACnet explorer
such as YABE is one example, and the protocol is the same in all of them.

Point it at `127.0.0.1:47808`, or at the device instance 1001 if the tool
asks for one.

Discovery from the laptop will not work, and that is not a fault. Who-Is is a
broadcast, the port forward is not a broadcast domain, and nothing here is a
BBMD. Unicast reads work. That difference is the reason `ARCHITECTURE.md` has a
section on BBMD.

## Exercises, in order

1. Read `analog-input,5` and say what the point is physically. The name and the
   unit answer it without a register map.
2. Read `status-flags` and explain why a BACnet point needs four bits where a
   Modbus register needs none.
3. Add a point to `ahu.py`, deploy again, and confirm the client reads it
   without any change. Then explain what would have been required in the Modbus
   lab.
4. Capture a full read of the AHU and count the datagrams. Compare that with a
   polling client that reads one point per request, which is what the "read one
   property" example does.
5. Change the AHU instance number to 2001 and watch discovery. Then change only
   the IP address and watch discovery again. The second case should still work,
   because the client binds to the instance, not the address.
6. Write down what an attacker on the same VLAN can do with Who-Is. Then read
   `docs/architecture.md` on zones and conduits.
