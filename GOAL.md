# Project Goal

This is an ECLAB project studying the following question:

If a chiplet interconnect is used between an NPU and flash, how should the
in-flash processing (IFP) module be designed? Should it remain in the flash
side, be changed, or be removed?

The ancestor reference paper is MICRO'24: Cambricon-LLM, a 70B edge inference
system.

The relevant simulators are:

- NPU: PytorchSIM
- Chiplet interconnect: LegoSim
- Flash/SSD: SimpleSSD-Standalone

The intended flow is:

```text
PytorchSIM -> LegoSim -> SimpleSSD-Standalone
```

This project is split into two sub-teams. This repository is owned by the flash
team and is responsible for the SimpleSSD-Standalone side.

## Repository Layout

LegoSim and SimpleSSD-Standalone should remain sibling projects, not nested
inside each other:

```text
ECLAB/SIM/
  LEGOSIM_MICRO/
  SimpleSSD-Standalone/
```

Reason: LegoSim is a coordinator that launches simulator processes from YAML.
SimpleSSD should be integrated as another external simulator process, similar
to gem5, GPGPU-Sim, Sniper, PopNet, or ScaleSim. It should only be placed under
`LEGOSIM_MICRO/third_party` if the project changes direction and LegoSim needs
to build or link SimpleSSD as a vendored library dependency.

## Working Assumptions

The first target architecture is an active SSD model:

```text
NPU -> chiplet interconnect -> flash controller chiplet -> flash dies
```

SimpleSSD should represent the flash controller and SSD internals. LegoSim
should represent the chiplet interconnect and cross-simlet synchronization.

This means:

- LegoSim owns NPU-to-flash-controller interconnect latency/bandwidth.
- SimpleSSD owns active SSD service time: HIL, ICL, FTL, PAL, flash timing,
  internal queueing, cache effects, garbage collection, and flash contention.
- SimpleSSD should not expose physical flash addresses in the first API.
- SimpleSSD should expose a logical timing interface for reads and writes.
- IFP should be added after the baseline LegoSim-to-SimpleSSD path works.

## Milestones

1. Understand the goal and SimpleSSD architecture.
2. Connect SimpleSSD-Standalone to LegoSim as a separate SimpleSSD simlet.
3. Validate baseline read/write timing behavior.
4. Add IFP support after the baseline integration is stable.

## First Integration API

SimpleSSD should run as a separate process and communicate with LegoSim over
IPC. The first protocol should match LegoSim's native interchiplet protocol,
not introduce a separate JSON layer.

LegoSim communicates with child simulators through stdin/stdout pipes and
parses lines beginning with:

```text
[INTERCMD]
```

The SimpleSSD simlet should therefore be launched as a LegoSim phase-1 process
from YAML and should emit/consume LegoSim-compatible text commands, following
the conventions in:

- `LEGOSIM_MICRO/interchiplet/includes/sync_protocol.h`
- `LEGOSIM_MICRO/interchiplet/srcs/interchiplet.cpp`
- `LEGOSIM_MICRO/interchiplet/srcs/cmd_handler.cpp`

The first API is timing-only. It should not transfer real payload bytes.

Supported storage operations:

- logical read
- logical write
- basic info/stat reporting for validation

The API should be asynchronous and support multiple outstanding requests from
the start, because SSD queue depth and concurrency affect timing. Bring-up and
debugging can still use queue depth 1.

Requests from LegoSim are expressed in cycle time. The SimpleSSD simlet should
convert LegoSim-side request timing into SimpleSSD event-engine ticks, submit
logical I/O into the active SSD path, and return completion timing through the
same LegoSim synchronization style.

The normal LegoSim communication commands look like:

```text
[INTERCMD] READ  <cycle> <src_x> <src_y> <dst_x> <dst_y> <nbytes> <desc>
[INTERCMD] WRITE <cycle> <src_x> <src_y> <dst_x> <dst_y> <nbytes> <desc>
```

Responses use LegoSim-style commands such as:

```text
[INTERCMD] SYNC <cycle>
[INTERCMD] RESULT ...
```

One open design point remains: LegoSim's built-in `READ` and `WRITE` command
format carries cycle, source/destination coordinates, byte count, and protocol
descriptor, but it does not carry a storage offset or LBA. The first bring-up
may use a simple offset convention, such as an internal sequential logical
offset cursor. A cleaner later contract may add a SimpleSSD-specific command
or descriptor convention for explicit logical offsets.

## Statistics API

`get_stats` should return a small stable subset by default, not raw SimpleSSD
internal stat names. This avoids coupling LegoSim to SimpleSSD implementation
details.

The default stable subset should include:

- read/write count
- bytes read/written
- completed request count
- pending request count
- average latency
- selected cache counters, such as cache hits/misses
- selected flash counters, such as NAND reads/writes
- selected FTL counters, such as GC count

A later debug mode may expose raw SimpleSSD stats, but raw stats should not be
the default LegoSim API contract.
