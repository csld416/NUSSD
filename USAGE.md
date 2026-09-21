# NUSSD Runtime Bridge Usage

This guide covers the current NPU–SSD runtime bridge: starting the three-process simulation, selecting its main toggles, watching requests cross the protocol, and understanding the expected result.

## What Starts

With the runtime SSD path enabled, the PyTorchSim launcher asks LegoSim/interchiplet to start and coordinate three independent processes:

```text
PyTorchSim / TOGSim  <->  LegoSim/interchiplet  <->  SimpleSSD
   NPU requests          synchronization             storage timing
                               |
                            PopNet
                    NPU--SSD network timing
```

The FIFO carries protocol messages such as request ID, operation, logical offset, and length. Matching LegoSim events carry simulated command and response sizes and resolve their arrival cycles.

## Before Starting a Full Workload

The quick protocol demo builds its small NPU-side client automatically. A full PyTorchSim workload requires all of the following binaries:

```text
build/togsim/bin/Simulator
LEGOSIM_MICRO/interchiplet/bin/interchiplet
LEGOSIM_MICRO/popnet_chiplet/build/popnet
SimpleSSD-Standalone/build/simplessd-legosim
```

The SimpleSSD wrapper can be rebuilt with:

```bash
cmake --build SimpleSSD-Standalone/build --target simplessd-legosim -j2
```

TOGSim also needs to be rebuilt after its bridge sources change. Its current build requires the project-compatible compiler and Conan dependencies.

With the configured out-of-tree build used by `config/nussd_runtime.env`, rebuild it with:

```bash
cmake --build build/togsim --target Simulator -j2
```

## Quick Protocol Demonstration

The easiest way to watch the NPU-side client and SimpleSSD cooperate is:

```bash
./run.sh
```

The script builds its small protocol client when needed, creates an isolated run directory, waits briefly for a monitor to attach, and starts LegoSim plus the runtime SimpleSSD wrapper. Its human-editable toggle section controls request offset/length, tracing, monitor delay, and whether SimpleSSD is rebuilt.

In a second terminal, run:

```bash
cd /home/csld/SIM
./run.sh monitor
```

The `monitor` command automatically follows the latest demo; no run-directory or LegoSim command needs to be copied. After a run, `./run.sh path` prints its output directory.

## Start a Full PyTorchSim Workload

For the full PyTorchSim launcher path, load the prepared environment:

```bash
source config/nussd_runtime.env
```

Then run your normal PyTorchSim workload or test from the same shell. Environment variables exported by the configuration file are inherited by the Python frontend, interchiplet, TOGSim, and SimpleSSD.

When tracing is enabled, the launcher prints a command similar to:

```text
[NUSSD trace] monitor with: MONITOR_MODE=bridge RUN_DIR=/path/to/0.legosim_run ./monitor.sh
```

Copy that command into a second terminal. For example:

```bash
MONITOR_MODE=bridge \
RUN_DIR=/home/csld/SIM/runtime_results/0.legosim_run \
INTERVAL=1 \
./monitor.sh
```

The run index may not be `0`; use the exact path printed by the launcher.

## Quick-Demo Toggles

For `./run.sh`, edit the toggle block at the top of [run.sh](run.sh):

| Variable | Purpose |
|---|---|
| `NUSSD_PROTOCOL_TRACE` | Set to `1` for live monitor events or `0` to disable them |
| `REQUEST_OFFSET_BYTES` | Logical SSD byte offset used by the demo read |
| `REQUEST_LENGTH_BYTES` | Number of bytes requested by the demo read |
| `MONITOR_ATTACH_DELAY_SECONDS` | Delay before launch, giving the second terminal time to attach |
| `MONITOR_REFRESH_SECONDS` | Refresh interval used by `./run.sh monitor` |
| `REBUILD_SIMPLESSD` | Set to `1` to rebuild `simplessd-legosim` before running |

Each value can also be overridden for one invocation, for example:

```bash
REQUEST_LENGTH_BYTES=16384 ./run.sh
```

## Full-Workload Toggles

Edit [config/nussd_runtime.env](config/nussd_runtime.env) before sourcing it, or override a value afterward in the same shell.

| Variable | `1` | `0` |
|---|---|---|
| `TOGSIM_LEGOSIM_SSD` | Route weight DMA reads to the live SimpleSSD process | Use the non-live SSD path |
| `TOGSIM_LEGOSIM_SSD_NOC` | Run phase-two PopNet for the NPU--SSD link | Use the no-op phase-two process |
| `NUSSD_PROTOCOL_TRACE` | Write live NPU and SSD protocol events | Disable per-request event files |
| `TOGSIM_LEGOSIM_DRAM` | Enable the separate DRAM LegoSim service | Keep the normal DRAM path |
| `TOGSIM_LEGOSIM_DRAM_NOC` | Enable the DRAM PopNet phase when the DRAM service is active | Use its no-op phase-two path |

