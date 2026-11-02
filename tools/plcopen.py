#!/usr/bin/env python3
"""Check IEC 61131-3 programs in PLCopen TC6 XML before you import them.

A PLCopen file is a plain XML document, so most mistakes in it are visible
without a PLC: a contact that names an undeclared variable, a connection that
points at a node that does not exist, a structured text body that is empty.

This tool checks that class of mistake. It does not compile the program. A
compiler catches the rest.

Usage:

    python3 tools/plcopen.py lint plc/*.xml
    python3 tools/plcopen.py lint plc/level_control_ld.xml --quiet

Exit code 0 means no errors. Warnings do not change the exit code.
"""

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PLCOPEN_NS = "http://www.plcopen.org/xml/tc6_0201"
XHTML_NS = "http://www.w3.org/1999/xhtml"

GRAPHICAL_LANGUAGES = ("LD", "FBD", "SFC")
TEXT_LANGUAGES = ("ST", "IL")
ALL_LANGUAGES = GRAPHICAL_LANGUAGES + TEXT_LANGUAGES


class Problem:
    """One finding, tied to a file and a place inside it."""

    def __init__(self, level, where, message):
        self.level = level
        self.where = where
        self.message = message

    def __str__(self):
        return "%s: %s: %s" % (self.level, self.where, self.message)


class Report:
    def __init__(self, label):
        self.label = label
        self.problems = []
        self.languages = []
        self.pous = []

    def error(self, where, message):
        self.problems.append(Problem("error", where, message))

    def warning(self, where, message):
        self.problems.append(Problem("warning", where, message))

    @property
    def errors(self):
        return [p for p in self.problems if p.level == "error"]

    @property
    def warnings(self):
        return [p for p in self.problems if p.level == "warning"]

    @property
    def ok(self):
        return not self.errors


def tag(element):
    """Local element name, without the namespace."""
    return element.tag.rsplit("}", 1)[-1]


def children(element, name):
    return [child for child in element if tag(child) == name]


def child(element, name):
    found = children(element, name)
    return found[0] if found else None


def load(path):
    """Parse the file and return the root element."""
    return ET.parse(str(path)).getroot()


# ---------------------------------------------------------------------------
# What a POU declares and what it uses
# ---------------------------------------------------------------------------


def declared_variables(pou):
    """Every variable the POU declares, by name, with its type name."""
    interface = child(pou, "interface")
    declared = {}
    if interface is None:
        return declared
    for block_name in ("inputVars", "outputVars", "inOutVars", "localVars",
                       "tempVars", "externalVars", "globalVars"):
        block = child(interface, block_name)
        if block is None:
            continue
        for variable in children(block, "variable"):
            name = variable.get("name")
            if not name:
                continue
            type_element = child(variable, "type")
            type_name = tag(list(type_element)[0]) if type_element is not None and len(type_element) else "?"
            declared[name] = type_name
    return declared


def body_of(pou):
    body = child(pou, "body")
    return body


def body_language(pou):
    body = body_of(pou)
    if body is None:
        return None
    for element in body:
        return tag(element)
    return None


def local_ids(body):
    """Every element that carries a localId, by id."""
    found = {}
    for element in body.iter():
        local_id = element.get("localId")
        if local_id is not None:
            found[local_id] = tag(element)
    return found


def referenced_ids(body):
    """Every refLocalId value used anywhere in the body."""
    ids = []
    for element in body.iter():
        if tag(element) != "connection":
            continue
        value = element.get("refLocalId")
        if value is not None:
            ids.append(value)
    return ids


def graphical_variable_refs(body):
    """Variables named by contacts, coils and input variables."""
    names = []
    for element in body.iter():
        name = tag(element)
        if name in ("contact", "coil"):
            variable = child(element, "variable")
            if variable is not None and variable.text:
                names.append(variable.text.strip())
        elif name == "inVariable":
            expression = child(element, "expression")
            if expression is not None and expression.text:
                names.append(expression.text.strip())
    return names


