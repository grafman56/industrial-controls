"""Tests for the BACnet/IP codec, the device model, and the point reader.

What these tests prove: the frame layout this lab produces matches the layout
the codec reads, the device answers the services it claims, and a client can
discover it and read every point.

What they do not prove: interoperation with a vendor device. There is no vendor
device in this lab, so the bytes are checked against the layout the code says it
implements, not against a BTL test.
"""

import importlib.machinery
import importlib.util
import struct
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABDIR = ROOT / "bacnet-ip"


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


codec = load("bacnet_codec", LABDIR / "bacnet_codec.py")
device_module = load("bacnet_device", LABDIR / "bacnet_device.py")
ahu = load("bacnet_ahu", LABDIR / "ahu.py")
supervisor = load("bacnet_supervisor", LABDIR / "supervisor.py")


def decode_encoded(encoded):
    """Decode one complete application-tagged value, tag byte included."""
    number, payload, _offset, _context = codec.read_tagged(encoded, 0)
    return codec.decode_value(number, payload)


class FrameLayoutTests(unittest.TestCase):
    def test_who_is_is_the_broadcast_frame(self):
        frame = codec.who_is()
        self.assertEqual(frame, b"\x81\x0b\x00\x08\x01\x00\x10\x08")

    def test_bvlc_length_covers_the_whole_frame(self):
        frame = codec.read_property(codec.OBJECT_ANALOG_INPUT, 1, codec.PROP_PRESENT_VALUE)
        declared = struct.unpack(">H", frame[2:4])[0]
        self.assertEqual(declared, len(frame))
        self.assertEqual(frame[0], 0x81)

    def test_read_property_carries_the_service_and_the_object(self):
        frame = codec.read_property(codec.OBJECT_ANALOG_INPUT, 1, codec.PROP_PRESENT_VALUE, invoke_id=7)
        self.assertEqual(frame[1], codec.BVLC_ORIGINAL_UNICAST)
        self.assertEqual(frame[4], 0x01)
        self.assertEqual(frame[5], 0x04, "a confirmed request expects a reply")
        self.assertEqual(frame[6], codec.PDU_CONFIRMED_REQUEST)
        self.assertEqual(frame[7], 0x05)
        self.assertEqual(frame[8], 7, "invoke id")
        self.assertEqual(frame[9], codec.SERVICE_READ_PROPERTY)
        self.assertEqual(frame[10], 0x0C, "context tag 0, four octets")
        object_id = struct.unpack(">I", frame[11:15])[0]
        self.assertEqual(codec.split_object_identifier(object_id), (codec.OBJECT_ANALOG_INPUT, 1))
        self.assertEqual(frame[15], 0x19, "context tag 1, one octet")
        self.assertEqual(frame[16], codec.PROP_PRESENT_VALUE)

    def test_read_property_multiple_opens_and_closes_the_property_list(self):
        frame = codec.read_property_multiple(
            codec.OBJECT_DEVICE, 1001, [codec.PROP_OBJECT_NAME, codec.PROP_PRESENT_VALUE]
        )
        self.assertEqual(frame[9], codec.SERVICE_READ_PROPERTY_MULTIPLE)
        self.assertIn(b"\x1e", frame, "opening tag 1")
        self.assertIn(b"\x1f", frame, "closing tag 1")

    def test_declared_length_that_disagrees_is_rejected(self):
        frame = bytearray(codec.who_is())
        frame[3] = frame[3] + 1
        with self.assertRaises(codec.DecodeError):
            codec.decode_bvlc(bytes(frame))

    def test_a_frame_that_is_not_bacnet_ip_is_rejected(self):
        with self.assertRaises(codec.DecodeError):
            codec.decode_bvlc(b"\x82\x0a\x00\x08\x01\x00\x10\x08")

    def test_a_routed_npdu_is_rejected_rather_than_misread(self):
        frame = bytearray(codec.who_is())
        frame[5] = 0x20
        with self.assertRaises(codec.DecodeError):
            codec.decode_bvlc(bytes(frame))


