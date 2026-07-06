# Project Context

This file summarizes the working context and decisions from the initial
discussion so a new agent can continue from the same point.

## Research Goal

This is an ECLAB project studying:

```text
If a chiplet interconnect is used between an NPU and flash, how should the
in-flash processing (IFP) module be designed? Should it remain, change, or be
removed?
```

The ancestor reference is MICRO'24: Cambricon-LLM, a 70B edge inference system.

The planned simulator stack is:

```text
PytorchSIM -> LegoSim -> SimpleSSD-Standalone
```

Simulator ownership:

- `PytorchSIM`: NPU side
- `LegoSim`: chiplet interconnect and cross-simlet synchronization
- `SimpleSSD-Standalone`: flash/SSD side

This repository is the flash team's repository.

## Architecture Decision

The first target architecture is an active SSD:

```text
NPU -> chiplet interconnect -> flash controller chiplet -> flash dies
```

SimpleSSD represents the flash controller chiplet and SSD internals. It should
not expose raw flash dies or physical flash addresses in the first integration.

LegoSim owns:

- NPU-to-flash-controller chiplet interconnect latency/bandwidth
- Network-on-Interposer timing
- cross-simlet synchronization
- return-path interconnect delay

SimpleSSD owns:

- active SSD service time
- HIL, ICL, FTL, PAL
- internal DRAM/cache behavior
- internal queueing/contention
- garbage collection
- NAND/flash timing

This avoids double-counting interconnect delay and keeps SimpleSSD focused on
flash-side behavior.

## Development Order

The agreed milestone order is:

1. Understand the goal and SimpleSSD architecture.
2. Connect SimpleSSD-Standalone to LegoSim as a separate SimpleSSD simlet.
3. Validate baseline read/write timing behavior.
4. Add IFP after the baseline integration is stable.

IFP is intentionally last because it should be independent of understanding the
baseline and building the LegoSim connection.

## Repository Layout Recommendation

Keep LegoSim and SimpleSSD as sibling projects, not nested inside each other:

```text
ECLAB/
  LegoSim/
  SimpleSSD-Standalone/
  PytorchSIM/
  experiments/
    configs/
    scripts/
    traces/
    results/
```

Reason: SimpleSSD is planned as a separate simlet process over IPC, not a
library vendored into LegoSim.

Only use `LegoSim/third_party/SimpleSSD` if the design changes to building
SimpleSSD as a LegoSim dependency. That is not the current plan.

## SimpleSSD Integration Boundary

Use a logical storage API first, not physical flash operations.

Good first API level:

```text
read(offset, size, arrival_tick, id)
write(offset, size, arrival_tick, id)
```

Avoid first exposing:

```text
channel/package/die/plane/page operations
```

Reason: exposing physical flash internals would bypass or weaken the active SSD
firmware path. That would move toward an OCSSD/passive-flash architecture, which
is a different experiment.

Existing useful code path:

- `sil/none/none.cc` converts external block I/O into `SimpleSSD::HIL::Request`.
- `simplessd/hil/hil.cc` handles logical read/write and forwards into `ICL`.
- `ICL -> FTL -> PAL` preserves active SSD behavior.

The planned SimpleSSD simlet should probably reuse the `SIL::None` style path
and skip the internal workload generator (`IGL`).

## IPC/API Decision

SimpleSSD should run as a separate process and communicate with LegoSim over
IPC.

First protocol:

- line-delimited JSON
- timing-only
- one JSON object per line
- logs should go to `stderr` or files so `stdout` can remain clean protocol
  output if stdin/stdout is used

JSON was chosen because it is easy to debug, log, and replay. Binary/shared
memory can be considered later if IPC overhead matters.

Initial transport can be stdin/stdout if LegoSim spawns the SimpleSSD process.
A Unix socket is also acceptable later, but the protocol should remain the same.

## Timing Model

The API is asynchronous.

Requests from LegoSim are assumed to arrive in nondecreasing `arrival_tick`
order.

The simlet must support multiple outstanding requests from the start because
queue depth and concurrency affect SSD behavior. However, initial validation can
use queue depth 1.

Important rule:

```text
Completion order does not have to match submission order.
LegoSim must match completions by request id.
```

Conceptual flow:

```text
1. LegoSim models NPU -> flash-controller interconnect delay.
2. LegoSim sends request to SimpleSSD with arrival_tick.
3. SimpleSSD injects the request into its active SSD model at arrival_tick.
4. SimpleSSD computes internal SSD completion timing.
5. SimpleSSD emits completion with completion_tick.
6. LegoSim models return-path interconnect delay and synchronizes the NPU side.
```

## Initial Protocol Shape

Example read request:

```json
{"type":"read","id":1,"offset":4096,"size":16384,"arrival_tick":1000000}
```

Example write request:

```json
{"type":"write","id":2,"offset":8192,"size":4096,"arrival_tick":1000100}
```

Example completion:

```json
{"type":"complete","id":1,"completion_tick":1234567,"status":"ok"}
```

Useful control requests:

```json
{"type":"get_info","id":3}
{"type":"get_stats","id":4}
{"type":"shutdown","id":5}
```

Example info response:

```json
{"type":"info","id":3,"capacity":1073741824,"logical_page_size":4096,"min_io_size":512}
```

## Statistics API

`get_stats` should return a small stable subset by default, not raw SimpleSSD
stat names. This avoids coupling LegoSim to SimpleSSD internals.

Default stable stats should include:

- read/write count
- bytes read/written
- completed request count
- pending request count
- average latency
- selected cache counters, such as cache hits/misses
- selected flash counters, such as NAND reads/writes
- selected FTL counters, such as GC count

Example stats response:

```json
{
  "type": "stats",
  "id": 4,
  "tick": 1234567,
  "stats": {
    "reads": 100,
    "writes": 20,
    "bytes_read": 409600,
    "bytes_written": 81920,
    "completed": 120,
    "pending": 4,
    "avg_latency": 12345,
    "cache_hits": 80,
    "cache_misses": 20,
    "nand_reads": 40,
    "nand_writes": 25,
    "gc_count": 2
  }
}
```

A later debug extension may expose raw SimpleSSD stats, but raw stats should
not be the default LegoSim API contract.

## Likely Next Implementation Step

Add a new SimpleSSD simlet executable or mode that:

1. Initializes the SimpleSSD engine and HIL path.
2. Does not create an `IGL` request generator or trace replayer.
3. Reads line-delimited JSON requests from IPC.
4. Schedules/injects read/write requests at `arrival_tick`.
5. Maintains pending requests by `id`.
6. Emits completion JSON when callbacks fire.
7. Supports `get_info`, `get_stats`, and `shutdown`.

The first validation should use queue depth 1. After that works, validate
multiple outstanding requests and out-of-order completions.