def body_text(body, language):
    """The program text of a text language body."""
    block = child(body, language)
    if block is None:
        return ""
    collected = []
    for element in block.iter():
        if element.text and tag(element) == "p":
            collected.append(element.text)
        elif tag(element) == "p" and len(element) and element[0].text:
            collected.append(element[0].text)
    return "\n".join(collected).strip()


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_root(root, label):
    report = Report(label)

    if tag(root) != "project":
        report.error(label, "root element is %s, expected project" % tag(root))
        return report
    if not root.tag.startswith("{%s}" % PLCOPEN_NS):
        report.error(
            label,
            "namespace is not %s, so a PLCopen tool will not read the file" % PLCOPEN_NS,
        )

    types = child(root, "types")
    pous = child(types, "pous") if types is not None else None
    pou_elements = children(pous, "pou") if pous is not None else []
    if not pou_elements:
        report.error(label, "no POU in the file")
        return report

    for pou in pou_elements:
        check_pou(pou, report)

    return report


def check_pou(pou, report):
    name = pou.get("name", "<unnamed>")
    report.pous.append(name)
    if not pou.get("pouType"):
        report.error(name, "pouType is missing")

    language = body_language(pou)
    if language is None:
        report.error(name, "body is empty or missing")
        return
    if language not in ALL_LANGUAGES:
        report.error(name, "body language %s is not one of %s" % (language, ", ".join(ALL_LANGUAGES)))
        return
    report.languages.append(language)

    declared = declared_variables(pou)
    body = body_of(pou)

    if language in TEXT_LANGUAGES:
        text = body_text(body, language)
        if not text:
            report.error(name, "%s body has no text" % language)
            return
        for variable in sorted(declared):
            if not re.search(r"\b%s\b" % re.escape(variable), text):
                report.warning(name, "variable %r is declared but not used" % variable)
        return

    if language == "LD":
        ladder = child(body, "LD")
        if ladder is None:
            report.error(name, "body declares LD but holds no LD element")
            return
        check_ladder(ladder, declared, name, report)


def check_ladder(body, declared, name, report):
    ids = local_ids(body)
    raw_ids = [element.get("localId") for element in body.iter() if element.get("localId") is not None]
    duplicates = sorted({value for value in raw_ids if raw_ids.count(value) > 1})
    for duplicate in duplicates:
        report.error(name, "localId %s is used more than once" % duplicate)

    for referenced in referenced_ids(body):
        if referenced not in ids:
            report.error(name, "a connection points at localId %s, which does not exist" % referenced)

    for element_name in ("leftPowerRail", "rightPowerRail"):
        if not children(body, element_name):
            report.error(name, "ladder body has no %s" % element_name)

    used = graphical_variable_refs(body)
    for variable in used:
        if variable not in declared:
            report.error(name, "variable %r is used but not declared" % variable)
    for variable in sorted(set(declared) - set(used)):
        report.warning(name, "variable %r is declared but not used" % variable)

    for contact in children(body, "contact") + children(body, "coil"):
        if child(contact, "connectionPointIn") is None:
            report.error(
                name,
                "%s %s has no connectionPointIn" % (tag(contact), contact.get("localId", "?")),
            )
        if child(contact, "variable") is None:
            report.error(
                name,
                "%s %s names no variable" % (tag(contact), contact.get("localId", "?")),
            )


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def lint_paths(paths, quiet=False):
    reports = []
    for path in paths:
        path = Path(path)
        try:
            root = load(path)
        except ET.ParseError as error:
            report = Report(str(path))
            report.error(str(path), "not well formed XML: %s" % error)
            reports.append(report)
            continue
        reports.append(check_root(root, str(path)))

    for report in reports:
        if not quiet:
            languages = ", ".join(report.languages) if report.languages else "none"
            print("%s: POU %s, language %s" % (report.label, ", ".join(report.pous) or "none", languages))
        for problem in report.problems:
            print(" %s" % problem)

    errors = sum(len(report.errors) for report in reports)
    warnings = sum(len(report.warnings) for report in reports)
    print("%d file(s), %d error(s), %d warning(s)" % (len(reports), errors, warnings))
    return 0 if errors == 0 else 1


def main(argv):
    parser = argparse.ArgumentParser(description="Check PLCopen TC6 XML programs.")
    sub = parser.add_subparsers(dest="command", required=True)
    lint = sub.add_parser("lint", help="check one or more PLCopen files")
    lint.add_argument("paths", nargs="+")
    lint.add_argument("--quiet", action="store_true", help="print only the findings")
    args = parser.parse_args(argv)

    if args.command == "lint":
        return lint_paths(args.paths, quiet=args.quiet)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