class TagTests(unittest.TestCase):
    def test_small_application_tag_holds_the_length(self):
        encoded = codec.encode_value(codec.TAG_REAL, 230.0)
        self.assertEqual(encoded[0], 0x44)
        self.assertEqual(codec.decode_value(codec.TAG_REAL, encoded[1:]), 230.0)

    def test_character_string_holds_its_charset_first(self):
        encoded = codec.encode_value(codec.TAG_CHARACTER_STRING, "AHU")
        self.assertEqual(encoded[0], 0x74, "tag 7, four octets: charset plus three characters")
        self.assertEqual(encoded[1], 0x00, "charset 0 is UTF-8")
        self.assertEqual(codec.decode_value(codec.TAG_CHARACTER_STRING, encoded[1:]), "AHU")

    def test_a_longer_string_carries_a_length_octet(self):
        encoded = codec.encode_value(codec.TAG_CHARACTER_STRING, "supply-air-temp")
        self.assertEqual(encoded[0], 0x75, "tag 7, length in the next octet")
        self.assertEqual(encoded[1], len("supply-air-temp") + 1)
        self.assertEqual(
            codec.decode_value(codec.TAG_CHARACTER_STRING, encoded[2:]), "supply-air-temp"
        )

    def test_bit_string_reports_its_unused_bits(self):
        encoded = codec.encode_value(codec.TAG_BIT_STRING, [0, 0, 0, 0])
        self.assertEqual(encoded[0], 0x82)
        self.assertEqual(encoded[1], 4, "four bits unused in the last octet")
        self.assertEqual(codec.decode_value(codec.TAG_BIT_STRING, encoded[1:]), [0, 0, 0, 0])

    def test_object_identifier_splits_into_type_and_instance(self):
        value = codec.object_identifier(codec.OBJECT_ANALOG_INPUT, 7)
        self.assertEqual(codec.split_object_identifier(value), (codec.OBJECT_ANALOG_INPUT, 7))
        self.assertEqual(codec.object_name(codec.OBJECT_ANALOG_INPUT, 7), "analog-input,7")

    def test_an_object_list_decodes_to_a_list_and_one_id_decodes_to_an_int(self):
        joined = b"".join([
            struct.pack(">I", codec.object_identifier(codec.OBJECT_DEVICE, 1001)),
            struct.pack(">I", codec.object_identifier(codec.OBJECT_ANALOG_INPUT, 1)),
        ])
        self.assertIsInstance(codec.decode_value(codec.TAG_OBJECT_ID, joined), list)
        single = codec.encode_value(codec.TAG_OBJECT_ID, codec.object_identifier(codec.OBJECT_DEVICE, 1001))
        self.assertIsInstance(codec.decode_value(codec.TAG_OBJECT_ID, single[1:]), int)

    def test_an_unsigned_uses_the_shortest_form_that_fits(self):
        self.assertEqual(codec.encode_value(codec.TAG_UNSIGNED, 5), b"\x21\x05")
        self.assertEqual(codec.encode_value(codec.TAG_UNSIGNED, 1476), b"\x22\x05\xc4")

    def test_a_negative_signed_value_keeps_its_sign(self):
        encoded = codec.encode_value(codec.TAG_SIGNED, -20)
        self.assertEqual(codec.decode_value(codec.TAG_SIGNED, encoded[1:]), -20)


class DeviceModelTests(unittest.TestCase):
    def setUp(self):
        self.device = ahu.build("ahu", 1001)

    def test_the_device_object_lists_itself_first(self):
        objects = self.device.object_list()
        self.assertEqual(objects[0], codec.object_identifier(codec.OBJECT_DEVICE, 1001))
        self.assertEqual(len(objects), 13)

    def test_a_point_answers_name_value_and_units(self):
        values = self.device.properties(codec.OBJECT_ANALOG_INPUT, 1)
        self.assertEqual(decode_encoded(values[codec.PROP_OBJECT_NAME]), "supply-air-temp")
        self.assertAlmostEqual(decode_encoded(values[codec.PROP_PRESENT_VALUE]), 13.4, places=2)
        self.assertEqual(decode_encoded(values[codec.PROP_UNITS]), codec.UNITS_DEGREES_CELSIUS)

    def test_a_binary_point_carries_an_enumerated_value(self):
        values = self.device.properties(codec.OBJECT_BINARY_INPUT, 1)
        self.assertEqual(values[codec.PROP_PRESENT_VALUE][0] >> 4, codec.TAG_ENUMERATED)
        self.assertEqual(decode_encoded(values[codec.PROP_PRESENT_VALUE]), 1)

    def test_an_unknown_point_is_an_unknown_object(self):
        with self.assertRaises(device_module.UnknownObject):
            self.device.properties(codec.OBJECT_ANALOG_INPUT, 99)

    def test_an_unknown_property_is_an_unknown_property(self):
        with self.assertRaises(device_module.UnknownProperty):
            self.device.property_value(codec.OBJECT_ANALOG_INPUT, 1, 999)

    def test_a_new_value_is_visible_on_the_next_read(self):
        self.device.set_value(codec.OBJECT_ANALOG_OUTPUT, 1, 55.0)
        values = self.device.properties(codec.OBJECT_ANALOG_OUTPUT, 1)
        self.assertAlmostEqual(decode_encoded(values[codec.PROP_PRESENT_VALUE]), 55.0, places=2)

    def test_two_points_cannot_share_an_identifier(self):
        with self.assertRaises(ValueError):
            device_module.Device(1010, "BAD", "lab", 1, "x", ahu.ahu_points() + ahu.ahu_points()[:1])


