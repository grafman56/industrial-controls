"""Encode and decode power meter registers.

A meter does not send engineering values. It sends raw 16-bit registers, and
the manual says how to turn them into volts and amps. Three things go wrong in
the field, and this module exists so that each one is a test case:

1. Word order. A 32-bit value that spans two registers can be sent high word
   first or low word first. Vendors differ, and some send one order per
   register block.
2. Scaling. A current may arrive as amps times ten, or as a raw count with a
   ratio from the current transformer.
3. Type. A float32 that spans two registers is not a signed integer, and
   reading it as one gives a plausible but wrong number.

The register map lives in `registers.json` so the map is data, not code.
"""

import json
import struct
from pathlib import Path

HIGH_FIRST = "high_first"
LOW_FIRST = "low_first"


class Entry:
    """One measurement in the register map."""

    def __init__(self, raw):
        self.name = raw["name"]
        self.description = raw.get("description", "")
        self.address = int(raw["address"])
        self.kind = raw["type"]
        self.word_order = raw.get("word_order", HIGH_FIRST)
        self.scale = float(raw.get("scale", 1))
        self.unit = raw.get("unit", "")
        self.words = {"float32": 2, "uint32": 2, "int32": 2, "uint16": 1, "int16": 1}[self.kind]

    @property
    def last_address(self):
        return self.address + self.words - 1

    def __repr__(self):
        return "Entry(%s at %d, %s)" % (self.name, self.address, self.kind)


def load_map(path):
    """Read the register map and return entries in address order."""
    document = json.loads(Path(path).read_text())
    entries = [Entry(raw) for raw in document["registers"]]
    entries.sort(key=lambda entry: entry.address)
    _check_no_overlap(entries)
    return entries


def _check_no_overlap(entries):
    taken = {}
    for entry in entries:
        for address in range(entry.address, entry.last_address + 1):
            if address in taken:
                raise ValueError(
                    "%s and %s both claim register %d" % (taken[address], entry.name, address)
                )
            taken[address] = entry.name


def encode(entry, value):
    """Engineering value to raw 16-bit words."""
    if entry.kind == "float32":
        words = list(struct.unpack(">HH", struct.pack(">f", float(value))))
    elif entry.kind == "uint32":
        words = list(struct.unpack(">HH", struct.pack(">I", int(round(value / entry.scale)))))
    elif entry.kind == "int32":
        words = list(struct.unpack(">HH", struct.pack(">i", int(round(value / entry.scale)))))
    elif entry.kind == "uint16":
        words = [int(round(value / entry.scale)) & 0xFFFF]
    elif entry.kind == "int16":
        words = [struct.unpack(">H", struct.pack(">h", int(round(value / entry.scale))))[0]]
    else:
        raise ValueError("unknown type %r" % entry.kind)

    if len(words) == 2 and entry.word_order == LOW_FIRST:
        words.reverse()
    return words


def decode(entry, words):
    """Raw 16-bit words to an engineering value."""
    words = list(words)
    if len(words) != entry.words:
        raise ValueError("%s needs %d words, got %d" % (entry.name, entry.words, len(words)))
    if len(words) == 2 and entry.word_order == LOW_FIRST:
        words.reverse()

    if entry.kind == "float32":
        return struct.unpack(">f", struct.pack(">HH", *words))[0]
    if entry.kind == "uint32":
        return struct.unpack(">I", struct.pack(">HH", *words))[0] * entry.scale
    if entry.kind == "int32":
        return struct.unpack(">i", struct.pack(">HH", *words))[0] * entry.scale
    if entry.kind == "uint16":
        return words[0] * entry.scale
    if entry.kind == "int16":
        return struct.unpack(">h", struct.pack(">H", words[0]))[0] * entry.scale
    raise ValueError("unknown type %r" % entry.kind)


def decode_block(entries, registers, start, count):
    """Decode every measurement that fits fully inside one register read."""
    values = {}
    for entry in entries:
        if entry.address >= start and entry.last_address < start + count:
            offset = entry.address - start
            values[entry.name] = decode(entry, registers[offset:offset + entry.words])
    return values
