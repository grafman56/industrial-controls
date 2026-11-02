#!/usr/bin/env python3
"""Two BACnet devices: an air handling unit and a VAV box.

    python3 ahu.py --profile ahu --instance 1001 --verbose
    python3 ahu.py --profile vav --instance 1002

The point list is the interesting part. It is what a BMS engineer sees in a
point schedule, and every entry is an object a client can read by name.

    analog-input,1   supply air temperature      degC
    analog-input,2   return air temperature      degC
    analog-output,1  chilled water valve         percent
    binary-output,1  supply fan command          -
    binary-input,1   fan status                  -
    analog-value,1   supply air setpoint         degC
"""

import argparse
import sys

from bacnet_codec import (
    OBJECT_ANALOG_INPUT,
    OBJECT_ANALOG_OUTPUT,
    OBJECT_ANALOG_VALUE,
    OBJECT_BINARY_INPUT,
    OBJECT_BINARY_OUTPUT,
    UNITS_DEGREES_CELSIUS,
    UNITS_NO_UNITS,
    UNITS_PASCALS,
    UNITS_PERCENT,
)
from bacnet_device import Device, DeviceServer, Point

VENDOR_ID = 999
VENDOR_NAME = "Industrial Controls Lab"
MODEL_NAME = "LAB-AHU-1"


def ahu_points():
    """An air handling unit: sensors in, valve and fan out."""
    return [
        Point(OBJECT_ANALOG_INPUT, 1, "supply-air-temp", 13.4, UNITS_DEGREES_CELSIUS, "Supply air temperature"),
        Point(OBJECT_ANALOG_INPUT, 2, "return-air-temp", 22.8, UNITS_DEGREES_CELSIUS, "Return air temperature"),
        Point(OBJECT_ANALOG_INPUT, 3, "mixed-air-temp", 18.1, UNITS_DEGREES_CELSIUS, "Mixed air temperature"),
        Point(OBJECT_ANALOG_INPUT, 4, "duct-static-pressure", 312.0, UNITS_PASCALS, "Supply duct static pressure"),
        Point(OBJECT_ANALOG_INPUT, 5, "filter-differential-pressure", 48.0, UNITS_PASCALS, "Filter differential pressure"),
        Point(OBJECT_ANALOG_OUTPUT, 1, "chilled-water-valve", 42.0, UNITS_PERCENT, "Chilled water valve position"),
        Point(OBJECT_ANALOG_OUTPUT, 2, "fan-speed", 68.0, UNITS_PERCENT, "Supply fan speed command"),
        Point(OBJECT_ANALOG_VALUE, 1, "supply-air-setpoint", 13.0, UNITS_DEGREES_CELSIUS, "Supply air temperature setpoint"),
        Point(OBJECT_ANALOG_VALUE, 2, "static-pressure-setpoint", 300.0, UNITS_PASCALS, "Duct static pressure setpoint"),
        Point(OBJECT_BINARY_INPUT, 1, "fan-status", True, UNITS_NO_UNITS, "Fan proof of operation"),
        Point(OBJECT_BINARY_INPUT, 2, "filter-alarm", False, UNITS_NO_UNITS, "Filter differential pressure switch"),
        Point(OBJECT_BINARY_OUTPUT, 1, "supply-fan-command", True, UNITS_NO_UNITS, "Supply fan start command"),
    ]


def vav_points():
    """A VAV terminal box: zone sensor, damper, and a reheat valve."""
    return [
        Point(OBJECT_ANALOG_INPUT, 1, "zone-temp", 21.6, UNITS_DEGREES_CELSIUS, "Zone air temperature"),
        Point(OBJECT_ANALOG_INPUT, 2, "airflow", 34.0, UNITS_PERCENT, "Airflow as a percentage of design"),
        Point(OBJECT_ANALOG_OUTPUT, 1, "damper-position", 34.0, UNITS_PERCENT, "Damper position"),
        Point(OBJECT_ANALOG_OUTPUT, 2, "reheat-valve", 0.0, UNITS_PERCENT, "Hot water reheat valve position"),
        Point(OBJECT_ANALOG_VALUE, 1, "zone-temp-setpoint", 21.0, UNITS_DEGREES_CELSIUS, "Zone temperature setpoint"),
        Point(OBJECT_BINARY_INPUT, 1, "zone-occupied", True, UNITS_NO_UNITS, "Occupancy from the schedule"),
        Point(OBJECT_BINARY_OUTPUT, 1, "reheat-enable", False, UNITS_NO_UNITS, "Reheat enable"),
    ]


PROFILES = {
    "ahu": ("AHU-1", ahu_points),
    "vav": ("VAV-1", vav_points),
}


def build(profile, instance):
    try:
        name, points = PROFILES[profile]
    except KeyError:
        raise SystemExit("unknown profile %r, choose ahu or vav" % profile)
    return Device(instance, name, VENDOR_NAME, VENDOR_ID, MODEL_NAME, points())


def main(argv):
    parser = argparse.ArgumentParser(description="A BACnet/IP device on UDP 47808.")
    parser.add_argument("--profile", default="ahu", choices=sorted(PROFILES))
    parser.add_argument("--instance", type=int, default=1001)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=47808)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    device = build(args.profile, args.instance)
    print(
        "device %s instance %d, %d objects"
        % (device.name, device.instance, len(device.object_list())),
        flush=True,
    )
    DeviceServer(device, bind=args.bind, port=args.port, verbose=args.verbose).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