class ServerFrameTests(unittest.TestCase):
    """The request and reply logic, one frame at a time, with no socket."""

    def setUp(self):
        self.device = ahu.build("ahu", 1001)
        self.server = device_module.DeviceServer(self.device)

    def test_who_is_is_answered_with_i_am(self):
        reply = self.server.handle(codec.who_is())
        self.assertIsNotNone(reply)
        frame = codec.decode_bvlc(reply)
        self.assertEqual(frame.apdu[0] & 0xF0, codec.PDU_UNCONFIRMED_REQUEST)
        self.assertEqual(frame.apdu[1], codec.SERVICE_I_AM)
        instance, max_apdu, segmentation = supervisor.Client.parse_i_am(frame.apdu[2:])
        self.assertEqual(instance, 1001)
        self.assertEqual(max_apdu, 1476)
        self.assertEqual(segmentation, 3)

    def test_read_property_is_answered_with_a_complex_ack(self):
        reply = self.server.handle(
            codec.read_property(codec.OBJECT_ANALOG_INPUT, 1, codec.PROP_PRESENT_VALUE, invoke_id=3)
        )
        object_id, prop, value = supervisor.parse_read_property_ack(codec.decode_bvlc(reply).apdu)
        self.assertEqual(codec.split_object_identifier(object_id), (codec.OBJECT_ANALOG_INPUT, 1))
        self.assertEqual(prop, codec.PROP_PRESENT_VALUE)
        self.assertAlmostEqual(value, 13.4, places=2)

    def test_read_property_of_an_unknown_object_is_an_error(self):
        reply = self.server.handle(
            codec.read_property(codec.OBJECT_ANALOG_INPUT, 99, codec.PROP_PRESENT_VALUE, invoke_id=4)
        )
        apdu = codec.decode_bvlc(reply).apdu
        self.assertEqual(apdu[0], codec.PDU_ERROR)
        self.assertEqual(apdu[1], 4, "the invoke id comes back")
        self.assertEqual((apdu[3], apdu[4]), (1, 2), "error class object, code unknown-object")
        self.assertEqual(self.server.unknown_object, 1)

    def test_read_property_of_an_unknown_property_is_an_error(self):
        reply = self.server.handle(codec.read_property(codec.OBJECT_ANALOG_INPUT, 1, 200, invoke_id=5))
        apdu = codec.decode_bvlc(reply).apdu
        self.assertEqual((apdu[3], apdu[4]), (2, 2), "error class property, code unknown-property")
        self.assertEqual(self.server.unknown_property, 1)

    def test_an_unsupported_service_is_aborted_with_the_invoke_id(self):
        frame = codec.bvlc(
            codec.BVLC_ORIGINAL_UNICAST,
            codec.npdu(codec.confirmed_request(9, 0x0F, b"")),
        )
        apdu = codec.decode_bvlc(self.server.handle(frame)).apdu
        self.assertEqual(apdu[0] & 0xF0, codec.PDU_ABORT)
        self.assertEqual(apdu[1], 9)
        self.assertEqual(apdu[2], 0x0F)

    def test_read_property_multiple_returns_every_requested_property(self):
        reply = self.server.handle(
            codec.read_property_multiple(
                codec.OBJECT_ANALOG_INPUT,
                1,
                [codec.PROP_OBJECT_NAME, codec.PROP_PRESENT_VALUE, codec.PROP_UNITS],
                invoke_id=6,
            )
        )
        values = supervisor.parse_read_property_multiple_ack(codec.decode_bvlc(reply).apdu)
        object_id = codec.object_identifier(codec.OBJECT_ANALOG_INPUT, 1)
        self.assertEqual(values[(object_id, codec.PROP_OBJECT_NAME)], "supply-air-temp")
        self.assertAlmostEqual(values[(object_id, codec.PROP_PRESENT_VALUE)], 13.4, places=2)
        self.assertEqual(values[(object_id, codec.PROP_UNITS)], codec.UNITS_DEGREES_CELSIUS)

    def test_a_truncated_frame_is_dropped_without_an_exception(self):
        self.assertIsNone(self.server.handle(b"\x81\x0a\x00"))
        self.assertIsNone(self.server.handle(b""))


