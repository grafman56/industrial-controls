#!/usr/bin/env bash
# Verify the SCADA lab: the HMI, the PLC editor, the historian and one stored
# point. Nothing here changes the process.
set -euo pipefail

cd "$(dirname "$0")"

wait_http() {
  name=$1
  url=$2
  for _ in $(seq 1 45); do
    if curl -fsSk -o /dev/null "$url"; then
      echo "PASS: $name answers on $url"
      return 0
    fi
    sleep 2
  done
  echo "FAIL: $name did not answer on $url within 90 s" >&2
  return 1
}

wait_tcp() {
  name=$1
  host=$2
  port=$3
  for _ in $(seq 1 45); do
    if docker exec clab-scada-hmi-poller python -c \
      "import socket; socket.create_connection(('$host', $port), 3).close()" 2>/dev/null; then
      echo "PASS: $name accepts a connection on $host:$port"
      return 0
    fi
    sleep 2
  done
  echo "FAIL: $name did not accept a connection on $host:$port within 90 s" >&2
  return 1
}

wait_http "historian" "http://127.0.0.1:8086/health"
wait_http "hmi" "http://127.0.0.1:1881/"
wait_http "dashboard" "http://127.0.0.1:3000/api/health"
wait_tcp "tank modbus" "172.111.20.10" "5020"
wait_tcp "plc editor api" "172.111.20.11" "8443"

# The poller reads the tank and writes one point. This fails if either the
# Modbus read or the historian write is broken.
docker exec clab-scada-hmi-poller python /app/poller.py --once

# The point must be queryable, not only written.
query='from(bucket:"process") |> range(start: -10m) |> filter(fn: (r) => r._measurement == "process" and r._field == "level_percent") |> last()'
result=$(curl -fsS -X POST "http://127.0.0.1:8086/api/v2/query?org=lab" \
  -H "Authorization: Token lab-token-not-a-secret" \
  -H "Accept: application/csv" \
  -H "Content-Type: application/vnd.flux" \
  --data "$query")

if ! grep -q "level_percent" <<<"$result"; then
  echo "FAIL: the historian returned no level_percent point" >&2
  echo "$result" >&2
  exit 1
fi
echo "PASS: the historian returns a stored level point"
