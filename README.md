# Industrial Controls lab

A reproducible lab for PLC programming, industrial protocols, SCADA and OT
network design. Every lab runs as containers on one lab host and is driven by
one lifecycle tool, `./labctl`.

This repository is the controls and industrial estate. It is not a networking
lab. Network protocols, fabrics and routing drills stay in
`network/containerlab-labs`. The two do not share a topology.

## What is here now

| Lab | What it proves | State |
|---|---|---|
| `modbus-tcp` | A soft PLC exchanges real Modbus/TCP frames with a process model | Working. Moved here from `network/containerlab-labs-public`. |

Everything else in [docs/roadmap.md](docs/roadmap.md) is a plan, not a
claim.

Two support directories sit outside the lab registry:

- `plc/`: five programs in four IEC 61131-3 languages, as PLCopen files you
  can import into the OpenPLC Editor.
- `tools/`: small Python tools for this work. `plcopen.py` checks a PLCopen
  program before you import it.

## Quick start

The lab host runs Docker and Containerlab. This repository is deployed there,
never on a workstation.

```bash
ssh <user>@<lab-host>
git clone http://<forgejo>/paul/Industrial-Controls.git
cd Industrial-Controls
./labctl check                     # manifest against topology sources
./labctl up modbus-tcp             # builds the simulator image, deploys, verifies
```

The OpenPLC Editor runs on your own PC. Tunnel its port to your PC:

```bash
ssh -L 8443:127.0.0.1:8443 <user>@<lab-host>
```

Then open the Editor and point it at `https://127.0.0.1:8443`. The first
exercise is in [modbus-tcp/GETTING_STARTED.md](modbus-tcp/GETTING_STARTED.md).

Destroy one lab when you are done with it:

```bash
./labctl down modbus-tcp
```

## What is real and what is simulated

Real:

- Modbus/TCP frames, with real TCP sessions and real register addresses.
- An IEC 61131-3 program compiled by the OpenPLC Editor and executed by a PLC
  runtime with a scan cycle.
- Container networking, so a capture on the wire shows what a plant network
  shows.

Simulated:

- The PLC is software on a container, not a device with a fixed scan time.
  Real hardware keeps a deterministic cycle. A container does not.
- The tank is an 85 line Python process model. It has a level and a pump, and
  no physical inertia.
- No 24 V loop, no 4-20 mA transmitter, no motor, no valve. Electrical fault
  behaviour is not present.

The learning value is protocol detail and control logic. It is not electrical
fidelity. A physical PLC closes that gap, and no container can.

## Repository layout

```
labs.toml               one entry per lab, the only place a lab is described
labctl                  lifecycle driver, standard library only
validate-repository.sh  static gate: manifest, topologies, shell syntax
modbus-tcp/             one lab: topology, image, process model, docs
docs/                   architecture, protocols, learning path, roadmap
```

## Working rules

- One command changes one lab. There is no `--all`, and `./labctl` never
  passes `--all` to Containerlab.
- Every image is pinned by tag or digest.
- Management subnets are unique per lab and recorded in `labs.toml`.
- Protocol traffic stays inside the topology. Only a management surface is
  published, and only on host loopback.
- The repository holds no vendor licence, no device password and no plant
  data.

## Documents

- [docs/architecture.md](docs/architecture.md): the plant model, Purdue
  levels, zones and conduits, host sizing.
- [docs/protocols.md](docs/protocols.md): which protocol, who uses it, and
  which tool reads it.
- [docs/learning-path.md](docs/learning-path.md): the staged path from
  electrical work to controls and OT.
- [docs/roadmap.md](docs/roadmap.md): the labs that do not exist yet.
- [docs/lifecycle.md](docs/lifecycle.md): the manifest schema and the rules
  the driver enforces.

## Enterprise framing

A plant network separates the process, the control zone and the plant
network, and it lets traffic cross those boundaries only through a declared
conduit. The lab copies that shape at small scale: the process model and the
PLC sit together, the HMI sits one zone out, and the historian and the
engineering workstation sit further out again.

The pattern scales without change. A site with 40 PLCs and three DMZ hops
uses the same zone and conduit model, and the same rule that no protocol
crosses a boundary without a reason written down.
