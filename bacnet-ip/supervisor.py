#!/usr/bin/env python3
"""Discover BACnet devices and read their points.

    python3 supervisor.py --broadcast 172.111.30.255
    python3 supervisor.py --target 172.111.30.10 --device 1001

Three steps, in the order a BMS does them:

1. Who-Is, then collect the I-Am replies. This is discovery, and it is why a
   BACnet network finds itself without a device list in a configuration file.
2. ReadProperty the device object's object-list, to learn which objects exist.
3. ReadPropertyMultiple every point for its name, present value, and units.

A poller that hard-codes the point list skips step 2 and breaks the day someone
adds a point. That is the argument for reading the object list.
"""

import argparse
import socket
import struct
import sys
import time

import bacnet_codec as codec

DISCOVERY_TIMEOUT = 2.0
REPLY_TIMEOUT = 2.0
RETRIES = 2


class Client:
    """One UDP socket, a transaction id per request, and a reply reader."""

    def __init__(self, broadcast="255.255.255.255", port=47808):
        self.broadcast = broadcast
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind(("0.0.0.0", 0))
        self.invoke_id = 0

    def close(self):
        self.sock.close()

    def next_invoke(self):
        self.invoke_id = self.invoke_id % 255 + 1
        return self.invoke_id

    def send(self, frame, address):
        self.sock.sendto(frame, address)

    def receive(self, timeout):
        self.sock.settimeout(timeout)
        try:
            data, address = self.sock.recvfrom(1500)
        except socket.timeout:
            return None, None
        return data, address

    def discover(self, timeout=DISCOVERY_TIMEOUT, targets=()):
        """Who-Is, then collect I-Am replies until the timeout."""
        frame = codec.who_is()
        addresses = [("255.255.255.255", self.port)]
        addresses.extend((target, self.port) for target in targets)
        for address in addresses:
            self.send(frame, address)

        found = {}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data, address = self.receive(max(0.1, deadline - time.monotonic()))
            if data is None:
                continue
            try:
                frame = codec.decode_bvlc(data)
            except codec.DecodeError:
                continue
            apdu = frame.apdu
            if (apdu[0] & 0xF0) != codec.PDU_UNCONFIRMED_REQUEST or apdu[1] != codec.SERVICE_I_AM:
                continue
            instance, _max_apdu, _segmentation = self.parse_i_am(apdu[2:])
            found[instance] = address
        return found

    @staticmethod
    def parse_i_am(parameters):
        number, payload, offset, _context = codec.read_tagged(parameters, 0)
        if number != codec.TAG_OBJECT_ID:
            raise codec.DecodeError("I-Am does not start with an object identifier")
        _type, instance = codec.split_object_identifier(struct.unpack(">I", payload)[0])
        number, payload, offset, _context = codec.read_tagged(parameters, offset)
        max_apdu = codec.decode_value(number, payload)
        number, payload, offset, _context = codec.read_tagged(parameters, offset)
        segmentation = codec.decode_value(number, payload)
        return instance, max_apdu, segmentation

    def request(self, frame, address, service):
        """Send a confirmed request and return its APDU, or raise."""
        invoke = self.next_invoke()
        frame = self.with_invoke(frame, invoke)
        for _attempt in range(RETRIES):
            self.send(frame, address)
            data, _from = self.receive(REPLY_TIMEOUT)
            if data is None:
                continue
            reply = codec.decode_bvlc(data)
            apdu = reply.apdu
            if apdu and apdu[0] & 0xF0 == codec.PDU_ERROR:
                raise BacnetError("error for service %d: class %d code %d" % (apdu[2], apdu[3], apdu[4]))
            if apdu and apdu[0] & 0xF0 == codec.PDU_ABORT:
                raise BacnetError("abort for service %d: reason %d" % (apdu[2], apdu[3]))
            if apdu and len(apdu) > 2 and apdu[1] == invoke:
                return apdu
        raise BacnetError("no reply from %s:%d for service %d" % (address[0], address[1], service))

    @staticmethod
    def with_invoke(frame, invoke):
        """Replace the invoke id of a confirmed request frame."""
        mutated = bytearray(frame)
        mutated[8] = invoke
        return bytes(mutated)

    def read_property(self, address, object_type, instance, prop):
        frame = codec.read_property(object_type, instance, prop)
        apdu = self.request(frame, address, codec.SERVICE_READ_PROPERTY)
        return parse_read_property_ack(apdu)

    def read_property_multiple(self, address, object_type, instance, props):
        frame = codec.read_property_multiple(object_type, instance, props)
        apdu = self.request(frame, address, codec.SERVICE_READ_PROPERTY_MULTIPLE)
        return parse_read_property_multiple_ack(apdu)


class BacnetError(Exception):
    pass


