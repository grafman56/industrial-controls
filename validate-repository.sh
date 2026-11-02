#!/usr/bin/env bash
# Static repository checks. Nothing here starts a lab or changes a container.
#
# The lab list comes from labs.toml, so adding a lab does not mean editing
# this file. Run it from anywhere; it changes to its own directory.
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$repo_dir"

echo "== manifest checks =="
# Standard library only, so this part runs on a host with no Python packages.
./labctl check

echo
echo "== topology checks =="
python3 - <<'PY'
from pathlib import Path
import tomllib

try:
    import yaml
except ModuleNotFoundError:
    raise SystemExit(
        "PyYAML is required for the topology checks.\n"
        "Install it with: python3 -m pip install -r requirements.txt\n"
        "The manifest checks run without it: ./labctl check"
    )

labs = tomllib.load(open("labs.toml", "rb"))["labs"]

# Every containerlab lab in the manifest, in name order, so the output is
# stable.
topologies = [
    Path(lab["dir"]) / lab["topology"]
    for _name, lab in sorted(labs.items())
    if lab.get("driver", "containerlab") == "containerlab"
]

for topology_path in topologies:
    with topology_path.open() as stream:
        topology = yaml.safe_load(stream)

    nodes = topology["topology"]["nodes"]
    endpoints = set()
    # A topology needs no explicit link: every node also joins the management
    # network. Only check the links that are declared.
    for link in topology["topology"].get("links", []):
        for endpoint in link["endpoints"]:
            node, _, _interface = endpoint.partition(":")
            if node not in nodes:
                raise SystemExit(f"{topology_path}: link references unknown node {node}")
            if endpoint in endpoints:
                raise SystemExit(f"{topology_path}: endpoint reused by multiple links: {endpoint}")
            endpoints.add(endpoint)

    for node_name, node in nodes.items():
        for binding in node.get("binds", []):
            source = binding.split(":", 1)[0]
            if source == f"runtime/{node_name}":
                continue
            source_path = topology_path.parent / source
            # Directories are legitimate bind sources, so check existence,
            # not file-ness.
            if not source_path.exists():
                raise SystemExit(
                    f"{topology_path}: {node_name} bind source missing: {source_path}"
                )

    print(f"PASS: {topology_path}")
PY

echo
echo "== unit tests =="
if [ -d tests ]; then
  python3 -m unittest discover -s tests -v
else
  echo "no tests directory"
fi

echo
echo "== PLCopen programs =="
if [ -d plc ]; then
  python3 tools/plcopen.py lint plc/*.xml --quiet
else
  echo "no plc directory"
fi

echo
echo "== shell syntax =="
# Every shell script in the repository, so a new lab cannot skip this check.
# The repository-level ./labctl is Python, not shell.
while IFS= read -r script; do
  bash -n "$script"
  echo "PASS: bash syntax $script"
done < <(
  find . -path ./.git -prune -o -name '*.sh' -print
)

echo
echo "PASS: repository static validation"