class DiscoveryAndReadTests(unittest.TestCase):
    """A real UDP socket, a real client, and a real read of every point."""

    def setUp(self):
        self.device = ahu.build("ahu", 1001)
        self.server = device_module.DeviceServer(self.device, bind="127.0.0.1", port=0)
        self.port = self.server.open()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.server.serve_forever, args=(self.stop,), daemon=True)
        self.thread.start()
        # Loopback only: the test never broadcasts onto a real network.
        self.client = supervisor.Client(broadcast="127.0.0.1", port=self.port)

    def tearDown(self):
        self.stop.set()
        self.thread.join(timeout=3)
        self.client.close()
        self.server.close()

    def test_discovery_finds_the_device_and_its_address(self):
        devices = self.client.discover(0.5, targets=["127.0.0.1"])
        self.assertEqual(list(devices), [1001])
        self.assertEqual(devices[1001], ("127.0.0.1", self.port))

    def test_every_point_is_read_with_name_value_and_units(self):
        devices = self.client.discover(0.5, targets=["127.0.0.1"])
        rows = supervisor.read_points(self.client, devices[1001], 1001)
        self.assertEqual(len(rows), 12)
        by_object = {row["object"]: row for row in rows}
        supply = by_object["analog-input,1"]
        self.assertEqual(supply["name"], "supply-air-temp")
        self.assertAlmostEqual(supply["value"], 13.4, places=2)
        self.assertEqual(supply["units"], codec.UNITS_DEGREES_CELSIUS)
        self.assertEqual(by_object["binary-output,1"]["value"], 1)

    def test_the_object_list_is_how_the_client_finds_the_points(self):
        devices = self.client.discover(0.5, targets=["127.0.0.1"])
        _object_id, _prop, objects = self.client.read_property(
            devices[1001], codec.OBJECT_DEVICE, 1001, codec.PROP_OBJECT_LIST
        )
        self.assertEqual(len(objects), 13)
        self.assertIn(codec.object_identifier(codec.OBJECT_ANALOG_INPUT, 5), objects)

    def test_a_second_device_profile_answers_with_its_own_points(self):
        vav = ahu.build("vav", 1002)
        other = device_module.DeviceServer(vav, bind="127.0.0.1", port=0)
        port = other.open()
        stop = threading.Event()
        thread = threading.Thread(target=other.serve_forever, args=(stop,), daemon=True)
        thread.start()
        try:
            client = supervisor.Client(broadcast="127.0.0.1", port=port)
            try:
                devices = client.discover(0.5, targets=["127.0.0.1"])
                rows = supervisor.read_points(client, devices[1002], 1002)
                self.assertEqual(len(rows), 7)
                self.assertEqual(
                    {row["object"] for row in rows},
                    {
                        "analog-input,1",
                        "analog-input,2",
                        "analog-output,1",
                        "analog-output,2",
                        "analog-value,1",
                        "binary-input,1",
                        "binary-output,1",
                    },
                )
            finally:
                client.close()
        finally:
            stop.set()
            thread.join(timeout=3)
            other.close()

    def test_the_formatted_row_names_the_units(self):
        row = {"object": "analog-input,1", "name": "supply-air-temp", "value": 13.4,
               "units": codec.UNITS_DEGREES_CELSIUS}
        self.assertIn("degC", supervisor.format_row(row))
        self.assertIn("13.40", supervisor.format_row(row))


if __name__ == "__main__":
    unittest.main()
