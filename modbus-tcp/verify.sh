#!/usr/bin/env bash
set -euo pipefail

# The simulator needs a moment after deploy, so retry the first check.
for attempt in 1 2 3 4 5 6; do
  docker exec clab-modbus-tcp-client python /lab/client.py 192.0.2.1 && break
  [ "$attempt" -eq 6 ] && exit 1
  sleep 3
done
docker exec clab-modbus-tcp-client python /lab/tank_plant_check.py 172.100.120.10
