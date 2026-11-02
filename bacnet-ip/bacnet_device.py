"""The object model of a BACnet device, and the UDP server that answers for it.

A BACnet device is a table of objects and a table of properties per object. A
point is not a register. That is the first thing to unlearn when you come from
Modbus: `analog-input,3` has a name, a unit, a status, and a present value, and
a client asks for the property it wants by identifier.

This module implements one device with the objects an air handling unit
exposes, and serves ReadProperty and ReadPropertyMultiple over UDP.
"""

import socket
import struct

import bacnet_codec as codec


class UnknownObject(Exception):
    pass


class UnknownProperty(Exception):
    pass


class Point:
    """One object below the device object."""

    def __init__(self, object_type, instance, name, value, units=None, description=""):
        self.object_type = object_type
        self.instance = instance
        self.name = name
        self.value = value
        self.units = units
        self.description = description

    @property
    def object_identifier(self):
        return codec.object_identifier(self.object_type, self.instance)

    def present_value_bytes(self):
        """The present-value property, encoded with the type the point carries."""
        if self.object_type in (
            codec.OBJECT_ANALOG_INPUT,
            codec.OBJECT_ANALOG_OUTPUT,
            codec.OBJECT_ANALOG_VALUE,
        ):
            return codec.encode_value(codec.TAG_REAL, self.value)
        # A binary point carries an enumerated active or inactive.
        return codec.encode_value(codec.TAG_ENUMERATED, 1 if self.value else 0)

    def __repr__(self):
        return "Point(%s, value=%r)" % (codec.object_name(self.object_type, self.instance), self.value)


class Device:
    """A device object with its points, and the property lookups a client needs."""

    def __init__(self, instance, name, vendor_name, vendor_id, model_name, points):
        self.instance = instance
        self.name = name
        self.vendor_name = vendor_name
        self.vendor_id = vendor_id
        self.model_name = model_name
        self.points = list(points)
        self._by_id = {point.object_identifier: point for point in self.points}
        if len(self._by_id) != len(self.points):
            raise ValueError("two points share an object identifier")

    @property
    def object_identifier(self):
        return codec.object_identifier(codec.OBJECT_DEVICE, self.instance)

    def object_list(self):
        """The device itself first, then every point, in instance order."""
        return [self.object_identifier] + sorted(self._by_id)

    def point(self, object_type, instance):
        if object_type == codec.OBJECT_DEVICE:
            raise UnknownObject("the device object is not a point")
        key = codec.object_identifier(object_type, instance)
        try:
            return self._by_id[key]
        except KeyError:
            raise UnknownObject(codec.object_name(object_type, instance))

    def properties(self, object_type, instance):
        """Every property this object answers, as encoded bytes."""
        values = {}

        if object_type == codec.OBJECT_DEVICE:
            if instance != self.instance:
                raise UnknownObject(codec.object_name(object_type, instance))
            values[codec.PROP_OBJECT_IDENTIFIER] = codec.encode_value(codec.TAG_OBJECT_ID, self.object_identifier)
            values[codec.PROP_OBJECT_NAME] = codec.encode_value(codec.TAG_CHARACTER_STRING, self.name)
            values[codec.PROP_OBJECT_TYPE] = codec.encode_value(codec.TAG_ENUMERATED, codec.OBJECT_DEVICE)
            values[codec.PROP_VENDOR_NAME] = codec.encode_value(codec.TAG_CHARACTER_STRING, self.vendor_name)
            values[codec.PROP_VENDOR_IDENTIFIER] = codec.encode_value(codec.TAG_UNSIGNED, self.vendor_id)
            values[codec.PROP_MODEL_NAME] = codec.encode_value(codec.TAG_CHARACTER_STRING, self.model_name)
            values[codec.PROP_MAX_APDU_LENGTH_ACCEPTED] = codec.encode_value(codec.TAG_UNSIGNED, 1476)
            values[codec.PROP_SYSTEM_STATUS] = codec.encode_value(codec.TAG_ENUMERATED, 0)
            values[codec.PROP_OBJECT_LIST] = codec.encode_value(
                codec.TAG_OBJECT_ID, b"".join(struct.pack(">I", item) for item in self.object_list())
            )
            return values

        point = self.point(object_type, instance)
        values[codec.PROP_OBJECT_IDENTIFIER] = codec.encode_value(codec.TAG_OBJECT_ID, point.object_identifier)
        values[codec.PROP_OBJECT_NAME] = codec.encode_value(codec.TAG_CHARACTER_STRING, point.name)
        values[codec.PROP_OBJECT_TYPE] = codec.encode_value(codec.TAG_ENUMERATED, point.object_type)
        values[codec.PROP_PRESENT_VALUE] = point.present_value_bytes()
        # Four status bits, all clear: in-alarm, fault, overridden, out-of-service.
        values[codec.PROP_STATUS_FLAGS] = codec.encode_value(codec.TAG_BIT_STRING, [0, 0, 0, 0])
        if point.units is not None:
            values[codec.PROP_UNITS] = codec.encode_value(codec.TAG_ENUMERATED, point.units)
        if point.description:
            values[codec.PROP_DESCRIPTION] = codec.encode_value(codec.TAG_CHARACTER_STRING, point.description)
        return values

    def property_value(self, object_type, instance, prop, array_index=None):
        values = self.properties(object_type, instance)
        try:
            encoded = values[prop]
        except KeyError:
            raise UnknownProperty(codec.PROPERTY_NAMES.get(prop, "property-%d" % prop))
        return encoded

    def set_value(self, object_type, instance, value):
        point = self.point(object_type, instance)
        point.value = value


