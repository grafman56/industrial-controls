"""A small BACnet/IP codec: enough of the standard to read a device.

Only what a point poller needs is here:

- the BVLC header, which is what makes it BACnet/IP instead of BACnet over
  another link layer
- the NPDU, which carries the routing flags
- confirmed requests and complex ACKs, for ReadProperty and
  ReadPropertyMultiple
- unconfirmed Who-Is and I-Am, for discovery
- application tags for the value types an equipment controller carries:
  Boolean, Unsigned, Real, CharacterString, BitString, Enumerated, and
  BACnetObjectIdentifier

Not here, on purpose: segmentation, confirmed COV subscriptions, the priority
array for writes, BBMD and foreign-device registration, and the routing
services. `README.md` lists what that costs.

Bit layout follows the standard's clause on the encoding, and every function
here has a test. The tests check the byte layout, not interoperation with a
vendor device, because no vendor device is in this lab.
"""

import struct

# BVLC, the BACnet Virtual Link Control header.
BVLC_TYPE = 0x81
BVLC_ORIGINAL_UNICAST = 0x0A
BVLC_ORIGINAL_BROADCAST = 0x0B

# NPDU control bits.
NPDU_EXPECTING_REPLY = 0x04
NPDU_DO_NOT_EXPECT_REPLY = 0x00

# PDU types, from the low nibble of the first APDU byte.
PDU_CONFIRMED_REQUEST = 0x00
PDU_UNCONFIRMED_REQUEST = 0x10
PDU_SIMPLE_ACK = 0x20
PDU_COMPLEX_ACK = 0x20
PDU_ERROR = 0x50
PDU_ABORT = 0x70

# Unconfirmed services.
SERVICE_I_AM = 0x00
SERVICE_WHO_IS = 0x08

# Confirmed services.
SERVICE_READ_PROPERTY = 0x0C
SERVICE_READ_PROPERTY_MULTIPLE = 0x0E

# Application tags.
TAG_NULL = 0
TAG_BOOLEAN = 1
TAG_UNSIGNED = 2
TAG_SIGNED = 3
TAG_REAL = 4
TAG_DOUBLE = 5
TAG_OCTET_STRING = 6
TAG_CHARACTER_STRING = 7
TAG_BIT_STRING = 8
TAG_ENUMERATED = 9
TAG_DATE = 10
TAG_TIME = 11
TAG_OBJECT_ID = 12

LENGTH_MINUS_ONE_FORMS = (5,)

# Object types.
OBJECT_ANALOG_INPUT = 0
OBJECT_ANALOG_OUTPUT = 1
OBJECT_ANALOG_VALUE = 2
OBJECT_BINARY_INPUT = 3
OBJECT_BINARY_OUTPUT = 4
OBJECT_BINARY_VALUE = 5
OBJECT_DEVICE = 8

OBJECT_TYPE_NAMES = {
    OBJECT_ANALOG_INPUT: "analog-input",
    OBJECT_ANALOG_OUTPUT: "analog-output",
    OBJECT_ANALOG_VALUE: "analog-value",
    OBJECT_BINARY_INPUT: "binary-input",
    OBJECT_BINARY_OUTPUT: "binary-output",
    OBJECT_BINARY_VALUE: "binary-value",
    OBJECT_DEVICE: "device",
}

# Property identifiers. Only the ones this lab reads.
PROP_DESCRIPTION = 28
PROP_MAX_APDU_LENGTH_ACCEPTED = 62
PROP_MODEL_NAME = 70
PROP_OBJECT_IDENTIFIER = 75
PROP_OBJECT_LIST = 76
PROP_OBJECT_NAME = 77
PROP_OBJECT_TYPE = 79
PROP_PRESENT_VALUE = 85
PROP_STATUS_FLAGS = 111
PROP_SYSTEM_STATUS = 112
PROP_UNITS = 117
PROP_VENDOR_IDENTIFIER = 120
PROP_VENDOR_NAME = 121

