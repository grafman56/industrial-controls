# SCADA and HMI lab

An operator interface and a process historian over the tank process from the
`modbus-tcp` lab. Six containers, one question: can you see the process, and
can you prove what it did last night.

## What is in it

| Node | Address | Role |
|---|---|---|
| `tank` | 172.111.20.10 | Process model, Modbus/TCP server on 5020 |
| `plc` | 172.111.20.11 | OpenPLC Runtime v4.3.1, IEC 61131-3 execution |
| `hmi` | 172.111.20.20 | FUXA 1.3.5, browser HMI and SCADA |
| `poller` | 172.111.20.30 | Reads the tank every second, writes line protocol |
| `historian` | 172.111.20.31 | InfluxDB 2.7.12, bucket `process` |
| `dashboard` | 172.111.20.32 | Grafana 11.3.0, provisioned dashboard |

Published ports, all on host loopback only:

- `127.0.0.1:1881` FUXA
- `127.0.0.1:3000` Grafana
- `127.0.0.1:8086` InfluxDB API
- `127.0.0.1:8443` OpenPLC Editor API

## Lifecycle

Run this on the lab host, from the repository root:

```bash
./labctl up scada-hmi        # builds two images, deploys, runs verify.sh
./labctl down scada-hmi      # destroys only this topology
```

The `modbus-lab:3.12.1` image is built from `../modbus-tcp`, so this lab does
not depend on the other lab being deployed first. Both labs use the same image
tag and therefore the same build.

Memory: about 1.2 GB for the six containers. The `labs.toml` entry asks for
4096 MB free, so a 3 GB host refuses it in `doctor`.

## Study it

[GETTING_STARTED.md](GETTING_STARTED.md) is the exercise: connect FUXA to the
tank, build an operator screen, then query the historian for a fact.

## The credentials in this lab

The historian username, password and token are fixed values written in the
topology, for example `lab-token-not-a-secret`. They are not secrets. The
historian is reachable only from the lab bridge network, and its port is
published on host loopback. A fixed value keeps the lab reproducible and keeps
the Grafana datasource file in Git.

Do not copy that pattern to a lab that is reachable from the LAN.

## What is verified, and what is not

Verified at deploy time by `verify.sh`:

- the historian, HMI and dashboard answer
- the tank and the PLC accept a connection
- the poller performs a real Modbus read and a real historian write
- the historian returns the stored point on a Flux query

Not verified:

- the Grafana dashboard JSON. It is provisioned from
  `grafana/dashboards/tank.json` and is the first thing to check if a panel is
  empty. The datasource is provisioned with `uid: influxdb`, which the panels
  reference.
- the FUXA screens. FUXA stores its project in its own database inside the
  container, so a destroyed lab loses the screens by design. Build them again
  from the instructions in GETTING_STARTED.md.

## Fidelity

The historian records 1 s samples from a counter-driven model. A real plant
historian samples thousands of tags at 100 ms to 1 s, compresses deadbands and
keeps years of data. The pattern is the same; the scale is not.

The HMI reads the same register the PLC writes. That is the useful part: two
independent clients of one process, and a disagreement between them is a real
fault you can chase.
