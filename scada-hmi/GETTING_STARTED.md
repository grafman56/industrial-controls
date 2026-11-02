# Start here: operator screen and historian

You need the lab deployed. On the lab host, from the repository root:

```bash
./labctl up scada-hmi
```

Then forward the four ports to your PC:

```bash
ssh -L 1881:127.0.0.1:1881 -L 3000:127.0.0.1:3000 \
    -L 8086:127.0.0.1:8086 -L 8443:127.0.0.1:8443 \
    <user>@<lab-host>
```

Open `http://127.0.0.1:1881` for the HMI and `http://127.0.0.1:3000` for
Grafana. Grafana is configured for anonymous read access. FUXA opens its
project editor directly. Both are reachable on the lab host loopback only.

## 1. Connect the HMI to the tank

In FUXA, add a device and point it at the process:

| Setting | Value |
|---|---|
| Type | Modbus TCP |
| Address | 172.111.20.10 |
| Port | 5020 |
| Unit id | 1 |

Do not point it at the PLC. The PLC publishes no Modbus server in this lab. The
tank owns the process values.

Two tags carry the process:

| Tag | Modbus type | Address | Meaning |
|---|---|---|---|
| level | Holding register | 0 | Level, 0 to 100 percent |
| pump | Coil | 0 | 1 means the pump runs |

The tank answers one register per request. A client that asks for ten values in
one request gets an exception code back, on purpose, so that a wrong request is
visible instead of silently zero.

Confirm the values before you build a screen. If the level does not change,
the device is not connected, and a screen will only hide that.

## 2. Build the operator screen

Build three items:

1. A numeric display of `level`, labelled with the unit and the range.
2. A switch for `pump` that shows the command, not the feedback. There is no
   feedback in this lab, and that gap is the lesson.
3. An alarm on high level at 90 percent, with a timestamp.

Then break it on purpose: write the coil to 0 while the level is below 30 and
watch the level fall to 0. Write down what an operator would have seen.

## 3. Read the historian

The poller writes one point per second. Grafana shows the last 15 minutes from
the provisioned dashboard. Query the same data directly:

```bash
curl -sS -X POST "http://127.0.0.1:8086/api/v2/query?org=lab" \
  -H "Authorization: Token lab-token-not-a-secret" \
  -H "Accept: application/csv" \
  -H "Content-Type: application/vnd.flux" \
  --data 'from(bucket:"process")
    |> range(start: -10m)
    |> filter(fn: (r) => r._measurement == "process")
    |> last()'
```

Answer these with the output, not with a screenshot:

- What was the level three minutes ago, and when exactly was that?
- How many samples arrived in the last ten minutes? A gap means the poller
  stopped, and a gap is a fact worth alarming on.
- Does the pump field ever disagree with the level trend?

## 4. The argument drill

The point of a historian is to settle a dispute. Do this:

1. Note the time. Write the pump coil to 1 by hand, from your own client.
2. Wait two minutes. Write it back to 0.
3. Query the historian for the pump field over that window.
4. Write the incident note: what changed, at what second, and what the data
   proves and does not prove.

The historian proves the value changed. It does not prove who changed it. That
second question needs the network capture, and it is the reason the
`ot-visibility` lab exists.

## If it does not work

- `docker exec clab-scada-hmi-poller python /app/poller.py --once` prints the
  Modbus or HTTP error that the loop swallowed.
- `./labctl verify scada-hmi` re-runs the whole check.
- A dashboard with an empty panel is usually a Grafana datasource problem. Open
  Connections, then the InfluxDB datasource, then Save and test. The token is
  `lab-token-not-a-secret`, the org is `lab`, the default bucket is `process`.