PROPERTY_NAMES = {
    PROP_DESCRIPTION: "description",
    PROP_MAX_APDU_LENGTH_ACCEPTED: "max-apdu-length-accepted",
    PROP_MODEL_NAME: "model-name",
    PROP_OBJECT_IDENTIFIER: "object-identifier",
    PROP_OBJECT_LIST: "object-list",
    PROP_OBJECT_NAME: "object-name",
    PROP_OBJECT_TYPE: "object-type",
    PROP_PRESENT_VALUE: "present-value",
    PROP_STATUS_FLAGS: "status-flags",
    PROP_SYSTEM_STATUS: "system-status",
    PROP_UNITS: "units",
    PROP_VENDOR_IDENTIFIER: "vendor-identifier",
    PROP_VENDOR_NAME: "vendor-name",
}

# Engineering units. The standard's enumeration, for the units in this lab.
UNITS_DEGREES_CELSIUS = 62
UNITS_PERCENT = 98
UNITS_PASCALS = 53
UNITS_NO_UNITS = 95

UNIT_NAMES = {
    UNITS_DEGREES_CELSIUS: "degC",
    UNITS_PERCENT: "%",
    UNITS_PASCALS: "Pa",
    UNITS_NO_UNITS: "",
}


class DecodeError(Exception):
    """The bytes on the wire are not a frame this codec understands."""


# ---------------------------------------------------------------------------
# Objects
# ---------------------------------------------------------------------------


def object_identifier(object_type, instance):
    return (object_type << 22) | (instance & 0x3FFFFF)


def split_object_identifier(value):
    return value >> 22, value & 0x3FFFFF


def object_name(object_type, instance):
    return "%s,%d" % (OBJECT_TYPE_NAMES.get(object_type, "type-%d" % object_type), instance)


# ---------------------------------------------------------------------------
# Application and context tags
# ---------------------------------------------------------------------------


def application_tag(number, payload):
    """Wrap bytes in an application tag.

    An application tag has the LVT bit clear, so the low three bits are the
    length when it fits: 0 to 4 directly, 5 means one length octet follows,
    6 means two length octets follow.
    """
    length = len(payload)
    first = number << 4
    if length <= 4:
        return bytes((first | length,)) + payload
    if length <= 253:
        return bytes((first | 5, length)) + payload
    return bytes((first | 6,)) + struct.pack(">H", length) + payload


def context_tag(number, payload):
    """Wrap bytes in a context tag, always in the length form."""
    length = len(payload)
    first = number << 4 | 0x08
    if length <= 4:
        return bytes((first | length,)) + payload
    if length <= 253:
        return bytes((first | 5, length)) + payload
    return bytes((first | 5, 254)) + struct.pack(">H", length) + payload


def opening_tag(number):
    return bytes(((number << 4) | 0x0E,))


def closing_tag(number):
    return bytes(((number << 4) | 0x0F,))


def encode_value(tag, value):
    """Encode a Python value with the application tag the type needs."""
    if tag == TAG_BOOLEAN:
        return application_tag(TAG_BOOLEAN, bytes((1 if value else 0,)))
    if tag == TAG_UNSIGNED:
        return application_tag(TAG_UNSIGNED, unsigned_bytes(int(value)))
    if tag == TAG_SIGNED:
        return application_tag(TAG_SIGNED, signed_bytes(int(value)))
    if tag == TAG_REAL:
        return application_tag(TAG_REAL, struct.pack(">f", float(value)))
    if tag == TAG_DOUBLE:
        return application_tag(TAG_DOUBLE, struct.pack(">d", float(value)))
    if tag == TAG_ENUMERATED:
        return application_tag(TAG_ENUMERATED, unsigned_bytes(int(value)))
    if tag == TAG_OBJECT_ID:
        # One identifier, or a pre-joined list of them for object-list.
        if isinstance(value, (bytes, bytearray)):
            return application_tag(TAG_OBJECT_ID, bytes(value))
        return application_tag(TAG_OBJECT_ID, struct.pack(">I", int(value)))
    if tag == TAG_CHARACTER_STRING:
        if isinstance(value, bytes):
            raw = value
        else:
            raw = str(value).encode("utf-8")
        return application_tag(TAG_CHARACTER_STRING, b"\x00" + raw)
    if tag == TAG_BIT_STRING:
        if isinstance(value, int):
            bits = [0] * value
        elif isinstance(value, (bytes, bytearray)):
            bits = [(byte >> shift) & 1 for byte in value for shift in range(7, -1, -1)]
        else:
            bits = [1 if bit else 0 for bit in value]
        unused = (8 - len(bits) % 8) % 8
        padded = bits + [0] * unused
        packed = bytearray()
        for start in range(0, len(padded), 8):
            byte = 0
            for bit in padded[start:start + 8]:
                byte = (byte << 1) | bit
            packed.append(byte)
        return application_tag(TAG_BIT_STRING, bytes((unused,)) + bytes(packed))
    raise ValueError("no encoder for application tag %d" % tag)