Other useful settings in the file select the LegoSim root, SimpleSSD executable/configurations, TOGSim log directory, and debug level.

The default SSD NoC profile models the existing UFS 4.0 raw-link baseline:

```text
TOGSIM_LEGOSIM_SSD_NOC_ROUNDS=3
TOGSIM_LEGOSIM_SSD_POPNET_FLIT_WORDS=1
TOGSIM_LEGOSIM_SSD_POPNET_CLOCK_RATE=0.725
TOGSIM_LEGOSIM_SSD_POPNET_TOPOLOGY=.../line_2_ufs4.gv
```

The runtime bridge uses nanoseconds as LegoSim's common time unit. One 64-bit
word per PopNet cycle at 0.725 cycles/ns represents approximately 5.8 GB/s.
The launcher gives the same flit-word value to both LegoSim's benchmark
generator and PopNet, so payload size is preserved across the phase boundary.
The topology's edge weight adds the fixed propagation component.
For reads, PopNet models a 64-byte command from the NPU to the SSD and the
full payload from the SSD back to the NPU. PopNet runs after phase one, so the
launcher uses multiple rounds and reports the last completed round, where the
calculated network delay has been fed back into TOGSim.

The launcher treats the PopNet phase as failed unless every child exits with
status zero, `delayInfo.txt` is nonempty, and round 2 reports that it loaded at
least one delay record. A communication-order mismatch that makes LegoSim
cancel the delay table is also a hard error rather than a timing-free pass.

`TOGSIM_LEGOSIM_SSD_BANDWIDTH_GBPS` is reserved for a future analytical link
and has no effect while PopNet is active. PopNet bandwidth is controlled by
its flit size, clock rate, and topology parameters above.

The full-workload configuration also selects `TOGSIM_SSD_TRACE_DIR`,
`TOGSIM_SSD_TRACE_NAME`, and `TOGSIM_SSD_PLACEMENT_ALIGNMENT`. Before each
streamed module executes, Python writes:

```text
<TOGSIM_SSD_TRACE_DIR>/<TOGSIM_SSD_TRACE_NAME>/
├── model_weight_placements.tsv
└── model_weight_layout.tsv
```

The active placement manifest maps each materialized tensor's half-open host
range `[host_base, host_end)` to a stable, aligned logical SSD range. TOGSim
uses the same record both to recognize a weight DMA and calculate its SSD
offset. The layout file records every tensor placement observed so far in the
current Python process.

Tracing flushes every event so a human can watch it immediately. It does not change simulated cycles, but it adds host-side file I/O and should normally be disabled for performance sweeps:

```bash
export NUSSD_PROTOCOL_TRACE=0
```

## What the Monitor Shows

Each traced run creates:

```text
<run_dir>/live/
├── npu.events.tsv
└── ssd.events.tsv
```

`monitor.sh` correlates these streams by protocol request ID and displays:

- TOGSim, LegoSim, and SimpleSSD process liveness
- issued, completed, in-flight, and failed request counts
- operation, logical offset, and byte length
- NPU issue and response-arrival cycles
- SimpleSSD BIO submission and completion ticks
- SSD service time and NPU-visible end-to-end cycles
- the most recent protocol lifecycle events

A successful read should progress through events equivalent to:

```text
NPU_ISSUE
NPU_REQUEST_FIFO_SENT
SSD_REQUEST_FIFO_RECEIVED
SSD_REQUEST_ARRIVED
SSD_BIO_SUBMITTED
SSD_BIO_COMPLETED
SSD_RESPONSE_TRANSFER_RESOLVED
NPU_RESPONSE_ARRIVED
NPU_REQUEST_COMPLETE
```

The NPU and SSD records should have the same request ID, operation, offset, length, and `SUCCESS` status. At program exit, a separate `SHUTDOWN` request and acknowledgement should appear.

## Current Expected Limitations

The current bridge proves that TOGSim and SimpleSSD can cooperate through the established runtime protocol, but it is not yet the final research configuration:

- Runtime storage requests are blocking queue-depth one.
- Logical SSD placements currently allocate tensors in first-seen order within
  one Python workload process; the simulator models timing and does not copy
  real tensor contents into an SSD image.
- The current PopNet profile is a raw UFS 4.0 link model; it does not yet
  include full UniPro/UFS protocol overheads, and the runtime request path is
  still blocking queue-depth one, so it cannot produce multi-request link
  contention.
- TOGSim currently issues reads; the shared protocol also defines write, flush, and trim operations for later integration.

These limitations mean the bridge is appropriate for protocol verification now, but not yet for final bottleneck measurements.
