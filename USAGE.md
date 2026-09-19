# NUSSD Runtime Bridge Usage

This guide covers the current NPU–SSD runtime bridge: starting the three-process simulation, selecting its main toggles, watching requests cross the protocol, and understanding the expected result.

## What Starts

With the runtime SSD path enabled, the PyTorchSim launcher asks LegoSim/interchiplet to start and coordinate three independent processes:

```text
PyTorchSim / TOGSim  <->  LegoSim/interchiplet  <->  SimpleSSD
   NPU requests             link timing             storage timing
```

The FIFO carries protocol messages such as request ID, operation, logical offset, and length. Matching LegoSim events carry simulated command and response sizes and resolve their arrival cycles.

## Before Starting

The following binaries must already exist:

```text
PytorchSim-S/TOGSim/build/bin/Simulator
LEGOSIM_MICRO/interchiplet/bin/interchiplet
SimpleSSD-Standalone/build/simplessd-legosim
```

The SimpleSSD wrapper can be rebuilt with:

```bash
cmake --build SimpleSSD-Standalone/build --target simplessd-legosim -j2
```

TOGSim also needs to be rebuilt after its bridge sources change. Its current build requires the project-compatible compiler and Conan dependencies.

## Start the Runtime Bridge

From the repository root, load the prepared environment:

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

## Main Toggles

Edit [config/nussd_runtime.env](config/nussd_runtime.env) before sourcing it, or override a value afterward in the same shell.

| Variable | `1` | `0` |
|---|---|---|
| `TOGSIM_LEGOSIM_SSD` | Route weight DMA reads to the live SimpleSSD process | Use the non-live SSD path |
| `NUSSD_PROTOCOL_TRACE` | Write live NPU and SSD protocol events | Disable per-request event files |
| `TOGSIM_LEGOSIM_DRAM` | Enable the separate DRAM LegoSim service | Keep the normal DRAM path |
| `TOGSIM_LEGOSIM_DRAM_NOC` | Enable the DRAM PopNet phase when the DRAM service is active | Use its no-op phase-two path |

Other useful settings in the file select the LegoSim root, SimpleSSD executable/configurations, TOGSim log directory, and debug level.

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
- TOGSim currently maps every weight read to temporary logical SSD offset zero.
- The generated SSD phase-two process is still `/bin/true`; the runtime path does not yet use the final UCIe/PopNet link topology.
- TOGSim currently issues reads; the shared protocol also defines write, flush, and trim operations for later integration.

These limitations mean the bridge is appropriate for protocol verification now, but not yet for final bottleneck measurements.