def unsigned_bytes(value):
    if value < 0:
        raise ValueError("unsigned value is negative")
    width = max(1, (value.bit_length() + 7) // 8)
    return value.to_bytes(width, "big")


def signed_bytes(value):
    if value >= 0:
        return unsigned_bytes(value)
    width = max(1, (value.bit_length() + 8) // 8)
    return value.to_bytes(width, "big", signed=True)


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------


def bvlc(function, npdu):
    """Wrap an NPDU in the BVLC header that makes it BACnet/IP."""
    return bytes((BVLC_TYPE, function)) + struct.pack(">H", len(npdu) + 4) + npdu


def npdu(apdu, expecting_reply=True):
    """A non-routed NPDU. A device that does not route sends no addresses."""
    control = NPDU_EXPECTING_REPLY if expecting_reply else NPDU_DO_NOT_EXPECT_REPLY
    return bytes((0x01, control)) + apdu


def confirmed_request(invoke_id, service, parameters):
    # 0x05 is the maximum-APDU octet this lab accepts (1476 octets, no
    # segmentation). A device that does not segment always sends that form.
    return bytes((PDU_CONFIRMED_REQUEST, 0x05, invoke_id & 0xFF, service)) + parameters


def unconfirmed_request(service, parameters=b""):
    return bytes((PDU_UNCONFIRMED_REQUEST, service)) + parameters


def complex_ack(invoke_id, service, parameters):
    return bytes((0x20, invoke_id & 0xFF, service)) + parameters


def error_pdu(invoke_id, service, error_class, error_code):
    return bytes((PDU_ERROR, invoke_id & 0xFF, service, error_class, error_code))


def abort_pdu(invoke_id, service, reason):
    return bytes((PDU_ABORT | 0x01, invoke_id & 0xFF, service, reason))


def who_is(device_instance_low=None, device_instance_high=None):
    """Who-Is, with the optional instance range."""
    parameters = b""
    if device_instance_low is not None:
        parameters = context_tag(0, unsigned_bytes(device_instance_low))
        parameters += context_tag(1, unsigned_bytes(device_instance_high))
    return bvlc(BVLC_ORIGINAL_BROADCAST, npdu(unconfirmed_request(SERVICE_WHO_IS, parameters), expecting_reply=False))


def i_am(device_instance, max_apdu=1476, segmentation=3):
    """I-Am. Segmentation 3 is no-segmentation."""
    parameters = encode_value(TAG_OBJECT_ID, object_identifier(OBJECT_DEVICE, device_instance))
    parameters += encode_value(TAG_UNSIGNED, max_apdu)
    parameters += encode_value(TAG_ENUMERATED, segmentation)
    return bvlc(BVLC_ORIGINAL_BROADCAST, npdu(unconfirmed_request(SERVICE_I_AM, parameters), expecting_reply=False))


def read_property(object_type, instance, prop, invoke_id=1, array_index=None):
    """A ReadProperty confirmed request."""
    parameters = context_tag(0, struct.pack(">I", object_identifier(object_type, instance)))
    parameters += context_tag(1, bytes((prop,)))
    if array_index is not None:
        parameters += context_tag(2, unsigned_bytes(array_index))
    return bvlc(
        BVLC_ORIGINAL_UNICAST,
        npdu(confirmed_request(invoke_id, SERVICE_READ_PROPERTY, parameters)),
    )


def read_property_multiple(object_type, instance, props, invoke_id=1):
    """A ReadPropertyMultiple confirmed request for one object."""
    parameters = context_tag(0, struct.pack(">I", object_identifier(object_type, instance)))
    parameters += opening_tag(1)
    for prop in props:
        parameters += context_tag(0, bytes((prop,)))
    parameters += closing_tag(1)
    return bvlc(
        BVLC_ORIGINAL_UNICAST,
        npdu(confirmed_request(invoke_id, SERVICE_READ_PROPERTY_MULTIPLE, parameters)),
    )


def read_property_ack(invoke_id, object_type, instance, prop, encoded_value):
    """A ReadProperty complex ACK around an already encoded value."""
    parameters = context_tag(0, struct.pack(">I", object_identifier(object_type, instance)))
    parameters += context_tag(1, bytes((prop,)))
    parameters += opening_tag(3) + encoded_value + closing_tag(3)
    return bvlc(
        BVLC_ORIGINAL_UNICAST,
        npdu(complex_ack(invoke_id, SERVICE_READ_PROPERTY, parameters)),
    )


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------


class Frame:
    def __init__(self, bvlc_function, payload, npdu_control):
        self.bvlc_function = bvlc_function
        self.payload = payload
        self.npdu_control = npdu_control

    @property
    def apdu(self):
        return self.payload

    def describe(self):
        return "bvlc=0x%02x control=0x%02x %s" % (
            self.bvlc_function,
            self.npdu_control,
            describe_apdu(self.apdu),
        )


def decode_bvlc(data):
    """Strip the BVLC header and the NPDU, and return the frame."""
    if len(data) < 6:
        raise DecodeError("frame is shorter than a BVLC header")
    if data[0] != BVLC_TYPE:
        raise DecodeError("not a BACnet/IP frame: type 0x%02x" % data[0])
    function = data[1]
    declared = struct.unpack(">H", data[2:4])[0]
    if declared != len(data):
        raise DecodeError("BVLC length says %d octets, frame is %d" % (declared, len(data)))
    if data[4] != 0x01:
        raise DecodeError("NPDU version %d is not 1" % data[4])

    control = data[5]
    if control & 0x20:
        raise DecodeError("routed NPDU is not decoded by this lab")
    offset = 6
    if control & 0x08:
        if offset + 2 > len(data):
            raise DecodeError("NPDU destination is truncated")
        dlen = data[offset + 1]
        offset += 2 + dlen + 1
    if control & 0x10:
        if offset + 3 > len(data):
            raise DecodeError("NPDU source is truncated")
        slen = data[offset + 1]
        offset += 2 + slen + 1
    if offset > len(data):
        raise DecodeError("NPDU addresses run past the end of the frame")
    return Frame(function, data[offset:], control)


def describe_apdu(apdu):
    if not apdu:
        return "empty APDU"
    pdu_type = apdu[0] & 0xF0
    if pdu_type == PDU_CONFIRMED_REQUEST:
        if len(apdu) < 4:
            return "truncated confirmed request"
        return "confirmed-request invoke=%d service=%d" % (apdu[2], apdu[3])
    if pdu_type == PDU_UNCONFIRMED_REQUEST:
        if len(apdu) < 2:
            return "truncated unconfirmed request"
        service = apdu[1]
        name = {SERVICE_I_AM: "i-am", SERVICE_WHO_IS: "who-is"}.get(service, "service %d" % service)
        return "unconfirmed-request %s" % name
    if pdu_type == PDU_COMPLEX_ACK:
        return "complex-ack invoke=%d service=%d" % (apdu[1], apdu[2])
    if pdu_type == PDU_ERROR:
        return "error invoke=%d class=%d code=%d" % (apdu[1], apdu[3], apdu[4])
    if pdu_type == PDU_ABORT:
        return "abort invoke=%d reason=%d" % (apdu[1], apdu[3])
    return "pdu type 0x%02x" % apdu[0]


def decode_tag(data, offset):
    """Read one tag header.

    Returns (number, length, value_offset, is_context, is_opening, is_closing).

    LVT=0 means an application tag, and the low three bits hold the length
    (5 means the next octet holds it). LVT=1 means a context tag, where the
    low three bits hold the length in the same way, except 6 which opens a
    constructed value and 7 which closes it.
    """
    if offset >= len(data):
        raise DecodeError("tag is past the end of the frame")
    first = data[offset]
    number = first >> 4
    if number == 0x0F:
        if offset + 1 >= len(data):
            raise DecodeError("extended tag number is truncated")
        number = data[offset + 1] + 15
        offset += 1
        first = data[offset]
    length_form = (first >> 3) & 0x01
    low = first & 0x07
    offset += 1

    if length_form == 0:
        # Application tag: the low bits are the length.
        if low <= 4:
            return number, low, offset, False, False, False
        if low == 5:
            return number, data[offset], offset + 1, False, False, False
        if low == 6:
            return number, struct.unpack(">H", data[offset:offset + 2])[0], offset + 2, False, False, False
        raise DecodeError("application tag length form 7 is reserved")

    # Context tag.
    if low == 6:
        return number, 0, offset, True, True, False
    if low == 7:
        return number, 0, offset, True, False, True
    if low <= 4:
        return number, low, offset, True, False, False
    return number, data[offset], offset + 1, True, False, False


def read_tagged(data, offset, context=False):
    """Read a tag and the bytes it carries, returning (number, value, offset)."""
    number, length, value_offset, is_context, opening, closing = decode_tag(data, offset)
    if opening or closing:
        raise DecodeError("expected a value tag, found a %s tag" % ("closing" if closing else "opening"))
    end = value_offset + length
    if end > len(data):
        raise DecodeError("tag value runs past the end of the frame")
    return number, data[value_offset:end], end, is_context


def decode_value(tag, payload):
    """Turn one application-tagged payload into a Python value."""
    if tag == TAG_BOOLEAN:
        return bool(payload[0]) if payload else False
    if tag == TAG_UNSIGNED:
        return int.from_bytes(payload, "big")
    if tag == TAG_SIGNED:
        return int.from_bytes(payload, "big", signed=True)
    if tag == TAG_REAL:
        return struct.unpack(">f", payload)[0]
    if tag == TAG_DOUBLE:
        return struct.unpack(">d", payload)[0]
    if tag == TAG_ENUMERATED:
        return int.from_bytes(payload, "big")
    if tag == TAG_CHARACTER_STRING:
        return payload[1:].decode("utf-8", "replace")
    if tag == TAG_BIT_STRING:
        unused = payload[0]
        bits = []
        for byte in payload[1:]:
            for shift in range(7, -1, -1):
                bits.append((byte >> shift) & 1)
        if unused:
            bits = bits[:-unused]
        return bits
    if tag == TAG_OBJECT_ID:
        # Four octets is one identifier. Longer is an object-list property,
        # which is a sequence of identifiers in one application tag.
        if len(payload) == 4:
            return struct.unpack(">I", payload)[0]
        return decode_object_identifier_list(payload)
    if tag == TAG_NULL:
        return None
    raise DecodeError("no decoder for application tag %d" % tag)


def decode_object_identifier_list(payload):
    """A list of object identifiers, as one application tag of 4n octets."""
    if len(payload) % 4:
        raise DecodeError("object identifier list is not a multiple of four octets")
    return [struct.unpack(">I", payload[offset:offset + 4])[0] for offset in range(0, len(payload), 4)]
