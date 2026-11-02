# Agent and contributor instructions

Read this file first. It points at the documents that govern work here.

## Governing documents

- [README.md](README.md): what this repository is and what it is not.
- [docs/architecture.md](docs/architecture.md): plant model, zones, host
  sizing, addressing.
- [docs/lifecycle.md](docs/lifecycle.md): the `labs.toml` schema and the
  safety rules `./labctl` enforces. Authoritative for anything about lab
  lifecycle.
- [docs/roadmap.md](docs/roadmap.md): planned labs. A lab listed there does
  not exist yet.
- [docs/learning-path.md](docs/learning-path.md): the intended exercise order.

If two current files disagree, stop and ask. Do not pick one.

## Scope

This repository holds industrial control labs: PLC programs, process models,
industrial protocols, HMI and SCADA, and the OT network that connects them.

These belong in `network/containerlab-labs`, not here:

- routing, switching, EVPN, MPLS, access and transport networks
- anything whose purpose is to teach a network protocol rather than a control
  system

A lab may contain a router when the router is the OT boundary. It may not
become a routing lab.

## Rules

1. Add a lab in its own directory with its own `[labs.<name>]` entry. Never
   edit another lab's topology to make a new one work.
2. Pin every image by tag or digest. `latest` is rejected by `./labctl check`.
3. Give each lab a unique management subnet from `172.111.<n>.0/24`. The
   exception is recorded in `labs.toml`.
4. Keep protocol traffic inside the topology. Publish management ports on
   127.0.0.1 only.
5. Run `./labctl check` and `./validate-repository.sh` before a commit. Report
   the exact command and its output.
6. Update the lab README, `docs/protocols.md` and `docs/roadmap.md` in the
   same change that adds or changes a lab. A state that is only in the roadmap
   is not visible to the next reader.
7. Never commit a password, token, vendor licence, device configuration from a
   real site, or a real plant address.

## Documentation style

Short sentences. One main idea per sentence. Active voice. Name the command
and the place to run it. No em dashes.

State measured facts, not impressions. "Verify ran 12 checks in 4 s and
returned 0" is a report. "It works" is not.

## Git flow

Forgejo is authoritative. Push to Forgejo only. Work on an issue, then a
branch, then a pull request. Do not commit to `main` except for the initial
repository import.