def _is_opening(first, number):
    """An opening tag is (number << 4) | 0x0E inside a context tag header."""
    return (first >> 4) == number and (first & 0x0F) == 0x0E


def _is_closing(first, number):
    return (first >> 4) == number and (first & 0x0F) == 0x0F


class FrameIO:
    """Read a tagged parameter list, in the order a confirmed request carries it."""

    def __init__(self, data):
        self.data = data
        self.offset = 0

    def at_end(self):
        return self.offset >= len(self.data)

    def peek(self):
        if self.at_end():
            raise codec.DecodeError("parameter list ended early")
        return self.data[self.offset]

    def read(self):
        number, value, self.offset, _context = codec.read_tagged(self.data, self.offset)
        return number, value

    def read_object_identifier(self):
        _number, value = self.read()
        return struct.unpack(">I", value)[0]

    def read_list_of_object_identifiers(self):
        """Read a list that is either one object id or a constructed list of them."""
        first = self.peek()
        if _is_opening(first, 0):
            self.offset += 1
            items = []
            while not _is_closing(self.peek(), 0):
                _number, value = self.read()
                items.append(struct.unpack(">I", value)[0])
            self.offset += 1
            return items
        return [self.read_object_identifier()]

    def read_property_list(self):
        """Read the property specifiers of a ReadPropertyMultiple request."""
        props = []
        while not self.at_end():
            first = self.peek()
            if _is_opening(first, 1):
                self.offset += 1
                while not _is_closing(self.peek(), 1):
                    _number, value = self.read()
                    props.append(value[0])
                self.offset += 1
            else:
                _number, value = self.read()
                props.append(value[0])
        return props


