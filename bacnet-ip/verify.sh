#!/usr/bin/env bash
# Verify the deployed bacnet-ip lab.
#
# Runs on the lab host, against containers that are already up. Two checks:
# one from inside the lab network, and one through the published UDP port,
# which is the path a laptop tool would take.
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
lab=bacnet-ip

echo "== discovery and every point, from the supervisor container =="
output=$(docker exec "clab-${lab}-supervisor" python3 /lab/supervisor.py \
  --broadcast 172.111.30.255 --target 172.111.30.10 --target 172.111.30.11 --timeout 3)

printf '%s\n' "$output"

printf '%s\n' "$output" | grep -q "discovered 2 device(s)"
printf '%s\n' "$output" | grep -q "supply-air-temp"
printf '%s\n' "$output" | grep -q "zone-temp"

points=$(printf '%s\n' "$output" | grep -cE '(analog|binary)-(input|output|value),[0-9]+')
if [ "$points" -ne 19 ]; then
  echo "expected 19 points, read $points" >&2
  exit 1
fi

echo
echo "== a direct unicast read through the published port =="
# The repository's own client, run on the host, against the AHU only. A
# laptop BACnet tool can do the same; this keeps the check dependency-free.
python3 "${here}/supervisor.py" --broadcast 127.0.0.1 --target 127.0.0.1 --device 1001 --timeout 2 \
  | tee /tmp/bacnet-host-read.txt

grep -q "supply-air-temp" /tmp/bacnet-host-read.txt
grep -q "duct-static-pressure" /tmp/bacnet-host-read.txt

echo
echo "PASS: bacnet-ip verification"
