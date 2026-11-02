# Lab lifecycle

One manifest, one driver, one gate.

`labs.toml` is the only place a lab is described. `./labctl` reads it.
`./validate-repository.sh` reads it. Nothing else keeps a list of labs.

## The manifest

One `[labs.<name>]` table per lab. The name is the Containerlab name, so the
container prefix is always `clab-<name>-`.

| Key | Required | Meaning |
|---|---|---|
| `dir` | yes | Directory that holds the lab. |
| `topology` | yes | Topology file inside that directory. |
| `summary` | no | One line, used by `./labctl list`. |
| `mgmt_subnet` | yes | Management CIDR. Must match the topology and must be unique. |
| `images` | no | Images the lab pulls before deploy. Each must be pinned. |
| `external_images` | no | Images that must already exist locally. The driver never pulls them. |
| `docker_builds` | no | `{ image, context }` pairs built before deploy. |
| `runtime_owner` | no | `uid:gid` applied to the runtime directories. |
| `verify` | no | Verification scripts, relative to the lab directory, run in order. |
| `[labs.<name>.hooks]` | no | Scripts run around deploy and destroy. See below. |
| `automation_only` | no | Reason the lab must run through the automation templates. |
| `automation_template` | no | Template name printed when the driver refuses. |
| `min_free_memory_mb` | no | Memory the lab needs. `doctor` warns when the host has less. |

### Hooks

Four phases, each a list of commands. The first element is a script path
relative to the lab directory. The rest are arguments.

```toml
[labs.<name>.hooks]
pre_deploy = [["lifecycle.sh", "pre-deploy"]]
post_deploy = [["lifecycle.sh", "post-deploy"]]
pre_destroy = [["lifecycle.sh", "pre-destroy"]]
post_destroy = [["lifecycle.sh", "post-destroy"]]
```

A deploy hook that fails stops the deploy. A destroy hook that fails is
reported and the teardown continues, because a half-destroyed lab is worse
than a destroyed one with a warning.

Hooks are script paths, not shell strings. The script must exist in the
repository, so `./labctl check` can prove that it does. The path is relative
to the lab directory, so a shared script is reached with `..`.

### Runtime directories

When a topology binds `runtime/<node>` into a container, the driver creates
one directory per binding. The list of node names is never written down
twice. When `runtime_owner` is set, the driver applies that owner.

## Commands

```sh
./labctl list                    # every lab, with node count from the topology
./labctl list --markdown         # a markdown table of the labs
./labctl check                   # manifest against topology sources
./labctl check --with-validator  # the whole gate
./labctl doctor                  # host preflight
./labctl up modbus-tcp --dry-run # print every command, change nothing
./labctl up modbus-tcp
./labctl verify modbus-tcp
./labctl status modbus-tcp
./labctl down modbus-tcp
```

## What `up` does, in order

1. Refuse the lab if it is `automation_only`.
2. Run `doctor` checks on docker, containerlab, sudo, memory and disk.
3. Run the `pre_deploy` hooks.
4. Create the runtime directories from the topology binds, and set their owner.
5. Build the local images, then pull the rest.
6. Run `containerlab deploy -t <topology>` from the lab directory.
7. Run the `post_deploy` hooks.

`down` runs the `pre_destroy` hooks, then
`containerlab destroy -t <topology> --cleanup`, then the `post_destroy` hooks.

## Safety rules the driver enforces

- Every changing command names one lab. There is no `--all`.
- The driver never passes `--all` to Containerlab.
- A lab with `automation_only` is refused, with the template name printed.
- An unknown lab is refused, with the list of known labs.
- `down` prints the lab, the topology, and the container prefix before it runs.
- One lab's command never touches another lab's containers.

## Adding a lab

1. Create the directory and the topology. Pin every image.
2. Pick a management CIDR that no other lab and no Docker network uses.
3. Add a `[labs.<name>]` entry to `labs.toml`.
4. Run `./labctl check`. It fails on a name mismatch, a subnet mismatch, an
   unpinned image, an image the topology uses but the manifest does not
   declare, and a missing verify or hook script.
5. Run `./labctl up <name> --dry-run` and read the commands.
6. Run `./labctl up <name>`, then `./labctl verify <name>`.
7. Update the lab README, `docs/protocols.md` and `docs/roadmap.md`.

## Why TOML and a separate reader

The driver uses only the Python standard library, so it runs on a lab host
with no packages installed. Python 3.11 or newer is required for `tomllib`.

Topology facts are read by a small indentation reader, not a YAML parser. It
reads the name, the management subnet, node kinds, node images and bind
sources, and nothing else. `validate-repository.sh` still parses every topology
with PyYAML, so a disagreement between the two shows up as a failing check
rather than as a wrong assumption.

## Provenance

The driver and the manifest pattern come from `network/containerlab-labs`,
where nine labs share them. They are copied here unchanged, except that
`validate-repository.sh` checks this repository's topologies and this
repository's tests.