class DeviceServer:
    """One UDP socket on port 47808, answering for one device."""

    def __init__(self, device, bind="0.0.0.0", port=47808, verbose=False):
        self.device = device
        self.bind = bind
        self.port = port
        self.verbose = verbose
        self.requests = 0
        self.unknown_object = 0
        self.unknown_property = 0

    def open(self):
        """Bind the socket, so a test can ask which port it landed on."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind((self.bind, self.port))
        self.port = self.sock.getsockname()[1]
        return self.port

    def close(self):
        self.sock.close()

    def serve_forever(self, stop=None):
        """Answer frames until `stop` is set, or for ever when it is None."""
        if not hasattr(self, "sock"):
            self.open()
        self.sock.settimeout(0.2)
        self.log("device %s listening on %s:%d" % (self.device.name, self.bind, self.port))
        while stop is None or not stop.is_set():
            try:
                data, address = self.sock.recvfrom(1500)
            except socket.timeout:
                continue
            reply = self.handle(data, address)
            if reply:
                self.sock.sendto(reply, address)

    def log(self, message):
        if self.verbose:
            print(message, flush=True)

    def handle(self, data, address=None):
        """Decode one frame and return the reply bytes, or None."""
        try:
            frame = codec.decode_bvlc(data)
        except codec.DecodeError as error:
            self.log("dropped a frame: %s" % error)
            return None

        apdu = frame.apdu
        if not apdu:
            return None
        pdu_type = apdu[0] & 0xF0

        if pdu_type == codec.PDU_UNCONFIRMED_REQUEST:
            service = apdu[1]
            if service == codec.SERVICE_WHO_IS:
                self.requests += 1
                self.log("who-is from %s, replying i-am" % (address,))
                return codec.i_am(self.device.instance)
            return None

        if pdu_type != codec.PDU_CONFIRMED_REQUEST:
            return None

        invoke_id = apdu[2]
        service = apdu[3]
        parameters = apdu[4:]
        self.requests += 1

        if service == codec.SERVICE_READ_PROPERTY:
            return self.read_property(invoke_id, parameters)
        if service == codec.SERVICE_READ_PROPERTY_MULTIPLE:
            return self.read_property_multiple(invoke_id, parameters)
        # A device that does not implement a service aborts the request.
        self.log("aborting unsupported service %d" % service)
        return codec.bvlc(codec.BVLC_ORIGINAL_UNICAST, codec.npdu(codec.abort_pdu(invoke_id, service, 0)))

    def read_property(self, invoke_id, parameters):
        reader = FrameIO(parameters)
        object_id = reader.read_object_identifier()
        _number, prop_bytes = reader.read()
        prop = prop_bytes[0]
        array_index = None
        if not reader.at_end():
            _number, index_bytes = reader.read()
            array_index = int.from_bytes(index_bytes, "big")

        object_type, instance = codec.split_object_identifier(object_id)
        try:
            encoded = self.device.property_value(object_type, instance, prop, array_index)
        except UnknownObject:
            self.unknown_object += 1
            # Error class 1 is object, code 2 is unknown-object.
            return codec.bvlc(
                codec.BVLC_ORIGINAL_UNICAST,
                codec.npdu(codec.error_pdu(invoke_id, codec.SERVICE_READ_PROPERTY, 1, 2)),
            )
        except UnknownProperty:
            self.unknown_property += 1
            # Error class 2 is property, code 2 is unknown-property.
            return codec.bvlc(
                codec.BVLC_ORIGINAL_UNICAST,
                codec.npdu(codec.error_pdu(invoke_id, codec.SERVICE_READ_PROPERTY, 2, 2)),
            )

        return codec.read_property_ack(invoke_id, object_type, instance, prop, encoded)

    def read_property_multiple(self, invoke_id, parameters):
        reader = FrameIO(parameters)
        object_id = reader.read_object_identifier()
        props = reader.read_property_list()
        object_type, instance = codec.split_object_identifier(object_id)

        try:
            values = self.device.properties(object_type, instance)
        except UnknownObject:
            self.unknown_object += 1
            return codec.bvlc(
                codec.BVLC_ORIGINAL_UNICAST,
                codec.npdu(codec.error_pdu(invoke_id, codec.SERVICE_READ_PROPERTY_MULTIPLE, 1, 2)),
            )

        body = codec.context_tag(0, struct.pack(">I", object_id))
        body += codec.opening_tag(1)
        for prop in props:
            body += codec.context_tag(0, bytes((prop,)))
            body += codec.opening_tag(2)
            if prop in values:
                body += values[prop]
            body += codec.closing_tag(2)
        body += codec.closing_tag(1)

        return codec.bvlc(
            codec.BVLC_ORIGINAL_UNICAST,
            codec.npdu(codec.complex_ack(invoke_id, codec.SERVICE_READ_PROPERTY_MULTIPLE, body)),
        )