def parse_read_property_ack(apdu):
    """Return (object_id, prop, value) from a ReadProperty complex ACK."""
    if (apdu[0] & 0xF0) != codec.PDU_COMPLEX_ACK:
        raise BacnetError("not a complex ACK")
    reader = _Reader(apdu[3:])
    object_id = reader.read_object_identifier()
    _number, prop_bytes = reader.read()
    prop = prop_bytes[0]
    reader.skip_to_opening(3)
    tag, payload = reader.read_value()
    return object_id, prop, codec.decode_value(tag, payload)


def parse_read_property_multiple_ack(apdu):
    """Return {(object_id, prop): value} from an RPM complex ACK."""
    if (apdu[0] & 0xF0) != codec.PDU_COMPLEX_ACK:
        raise BacnetError("not a complex ACK")
    reader = _Reader(apdu[3:])
    results = {}
    while not reader.at_end():
        object_id = reader.read_object_identifier()
        reader.skip_to_opening(1)
        while not reader.at_closing(1):
            _number, prop_bytes = reader.read()
            prop = prop_bytes[0]
            reader.skip_to_opening(2)
            if not reader.at_closing(2):
                tag, payload = reader.read_value()
                results[(object_id, prop)] = codec.decode_value(tag, payload)
            reader.skip_to_closing(2)
        reader.skip_to_closing(1)
    return results


class _Reader:
    """A small cursor over a parameter list, used only by the parsers above."""

    def __init__(self, data):
        self.data = data
        self.offset = 0

    def at_end(self):
        return self.offset >= len(self.data)

    def read(self):
        number, value, self.offset, _context = codec.read_tagged(self.data, self.offset)
        return number, value

    def read_object_identifier(self):
        _number, value = self.read()
        return struct.unpack(">I", value)[0]

    def read_value(self):
        return self.read()

    def _tag(self):
        number, _length, _offset, _context, opening, closing = codec.decode_tag(self.data, self.offset)
        return number, opening, closing

    def at_closing(self, number):
        tag, _opening, closing = self._tag()
        return closing and tag == number

    def skip_to_opening(self, number):
        tag, opening, _closing = self._tag()
        if not (opening and tag == number):
            raise codec.DecodeError("expected opening tag %d" % number)
        self.offset += 1

    def skip_to_closing(self, number):
        if self.at_closing(number):
            self.offset += 1
            return
        raise codec.DecodeError("expected closing tag %d" % number)


def read_points(client, address, instance):
    """Read every point of a device, using its own object list."""
    _object_id, _prop, objects = client.read_property(
        address, codec.OBJECT_DEVICE, instance, codec.PROP_OBJECT_LIST
    )
    if not isinstance(objects, list):
        raise BacnetError("object-list did not decode as a list")

    rows = []
    for object_id in objects:
        object_type, number = codec.split_object_identifier(object_id)
        if object_type == codec.OBJECT_DEVICE:
            continue
        values = client.read_property_multiple(
            address,
            object_type,
            number,
            [codec.PROP_OBJECT_NAME, codec.PROP_PRESENT_VALUE, codec.PROP_UNITS],
        )
        rows.append(
            {
                "object": codec.object_name(object_type, number),
                "name": values.get((object_id, codec.PROP_OBJECT_NAME), ""),
                "value": values.get((object_id, codec.PROP_PRESENT_VALUE)),
                "units": values.get((object_id, codec.PROP_UNITS)),
            }
        )
    return rows


def format_row(row):
    units = codec.UNIT_NAMES.get(row["units"], "" if row["units"] is None else "unit-%d" % row["units"])
    value = row["value"]
    if isinstance(value, float):
        value = "%.2f" % value
    elif isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    return "  %-18s %-26s %10s %-5s" % (row["object"], row["name"], value, units)


def main(argv):
    parser = argparse.ArgumentParser(description="Discover BACnet devices and read their points.")
    parser.add_argument("--broadcast", default="255.255.255.255", help="broadcast address to send Who-Is to")
    parser.add_argument("--target", action="append", default=[], help="also send Who-Is to this host")
    parser.add_argument("--device", type=int, action="append", default=[], help="only read this device instance")
    parser.add_argument("--port", type=int, default=47808)
    parser.add_argument("--timeout", type=float, default=DISCOVERY_TIMEOUT)
    args = parser.parse_args(argv)

    client = Client(args.broadcast, args.port)
    try:
        devices = client.discover(args.timeout, targets=args.target)
        if not devices:
            print("no I-Am replies. Check the broadcast address, or pass --target with the device address.")
            return 1

        print("discovered %d device(s)" % len(devices))
        for instance in sorted(devices):
            address = devices[instance]
            if args.device and instance not in args.device:
                continue
            print("\ndevice %d at %s:%d" % (instance, address[0], address[1]))
            rows = read_points(client, address, instance)
            for row in rows:
                print(format_row(row))
    except BacnetError as error:
        print("failed: %s" % error)
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
