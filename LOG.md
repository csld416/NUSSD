# Project Log (Rule: the more recent, the more on file top)

## 2026-09-19

**Runtime SimpleSSD IPC and live observability**

- Initialized this project as "NUSSD" in the public GitHub repository.
- Added `protocol/ssd_ipc_protocol.h` as the shared TOGSim/SimpleSSD wire contract. The fixed-size, versioned messages carry operation, request ID, logical byte offset, length, completion status, and SimpleSSD service timestamps. FIFO messages carry semantics while LegoSim events carry simulated transfer size and timing.
- Modified `SimpleSSD-Standalone/sim/legosim_main.cc` to add a persistent `--runtime-ipc` server mode. It blocks on the request FIFO instead of busy-waiting, validates each message, submits a BIO to SimpleSSD, advances the event engine until completion, returns a response, and exits only after a shutdown request. The first implementation is deliberately blocking QD1: one request is completed before the next is accepted.
- Modified `SimpleSSD-Standalone/CMakeLists.txt` to expose the repository-level protocol header and link the LegoSim IPC support required by the runtime wrapper.
- Reworked TOGSim's `SsdLegoSimLink` into a client for the shared protocol. Each logical read sends a 64-byte command event toward the SSD, exchanges the 32-byte request/response metadata through `PipeComm`, and models the returned payload as a LegoSim read event. Request IDs are checked end to end, and LegoSim's resolved response-arrival cycle becomes the DMA completion cycle.
- Modified `TOGSim/src/DMA.cc` so weight DMA reads use the live SSD client when `TOGSIM_SSD_LEGOSIM=1`. Requests claimed by the SSD path are not also sent through the DRAM LegoSim path. Address translation is intentionally temporary: all reads currently use logical SSD offset zero until tensor-to-storage placement metadata is implemented.
- Updated `Simulator/simulator.py` and `PyTorchSimFrontend/extension_config.py` to launch the real `simplessd-legosim --runtime-ipc` executable as a separate LegoSim phase-1 process, pass its configuration/output paths, and reconcile TOGSim core cycles with the SSD wrapper's nanosecond-facing LegoSim clock. The SSD phase-2 process remains `/bin/true`, so this step establishes real storage-service timing but does not yet add a PopNet SSD-link topology.
- Verified the bridge with syntax checks, Python bytecode compilation, and a live three-process smoke test using the modified TOGSim SSD client, LegoSim/interchiplet, and SimpleSSD. A 4 KiB runtime read completed successfully, SimpleSSD reported one completed read and 4096 bytes read, and the protocol shutdown/ack path exited cleanly.
- Deferred follow-up work: implement stable tensor/TOG-address to logical SSD-offset translation, replace the SSD phase-2 placeholder with the desired interconnect model, and extend the blocking QD1 protocol path if concurrent outstanding storage requests are required.
- Added optional live protocol observability. TOGSim and SimpleSSD now emit separate append-only TSV event streams under `<run_dir>/live`, correlated by request ID and recording protocol stages, request fields, LegoSim cycles, SimpleSSD ticks, and completion status. Extended `monitor.sh` with a bridge mode that reads these files without participating in the simulation. A traced 4 KiB live smoke test completed with matching request data, zero protocol errors, and a clean shutdown.
- Added `config/nussd_runtime.env` as the sourceable runtime/trace toggle configuration and `USAGE.md` as the human-readable start, monitoring, toggle, expected-output, and current-limitations guide.

## 2026-09-18

Updated README for more comprehensive goal structure.

## 2026-09-08

**Baseline Correction from PCIe to UFS 4.0**

The previous baseline was mislabeled as PCIe. The intended baseline is UFS 4.0.

Important implementation consequence:

```text
The active LegoSim integration does not use SimpleSSD's native NVMe PCIe timing
path for the host-to-SSD link. SimpleSSD is run with Interface = 0, and the
external NPU/SSD link is modeled by LegoSim + PopNet.
```

Therefore the correction should be made in the LegoSim/PopNet configs, not by
switching `SimpleSSD-Standalone/config/sample.cfg` to `Interface = 3`.

Added UFS4 baseline files:

```text
config/legosim_ufs4.yml
config/legosim_ufs4_hot.yml
SimpleSSD-Standalone/topology/line_2_ufs4.gv
```

UFS4 raw interface target:

```text
23.2 Gb/s per lane * 2 lanes = 46.4 Gb/s = 5.8 GB/s
```

PopNet representation:

```text
-F 1 => 8 bytes / PopNet cycle
clock_rate = 0.000725
```

Because interchiplet converts SimpleSSD/interchiplet ps ticks to PopNet cycles
by multiplying by `clock_rate`, this means:

```text
1 PopNet cycle = 1 / 0.000725 ps = 1379.31 ps = 1.37931 ns
8 bytes / 1.37931 ns ~= 5.8 GB/s
```

The UFS4 topology uses:

```text
edge[weight=5.075]
```

This corresponds to about `7 ns` in the UFS4 PopNet clock domain:

```text
5.075 cycles * 1.37931 ns/cycle ~= 7.0 ns
```

This is currently a raw-link UFS4 approximation. It does not fully model
UniPro packet headers, UFS command protocol, link startup, power-state
transitions, or software-stack latency.

Updated `results/run_pcie_p_characterization.py` so it can run either:

```text
--variant ufs4
--variant pcie
```

Default output paths now target UFS4:

```text
ufs4_p_characterization_8ch_onfi52/
results/ufs4_p_characterization_8ch_onfi52.csv
results/ufs4_p_characterization_8ch_onfi52.out
```

Smoke test:

```text
python3 -u results/run_pcie_p_characterization.py \
  --variant ufs4 \
  --modes cold \
  --sizes 4KB \
  --qds 1 \
  --run-root /tmp/ufs4_smoke \
  --csv /tmp/ufs4_smoke.csv \
  --log /tmp/ufs4_smoke.out \
  --force
```

Result:

```text
cold_ufs4_4096_qd1
final_cycle = 49,260,192 ps
link_occupied = 280,000 ps
p_wall = 0.0056841028959
PopNet finished = 2 / 2
```

The two link transactions were:

```text
64B read command
4KB read response
```

## 2026-08-27

**Analytical Model Correction: FTL CPU Cost Does Not Scale With N_LPN(S)**

### What Was Investigated

Traced `CPU::applyLatency()` (`simplessd/cpu/cpu.cc:733-793`) to determine
whether the FTL CPU-model cost is serialized across the multiple LPN
subrequests that make up one large read (i.e. whether the earlier
`T_FTL,CPU(S) = ceil(S/32KB) * 1.285us` formula is correct), by checking for
shared CPU scheduling state (busy-until timestamp, core pool queue, finite
parallelism).

### Finding 1: `applyLatency()` Is Completely Stateless

```text
uint64_t CPU::applyLatency(NAMESPACE ns, FUNCTION fct) {
  ...
  pCore->addStat(inst->second);   // pure statistics bookkeeping only
  return inst->second.latency;    // fixed CPI-table value, always
}
```

The return value is a static lookup from the `InstStat` CPI table -- it does
not depend on `tick`, on how many prior calls happened, or on any core-busy
state. `pCore->addStat()` (`cpu.cc:133-136`) only increments a cumulative
statistics counter used for the printed stats dump; it has zero effect on
control flow or timing. `leastBusyCPU()` (`cpu.cc:641-669`) only decides
which core's *statistics* counter gets incremented -- not which core
processes the "job" in any timing sense.

The class does contain real busy-until/queueing machinery
(`Core::submitJob`/`handleJob`/`jobDone`, `cpu.cc:90-131`, using a `busy`
flag and a `jobs` queue) that *would* implement genuine serialization -- but
`applyLatency()` never calls `submitJob()`. That machinery is dead code with
respect to every call site actually exercised by this project's read path
(`FTL::read`, `PageMapping::read`/`readInternal`, `ICL::read`,
`GenericCache::read`). `FTLCoreCount` in the active config has no effect on
the returned latency through this path.

### Finding 2: `ICL::read()`'s Per-LPN Loop Uses MAX, Not SUM -- This Is the Real Correction

```text
simplessd/icl/icl.cc:66-95, ICL::read()

for (uint64_t i = 0; i < req.range.nlp; i++) {
  beginAt = tick;                        // reset to the SAME starting tick every iteration
  ...
  pCache->read(reqInternal, beginAt);    // this LPN's whole chain (FTL CPU + mapping DRAM + PAL) runs from beginAt
  finishedAt = MAX(finishedAt, beginAt); // MAX across iterations, not accumulation
}
tick = finishedAt;
```

`beginAt` is reset to the *original* `tick` at the top of every loop
iteration, not carried forward from the previous iteration's result. All
`N = req.range.nlp` per-LPN chains are modeled as starting from the same
tick and running independently; the loop keeps only the maximum finishing
time across all N, not a sum.

### Correction to the Analytical Model

Since every per-LPN FTL CPU cost is identical (same `InstStat` lookup
regardless of which LPN is being processed), and `applyLatency()` has no
cross-call state (Finding 1), and the calling loop takes MAX not SUM
(Finding 2):

```text
T_FTL,CPU(S) = T_FTL,CPU,one          (constant, independent of S)
```

This replaces the earlier (incorrect) formula from this session's analytical
model derivation:

```text
T_FTL,CPU(S) = ceil(S/32KB) x 1.285us          <- WRONG, derived assuming
                                                    sequential/summed per-LPN
                                                    calls; ICL::read()'s loop
                                                    structure does not do that
```

This is a code-derived correction (not measured), confirmed independently at
two separate points: (1) the CPU-model layer has no mechanism to serialize
across calls, and (2) the calling loop explicitly does not accumulate `tick`
across iterations.

### Open Question Flagged, Not Yet Resolved

The "overlap -> max, not sum" behavior confirmed here is specific to the
ICL-level bookkeeping and the CPU-model layer, both shown to be stateless/
parallel-friendly. It does NOT automatically mean every per-LPN cost
overlaps for free:

- `pDRAM->read()`'s mapping-table lookup uses `SimpleDRAM::updateDelay()`,
  which tracks a shared `lastDRAMAccess` timestamp (`dram/simple.cc:53-74`)
  -- this IS stateful and order-dependent. Whether concurrent (same-tick)
  LPN subrequests contend on this shared DRAM state, and therefore whether
  `T_mapping_DRAM(S)` should also be corrected away from its
  `ceil(S/32KB) x 0.7us` form, has not been checked.
- The PAL layer's `FindFreeTime`/`InsertFreeSlot` channel/die scheduling
  (`pal/old/PAL2.cc`) is also stateful, but per-channel
  (`ChFreeSlots[channel]`) and per-die (`DieFreeSlots[die]`) -- different
  LPNs of one large request likely land on different channels (per
  `PageAllocation=CWDP` cycling channel first), which would mean their PAL
  costs genuinely overlap too, but this depends on channel count (8 in the
  active config) providing enough parallelism. Once `N_LPN(S)` exceeds the
  channel count, later LPNs would need to queue for a channel already in
  use -- a real finite-parallelism bound (P = channel count), distinct from
  and unrelated to the CPU-model layer covered in this entry. Not derived
  here.

Both of these need their own trace before `T_mapping_DRAM(S)` and `T_PAL(S)`
can be trusted at their previously-derived forms for `N_LPN(S) > 1`
(i.e. `S > 32KB`).

**Read Path: Split Request-Leg Command Size From Response-Leg Data Size**

### Motivation

Every measurement so far (including the PCIe/UCIe flit-latency analytical
model derived earlier this session) modeled both the request leg (NPU->SSD)
and the response leg (SSD->NPU) as carrying the full request size `S`. For a
read, that is not the abstraction we want: a real read's *request* is a
small fixed-size command (LBA + length), and only the *response* carries the
actual data payload. This entry changes the read path only; the write path
is intentionally left untouched for now.

### What Changed

- `PyTorchSim/TOGSim/include/DramLegoSim.h`: split `PendingRequest::nbytes`
  into two fields -- `command_bytes` (request/announce leg wire size) and
  `data_bytes` (response/data leg wire size, always the real request size).
- `PyTorchSim/TOGSim/src/DramLegoSim.cc`:
  - Added `kEnableReadCommandShrink` (bool) and `kReadCmdBytes` (= 64,
    e.g. an NVMe read command) as named constants in the anonymous
    namespace next to `kInterCmdHead`, not buried in `push()`.
  - `push()`: `command_bytes = (kEnableReadCommandShrink && !is_write) ?
    kReadCmdBytes : nbytes`. `data_bytes` is always the real `nbytes`.
  - `emit_request_write()` now sends `pending.command_bytes` instead of
    `pending.nbytes`; `emit_response_read()` sends `pending.data_bytes`.
- `SimpleSSD-Standalone/sim/legosim_main.cc`: mirrored the same
  `kEnableReadCommandShrink` / `kReadCmdBytes` constants, and the
  request-arrival leg (`emitRead`, paired against the NPU's WRITE) now
  sends `kReadCmdBytes` instead of `options.requestBytes` when
  `options.op == OP_READ`. The completion leg (`emitWrite`) and the SSD's
  internal `BIL::BIO` service size (`pending[i].bytes`) are both untouched
  -- the SSD still services the real `S` bytes internally; only the
  interconnect message size on the request leg changed.

### Critical Constraint Discovered

LegoSim's coordinator requires the WRITE and READ legs of a pair to declare
the *exact same* `nbytes`, or pairing fails and both simlets hang waiting
for a SYNC that never arrives:

```text
LEGOSIM_MICRO/interchiplet/includes/cmd_handler.h:391-392,437-438
  hasMatchWrite()/hasMatchRead(): __cmd.m_nbytes == __write_cmd.m_nbytes
```

This means `kReadCmdBytes` must be numerically identical in both
`DramLegoSim.cc` and `legosim_main.cc` -- there is no shared header between
these two separately-built binaries enforcing that. Documented loudly with
cross-referencing comments in both files pointing at each other and at this
constraint, since nothing will catch a mismatch except a hung run.

### Baseline Recoverability

`kEnableReadCommandShrink` is a named `constexpr bool` in both files.
Setting it to `false` in both places restores the original
single-size-both-legs behavior with no other code changes. (Full history is
also in git regardless.)

### Build

```text
cd SimpleSSD-Standalone && cmake --build build --target simplessd-legosim -j4

c++ -std=c++17 \
  PyTorchSim/TOGSim/tests/DramLegoSim_driver.cc \
  PyTorchSim/TOGSim/tests/DramLegoSim_base_stub.cc \
  PyTorchSim/TOGSim/src/DramLegoSim.cc \
  -IPyTorchSim/TOGSim/tests/stubs -IPyTorchSim/TOGSim/include \
  -IPyTorchSim/TOGSim/include/scheduler \
  -IPyTorchSim/TOGSim/extern/ramulator2/src \
  -o PyTorchSim/TOGSim/tests/build/dram_legosim_driver
```

(`dram_legosim_driver` is built standalone, not through TOGSim's own CMake
-- same constraint noted in the 2026-07-10 entry: no
`conanbuildinfo.cmake` in this checkout.)

### Validation

QD1 cold-read smoke test, `config/legosim_pcie.yml`, sizes 4KB-1MB, `-t 1`:

| S | bench.txt request-leg pac_size | request-leg delay (raw popnet cycles) | bench.txt response-leg pac_size | response-leg delay |
| ---: | ---: | ---: | ---: | ---: |
| 4KB | 5 | 49 | 257 | 975 |
| 16KB | 5 | 49 | 1,025 | 3,791 |
| 64KB | 5 | 49 | 4,097 | 15,055 |
| 256KB | 5 | 49 | 16,385 | 60,111 |
| 1MB | 5 | 49 | 65,537 | 240,335 |

- Request-leg `pac_size` is constant at 5 flits across every size (matches
  `ceil(64/16)+1 = 5` for PCIe `-F 2`, confirming `kReadCmdBytes=64` is
  actually reaching PopNet on the wire, not just the NPU-side struct).
- Request-leg delay is constant (49 cycles) across the full 4KB-1MB range.
- Response-leg delay grows with `S`, tracking the same values measured
  earlier this session for the (previously symmetric) full-size leg.
- Every run validated `Transaction count: 2` / `total finished: 2` in
  `popnet_0.log` (pairing succeeded on both legs despite their now-different
  declared sizes).
- Confirmed the SSD's internal service size is unaffected:
  `simplessd.log` RESULT line at S=1MB shows
  `bytes_read 1048576 bytes_written 1048576` -- the full real size, not
  `kReadCmdBytes`.

### Side Finding: the Earlier PCIe Flit-Latency Linear Fit Is Only Asymptotic

The request leg's measured delay at `e=5` flits (49 cycles) is *below* what
this session's earlier exact linear fit predicts:
`delay = (101 + 11*e)/3` -> `e=5` -> 52 cycles, not 49. The 3-cycle gap is
real (not noise -- both this run and the earlier sweep are exact-integer
PopNet outputs). Likely explanation: the earlier fit was calibrated only on
`e >= 257` (all previous sweep points), far above the router's output
buffer depth (`-B 12 -O 12` = 12 flits). Packets that fit entirely inside
the buffer (like this `e=5` command leg) never trigger the credit-based
back-pressure loop that produces the steady-state throttled rate measured
before; small packets likely drain at a different (probably faster,
un-throttled) rate. This means `T_PCIe,leg(S)` is **piecewise**, not
globally linear as the earlier fit implied -- the linear law only holds for
`e` well above the buffer depth. Not investigated further here; flagged for
follow-up if the command-leg latency itself becomes analytically important
(e.g. once IFP work needs a precise small-command-latency term).

## 2026-08-21

**Reverted Channel Count and Switched NAND DMA Speed to ONFI-5.2-Class**

Stopped the in-progress 42-channel PCIe-only characterization run.

Reason:

- The 42-channel configuration was useful as a hypothesis test for making the
  NAND interface faster than PCIe, but it is not a practical SSD design point.
- Based on the paper context shared by senior 榕駿, specifically the HPCA
  InstAttention discussion, a normal SSD channel count should be closer to the
  `8-16` range.
- Therefore, using `42` channels risks proving PCIe sensitivity only under an
  unrealistic SSD organization.

New decision:

- Switch the active characterization back to `8` channels.
- Increase NAND DMA speed instead of channel count.
- Keep `DMAWidth = 8`.
- Use `DMASpeed = 3600` to approximate an ONFI 5.2 / NV-DDR3-class interface.

Active SimpleSSD configs:

```text
SimpleSSD-Standalone/simplessd/config/sample.cfg
SimpleSSD-Standalone/simplessd/config/sample_nocache.cfg
```

Active PAL parameters:

```text
Channel  = 8
DMASpeed = 3600
DMAWidth = 8
```

Approximate aggregate NAND DMA bandwidth:

```text
per-channel ~= 3600 MT/s * 1 byte = 3.6 GB/s
aggregate   ~= 8 * 3.6 GB/s = 28.8 GB/s
```

This exceeds the PCIe-equivalent link target of about `15.8 GB/s`, while using
a practical channel count.

Caveat:

- SimpleSSD does not explicitly toggle an ONFI generation such as `ONFI 5.2`.
- The simulator only uses `DMASpeed` and `DMAWidth` to calculate NAND DMA bus
  timing.
- Array read/program/erase latencies such as `LSBRead`, `MSBRead`, `LSBWrite`,
  and `MSBWrite` remain unchanged.
- Therefore the correct report wording is: "we approximate ONFI 5.2 /
  NV-DDR3-class NAND interface speed by setting `DMASpeed = 3600 MT/s`."

Added hot 8-channel PCIe LegoSim config:

```text
config/legosim_pcie_hot.yml
```

Retargeted the PCIe-only characterization harness to the 8-channel ONFI-5.2
setup:

```text
results/run_pcie_p_characterization.py
```

New outputs:

```text
results/pcie_p_characterization_8ch_onfi52.csv
results/pcie_p_characterization_8ch_onfi52.out
results/pcie_p_characterization_8ch_onfi52.console.out
pcie_p_characterization_8ch_onfi52/
```

The sweep remains:

```text
request size = 4KB, 16KB, 64KB, 256KB, 1MB, 4MB
QD           = 1, 2, 4, 8, 16, 32
cases        = cold PCIe, hot PCIe
total cases  = 72
execution    = sequential, no --jobs
```

### Correction: QD Link Fraction Must Use Wall-Clock Occupancy

The first ONFI-5.2 run used:

```text
p = sum(delayInfo packet delays) / final_cycle
```

This is valid only as a per-packet delay sum diagnostic. It is not a
wall-clock fraction under QD > 1 because multiple PCIe packets can overlap in
time. Therefore the sum of packet residence times can exceed the workload
makespan, producing impossible values such as `p > 1`.

Stopped and archived that invalid partial run under:

```text
results/tmp/invalid_link_sum_as_p_20260821/
```

Updated `results/run_pcie_p_characterization.py` to report:

```text
t_link_sum_cycle          = sum of all delayInfo packet delays
t_link_occupied_cycle     = union of [packet_start, packet_end] intervals
p_link_occupied_fraction  = t_link_occupied_cycle / T_request
link_sum_over_request     = t_link_sum_cycle / T_request
```

The correct `p` for workload-level PCIe occupation is now:

```text
p = p_link_occupied_fraction
```

`link_sum_over_request` may still exceed `1` and should be interpreted only as
an overlap-sensitive packet-delay accumulation metric, not as a time fraction.

### Correction: QD32 Hangs Current SimpleSSD Configuration

The corrected ONFI-5.2 run reached:

```text
cold_pcie_4096_qd32
```

and then stalled in round-1 phase-1 before PopNet. This was not normal PopNet
runtime. The process tree showed `interchiplet`, `simplessd-legosim`, and the
driver all idle, with no `bench.txt` or `delayInfo.txt` produced.

Relevant active SimpleSSD queue limits:

```text
MaxRequestCount = 8
MaxIOCQueue     = 16
MaxIOSQueue     = 16
```

QD16 completed; QD32 deadlocked. Therefore, for the current platform
characterization, QD32 is outside the reliable operating range unless these
queue limits and the LegoSim/SimpleSSD request protocol are changed together.

Stopped the hung QD32 run and changed the default PCIe-only sweep QD list to:

```text
QD = 1, 2, 4, 8, 16
```

The ONFI-5.2 8-channel characterization is now a 60-case sweep:

```text
6 request sizes * 5 QD values * 2 memory modes = 60 cases
```

### Fix: Hot QD8 Phase-1 Protocol Stall

The ONFI-5.2 8-channel PCIe-only sweep later stalled at:

```text
hot_pcie_4096_qd8
```

This was not PopNet runtime. The run never reached phase 2 and produced no
`bench.txt` or `delayInfo.txt`. SimpleSSD had emitted all eight return-path
`[INTERCMD] WRITE` messages, but the two simlets did not finish the round.

Root cause:

```text
LEGOSIM_MICRO/interchiplet/srcs/interchiplet.cpp
```

only parsed protocol commands when a captured output line started exactly with
`[INTERCMD]`. In hot-cache runs, SimpleSSD simulator logging can interleave with
protocol stdout, causing valid `[INTERCMD]` messages to appear later in the same
captured line. Those commands were silently ignored, which could leave one side
waiting for a SYNC forever.

Fix:

```text
parse_command now searches each captured line for "[INTERCMD]" and parses the
command substring even if simulator text appears before it.
```

Validation:

```text
hot 4KB QD8  completed in /tmp/sim_hot_qd8_fix  with 16 bench/delay records
hot 4KB QD16 completed in /tmp/sim_hot_qd16_fix with 32 bench/delay records
```

The killed QD8 row remains recorded as `STOPPED` in the CSV from the aborted
run. A resumed harness run will re-run non-OK rows while preserving completed
OK rows.

### Completed: ONFI-5.2 8-Channel PCIe-Only p Characterization

Resumed the sequential harness after the hot-cache protocol parser fix.

The previously stalled case:

```text
hot_pcie_4096_qd8
```

completed successfully after the fix:

```text
cycles = 19264088
p_wall = 0.554191820552
done_at = 2026-08-22 16:00:33 UTC+8
```

The full 60-case sweep then completed:

```text
status summary: OK=60 RUNNING=0 PENDING=0 FAIL=0 STOPPED=0 total=60
final case: hot_pcie_4194304_qd16
final case cycles = 21728994047
final case p_wall = 0.727770278403
final case done_at = 2026-08-23 10:04:00 UTC+8
```

Validation rule:

```text
expected_records = 2 * QD
bench_records    = expected_records
delay_records    = expected_records
popnet_tx_count  = expected_records
popnet_finished  = expected_records
status           = OK
```

Validation result:

```text
rows = 60
invalid = 0
```

Generated validation and plots:

```text
results/plot_pcie_p_characterization.py
results/pcie_p_characterization_8ch_onfi52_validation.csv
results/pcie_p_characterization_8ch_onfi52_p_heatmap.png
results/pcie_p_characterization_8ch_onfi52_p_lines.png
```

Quick p-wall sanity summary:

```text
cold min p_wall = 0.029400 at 4KB QD8
cold max p_wall = 0.869557 at 4MB QD4
hot  min p_wall = 0.056012 at 64KB QD1
hot  max p_wall = 0.868426 at 16KB QD8
```

Next analysis step:

```text
Use the p_wall heatmap/line plots to identify SSD-dominated and
link-dominated regions, then plug p_wall into the PCIe->UCIe analytical
speedup model before running targeted UCIe validation cases.
```

### HIL Read-Path Instrumentation for Cold QD1 Analytical Model

Instrumented the actual SimpleSSD HIL read path used by the LegoSim cold-read
configuration:

```text
SimpleSSD-Standalone/simplessd/hil/hil.cc
```

The instrumentation logs the HIL READ CPU scheduling boundary and the downstream
ICL call boundary:

```text
HIL_SUBMIT
HIL_BEGIN
HIL_CPU = HIL_BEGIN - HIL_SUBMIT
ICL_BEGIN
ICL_END
ICL_ELAPSED = ICL_END - ICL_BEGIN
HIL_BODY_EXCLUSIVE
HIL_EXCLUSIVE = HIL_CPU + HIL_BODY_EXCLUSIVE
```

This preserves simulator timing; it only adds log output. The SimpleSSD target
was rebuilt successfully:

```text
cmake --build SimpleSSD-Standalone/build --target simplessd-legosim -j$(nproc)
```

Added a `--modes` option to the PCIe characterization harness so this
measurement can run cold-only:

```text
results/run_pcie_p_characterization.py --modes cold --qds 1
```

Ran the cold PCIe QD1 sweep for:

```text
4KB, 16KB, 64KB, 256KB, 1MB, 4MB
```

The first five harness rows completed normally and exactly matched the previous
PCIe QD1 characterization timing. The 4MB run produced the required SimpleSSD
HIL log and the converged final cycle in `interchiplet.out`; the wrapper was
stopped while waiting in the later PopNet convergence phase, so the raw harness
CSV leaves that row as RUNNING. The summary uses the already validated PCIe QD1
4MB timing for the denominator.

Extracted summary:

```text
results/extract_hil_cold_qd1.py
results/hil_cold_qd1_summary.csv
```

Result:

```text
size_bytes  T_HIL(ps)  T_SSD,cold(ps)  T_HIL/T_SSD,cold
4096        1492500    48873986        0.0305377
16384       1492500    50973986        0.0292796
65536       1492500    60073986        0.0248444
262144      1492500    97873986        0.0152492
1048576     1492500    249073986       0.0059922
4194304     1492500    878873986       0.0016982
```

Conclusion for the first-order cold QD1 analytical model:

```text
T_HIL = 1,492,500 ps = 1.4925 us
```

In this current configuration, `T_HIL` is a fixed per-request CPU scheduling
term for `CPU::HIL, CPU::READ`. It does not scale with request size in the
measured QD1 cold-read path. The size-dependent work is downstream of HIL,
primarily inside ICL/FTL/PAL. For large requests, HIL is safely negligible; for
4KB to 16KB requests it is still only about 3 percent of `T_SSD,cold`.

### NAND Type Switched from MLC to SLC

Changed both active SimpleSSD configs from MLC to SLC:

```text
SimpleSSD-Standalone/simplessd/config/sample.cfg
SimpleSSD-Standalone/simplessd/config/sample_nocache.cfg
```

Config change:

```text
NANDType = 1  # MLC
NANDType = 0  # SLC
```

No rebuild is required because this is a runtime config value. With SLC,
SimpleSSD's PAL selects `LatencySLC` and uses the existing LSB timing fields:

```text
LSBRead  = 40000000 ps
LSBWrite = 500000000 ps
```

Any results collected before this point used MLC and should not be mixed with
new SLC results.

### Current QD1 Cold-Read Theoretical Latency Model

Logged the current first-order analytical model after the read-command
payload fix and the NAND-type switch to SLC.

Current assumptions:

```text
QD                         = 1
read type                  = cold read
NANDType                   = SLC
logical page size           = 32 KB
physical NAND page size     = 16 KB
DMASpeed                   = 3600 MT/s
DMAWidth                   = 8 bits
SSD embedded DRAM page size = 4 KB
SSD DRAM bandwidth          = 6.4 GB/s
PCIe modeled bandwidth      = 16 GB/s
read-command payload        = 64 B
```

Define:

```text
N(S) = ceil(S / 32768)
```

Full decomposition:

```text
T_read(S)
  = T_PCIe,send(64B)
  + T_BIL
  + T_HIL
  + T_ICL,CPU
  + T_ICL,DRAM(S)
  + T_FTL,CPU(S)
  + T_FTL,DRAM(S)
  + T_PAL(S)
  + T_PCIe,receive(S)
```

Current derived SSD-side terms:

```text
T_BIL = 0

T_HIL = 1.4925 us

T_ICL,CPU = 0.3525 us

T_ICL,DRAM(S) = 5.6 * N(S) us
```

`T_ICL,DRAM` is the SimpleSSD embedded-DRAM / I/O-buffer traffic timing
surrogate in the no-cache ICL read path, not literal modeled data movement:

```text
8 DRAM pages/LPN * (18 ns + 42 ns + 4096 B / 6.4 GB/s)
= 8 * 0.7 us
= 5.6 us/LPN
```

FTL terms:

```text
T_FTL,CPU(S) = 1.285 * N(S) us
```

from:

```text
(57 + 62 + 395) cycles * 2.5 ns = 1.285 us/LPN
```

```text
T_FTL,DRAM(S) = 0.7 * N(S) us
```

because each LPN performs one 8-byte mapping-table lookup, and SimpleDRAM
charges one full 4KB DRAM-page access:

```text
18 ns + 42 ns + 4096 B / 6.4 GB/s = 0.7 us
```

PAL term under QD1 + SLC:

```text
T_PAL(S)
  = N(S) * (
      T_addr
    + T_wait
    + T_DMA0
    + T_MEM
    + T_ANTI
    + T_DMA1
    )
```

with:

```text
T_addr = 0
T_wait = 0
T_DMA0 ~= 0.001854 us
T_MEM = 40 us
T_ANTI = T_DMA0 ~= 0.001854 us
T_DMA1 ~= 4.3403 us
```

Therefore:

```text
T_PAL(S) ~= 44.344 * N(S) us
```

Combining SSD-side terms:

```text
T_SSD,QD1(S)
  = 1.845 + 51.929 * ceil(S / 32768) us
```

PCIe hardware model:

```text
T_PCIe,send(64B)
  = L_send + 64 / BW_PCIe

T_PCIe,receive(S)
  = L_receive + S / BW_PCIe
```

With:

```text
BW_PCIe = 16 GB/s
```

the QD1 cold-read model is:

```text
T_read,QD1(S)
  = 1.849
  + 51.929 * ceil(S / 32768)
  + S / 16000
  + L_send
  + L_receive
  us
```

where `S` is in bytes and `S / 16000` is in microseconds.

If later justified as a symmetric one-way fixed PCIe latency:

```text
T_read,QD1(S)
  = 1.849
  + 51.929 * ceil(S / 32768)
  + S / 16000
  + 2 * L_PCIe
  us
```

Important unresolved term:

```text
L_PCIe is currently unresolved.
```

Do not assign an arbitrary fixed PCIe latency until it is justified from either
the actual PopNet small-packet behavior or an explicitly chosen hardware
assumption. The known measured command-leg delay for the current 64B read
request is a simulator observation, but it has not yet been cleanly separated
into fixed latency plus serialization time.

### QD1 PCIe Theoretical Model Reasoning and Asymptotic p Bound

This entry records the reasoning path behind the current QD1 PCIe theoretical
model. The purpose is to preserve which pieces came from code, which pieces
were measured empirically, and which gaps remain unresolved.

#### 1. Original Starting Point

The original PCIe transfer model used ideal serialization:

```text
T_PCIe(S) = S / BW_PCIe
```

With:

```text
BW_PCIe = 16 GB/s
```

a 4MB one-way transfer would be:

```text
4 MB / 16 GB/s ~= 262 us
```

But previous PopNet measurements showed that one 4MB one-way PCIe transfer
took about:

```text
961 us
```

This is about:

```text
961 / 262 ~= 3.67x
```

larger than ideal serialization. Therefore `S / BW_PCIe` is not adequate for
the current simulator behavior.

#### 2. Why PopNet Behaves Differently

PopNet does not send an `S`-byte payload as one continuous object. It converts
the payload into flits.

Under the current PCIe configuration:

```text
payload per flit = 16 B
```

Therefore the packet flit count is:

```text
e(S) = ceil(S / 16) + 1
```

where the `+1` is the head flit.

The modeling chain is therefore:

```text
S -> e(S) -> T_PopNet
```

#### 3. Dense PopNet Sweep

To determine the relationship between `e` and latency, an isolated QD1 /
one-flow / one-hop PCIe sweep was used with dense sampling at very small packet
sizes, especially around the router buffer depth.

Measured examples:

```text
e   T(cycles)
2   45
3   47
4   47
5   49
...
12  56
13  88
24  100
25  132
36  145
37  176
48  190
49  220
```

Important observation:

```text
The latency is not globally linear.
```

Large jumps occur at:

```text
e = 13, 25, 37, 49, ...
```

or every 12 flits.

#### 4. Code-Level Explanation of the 12-Flit Period

The 12-flit periodicity is explained by PopNet's credit-based flow control.

`sw_arbitration()` allows a flit to advance only when both output credit
counters are positive. These counters are initialized from the configured
buffer sizes:

```text
B = 12
O = 12
```

Therefore up to 12 flits can be outstanding before credit is exhausted.

When the destination receives a flit, it returns a `CREDIT_` message. Until a
credit returns, the sender cannot advance another flit once its 12 credits are
exhausted.

Hence the number of credit-window boundaries crossed by a packet is:

```text
N_stall(e) = floor((e - 1) / 12)
```

This expression is derived from the observed and code-verified 12-flit credit
capacity. It is not an arbitrary regression term.

#### 5. Current PopNet Latency Approximation

The current mechanistic empirical approximation is:

```text
T(e) ~= 45 + (e - 2) + 32 * floor((e - 1) / 12)
```

Interpretation:

```text
45
  small-packet/startup anchor

(e - 2)
  baseline growth with additional flits

32 * floor((e - 1) / 12)
  periodic credit-stall penalty
```

Coefficient status:

```text
12-flit period
  code-derived and physically explained by credit counters

32-cycle stall penalty
  empirical; dense measurements show approximately this additional penalty per
  exhausted credit window, but it has not yet been derived from first principles

45-cycle startup anchor
  empirical; based on the measured small-packet latency at e = 2, with internal
  routing / VC / switch / wire decomposition still unresolved
```

Therefore this is a mechanistic empirical approximation, not a fully
first-principles model.

Substituting:

```text
e(S) = ceil(S / 16) + 1
```

gives:

```text
T_PCIe(S)
  ~= 44
   + ceil(S / 16)
   + 32 * floor(ceil(S / 16) / 12)
  ns
```

under:

```text
QD1 / single-flow / one-hop / no-contention PCIe
```

The periodic model achieved roughly:

```text
RMSE ~= 1.8 cycles
maximum observed error ~= 3 cycles
```

across the dense sweep.

#### 6. Current SSD-Side QD1 Model

Define:

```text
N_LPN(S) = ceil(S / 32768)
```

The current cold-read SSD decomposition is:

```text
T_SSD(S)
  = T_HIL
  + T_ICL,CPU
  + T_ICL,DRAM(S)
  + T_FTL,CPU(S)
  + T_FTL,DRAM(S)
  + T_PAL(S)
```

Current derived values:

```text
T_HIL = 1.4925 us

T_ICL,CPU = 0.3525 us

T_ICL,DRAM(S) = 5.6 * ceil(S / 32768) us
```

The 5.6 us/LPN term is SimpleSSD's embedded-DRAM / I/O-buffer traffic timing
surrogate, not literal modeled data movement.

```text
T_FTL,CPU(S) = 1.285 * ceil(S / 32768) us

T_FTL,DRAM(S) = 0.7 * ceil(S / 32768) us
```

The `T_FTL,DRAM` term corresponds to the 8-byte mapping-table lookup. SimpleDRAM
charges one full 4KB DRAM-page access for that lookup.

Under current QD1 + SLC assumptions:

```text
T_PAL(S) ~= 44.344 * ceil(S / 32768) us
```

Therefore:

```text
T_SSD(S)
  ~= 1.845 + 51.929 * ceil(S / 32768) us
```

#### 7. Definition of p(S)

The PCIe latency fraction is now defined using the PopNet-aware receive
latency:

```text
p(S) = T_PCIe(S) / (T_PCIe(S) + T_SSD(S))
```

Since the PCIe expression is in ns, convert it to us:

```text
p(S)
  = (T_PCIe(S) / 1000)
    /
    (
      T_PCIe(S) / 1000
      + 1.845
      + 51.929 * ceil(S / 32768)
    )
```

#### 8. Asymptotic Derivation

For large `S`:

```text
ceil(S / 16) ~ S / 16
```

and:

```text
floor(ceil(S / 16) / 12) ~ S / 192
```

Therefore:

```text
T_PCIe(S)
  ~ S / 16 + 32 * S / 192
  = S / 16 + S / 6
  = 11S / 48
  ns
```

Converting to us:

```text
T_PCIe(S) ~ 11S / 48000 us
```

Meanwhile:

```text
T_SSD(S) ~ (51.929 / 32768) * S us
```

Therefore:

```text
lim_{S -> infinity} p(S)
  =
  (11 / 48000)
  /
  (
    11 / 48000
    + 51.929 / 32768
  )
```

Numerically:

```text
11 / 48000 ~= 0.00022917 us/B

51.929 / 32768 ~= 0.0015844 us/B
```

Hence:

```text
lim_{S -> infinity} p(S) ~= 0.126 ~= 12.6%
```

#### 9. Current Conclusion

The previous ideal-bandwidth model produced an asymptotic PCIe fraction of
only about:

```text
3.8%
```

because it assumed:

```text
T_PCIe(S) = S / 16 GB/s
```

The PopNet-aware model instead predicts an asymptotic PCIe contribution of
about:

```text
12.6%
```

under the current QD1 assumptions.

The increase comes from PopNet's lower effective steady-state throughput,
caused by the 12-flit credit window and periodic credit-stall penalties.

Remaining open discrepancy:

```text
The current PopNet-aware theoretical model still does not recover the previous
experimental 4MB QD1 cold PCIe result:

measured old p ~= 68.6%
```

That old result came from:

```text
results/pcie_p_characterization_8ch_onfi52.csv
cold, pcie, size = 4194304, qd = 1
final_cycle              = 2801336986
t_link_occupied_cycle    = 1922463000
p_link_occupied_fraction = 0.686266239873
```

This mismatch remains explicitly open. It should not be explained away until
the theoretical SSD-side decomposition, the PopNet timing model, and the old
measured characterization path are reconciled against the same simulator
configuration and same read-link semantics.

### Current Corrected QD1 Cold PCIe Sweep: SLC + 64B Read Command

Reran the QD1 cold PCIe sweep after the two current semantic changes:

```text
NANDType = SLC
read request leg = 64B command
read response leg = S-byte data
```

Fresh builds before the run:

```text
cmake --build SimpleSSD-Standalone/build --target simplessd-legosim -j$(nproc)

c++ -std=c++17 \
  PyTorchSim/TOGSim/tests/DramLegoSim_driver.cc \
  PyTorchSim/TOGSim/tests/DramLegoSim_base_stub.cc \
  PyTorchSim/TOGSim/src/DramLegoSim.cc \
  -IPyTorchSim/TOGSim/tests/stubs -IPyTorchSim/TOGSim/include \
  -IPyTorchSim/TOGSim/include/scheduler \
  -IPyTorchSim/TOGSim/extern/ramulator2/src \
  -o PyTorchSim/TOGSim/tests/build/dram_legosim_driver
```

Harness:

```text
python3 -u results/run_pcie_p_characterization.py \
  --modes cold \
  --qds 1 \
  --sizes 4KB,16KB,64KB,256KB,1MB,4MB \
  --run-root pcie_qd1_cold_slc_cmd64_20260827 \
  --csv results/pcie_qd1_cold_slc_cmd64_20260827.csv \
  --log results/pcie_qd1_cold_slc_cmd64_20260827.out \
  --force
```

Extractor:

```text
results/extract_qd1_cold_slc_cmd64.py
results/pcie_qd1_cold_slc_cmd64_20260827_per_leg.csv
```

Measured per-leg results:

```text
size      req_flits  req_link_us  resp_flits  resp_link_us  SSD_us      total_us     p
4KB       5          0.049        257         0.975         48.873986   49.897986    0.020522
16KB      5          0.049        1025        3.791         50.973986   54.813986    0.070055
64KB      5          0.049        4097        15.055        60.073986   75.177986    0.200910
256KB     5          0.049        16385       60.111        97.873986   158.033986   0.380678
1MB       5          0.049        65537       240.335       249.073986  489.457986   0.491123
4MB       5          0.049        262145      961.231       853.873986  1815.153986  0.529586
```

Immediate interpretation:

```text
The corrected 4MB QD1 measured p is 52.96%.
```

This is lower than the old symmetric-link 4MB QD1 cold result:

```text
old p = 68.63%
```

but it is still far above the current theoretical asymptotic bound:

```text
theoretical p_limit ~= 12.6%
```

Therefore the request-leg correction explains part of the old p value but not
the whole discrepancy.

The current main identified modeling error is on the SSD side:

```text
T_SSD(S) = 1.845 + 51.929 * ceil(S / 32768) us
```

incorrectly serializes all LPN subrequests. The actual `ICL::read()` loop
starts each subrequest from the same original `tick` and then takes:

```text
finishedAt = max(finishedAt, beginAt)
```

so LPN-level work is overlapped through SimpleSSD's FTL/PAL scheduling rather
than summed naively. This is why the serialized model predicts a 4MB SSD time
of about `6648.757 us`, while the corrected measured 4MB SSD time is only:

```text
853.873986 us
```

Next analytical task:

```text
replace the serialized SSD-side model with a wave/overlap-aware model or fit
T_SSD(S) from measured SimpleSSD service time before using it to predict p(S).
```

**Result Archive, Timescale Fix, and Analytical Model Checkpoint**

### Archived Stale Results

Moved old generated results into:

```text
results/tmp/pre_timescale_fix_20260821/
```

The archive contains:

- `top_level_results/`: old CSV, PNG, and `.out` files from PCIe/UCIe,
  hot/cold, size/QD, 1MB-QD, and 4MiB-128MiB sweeps.
- `run_dirs/`: old generated simulation directories, including
  `size_qd_runs`, `link_scaling_*`, and `llama70b_layer_workloads_*`.

Runnable analysis/harness scripts remain directly under `results/`.

These archived measurements were collected before the PopNet/SimpleSSD
timescale correction below, so they should not be used for physical
conclusions without rerunning.

### Analytical Model Basis

Current request-level read model:

```text
T_request_read(S) = T_link_req(S) + T_SSD_read(S) + T_link_resp(S)
```

For PCIe vs UCIe comparison:

```text
Speedup(S) = (T_SSD_read(S) + T_PCIe_req(S) + T_PCIe_resp(S))
           / (T_SSD_read(S) + T_UCIe_req(S) + T_UCIe_resp(S))
```

The useful diagnostic fraction is:

```text
p = (T_PCIe_req(S) + T_PCIe_resp(S)) / T_request_pcie(S)
```

If `p` is small, replacing PCIe with UCIe cannot produce a large speedup.

### Link and NAND Bandwidth Reasoning

The current active link swap is modeled through PopNet/interchiplet configs,
not SimpleSSD's native NVMe PCIe fields.

- PCIe-equivalent target: PCIe 5.0 x4, about `15.8 GB/s` effective.
- UCIe-equivalent target: about `64 GB/s`.
- Current SimpleSSD NAND interface baseline:

```text
Channel = 8
DMASpeed = 400 MT/s
DMAWidth = 8 bits
```

Assuming `DMASpeed * DMAWidth` is per channel:

```text
BW_NAND_interface ~= 8 * 400 MB/s = 3.2 GB/s
```

This is below the PCIe-equivalent bandwidth, so the baseline SSD may be unable
to feed enough data to saturate PCIe.

Added 42-channel configs as a hypothesis test:

```text
BW_NAND_interface_42ch ~= 42 * 400 MB/s = 16.8 GB/s
```

This is slightly above PCIe 5.0 x4 effective bandwidth, making PCIe saturation
more plausible if other SSD-side scheduling and NAND-array terms do not
dominate.

### Timescale Mismatch and Fix

Found a unit mismatch:

- SimpleSSD simulation ticks are reported in ps.
- PopNet link timing is modeled as ns-scale cycles.
- Previous phase-2 configs used `clock_rate: 1`, which effectively treated
  PopNet ns cycles as SimpleSSD ps ticks and underweighted link latency by
  about `1000x`.

Fixed phase-2 config files by setting:

```text
clock_rate: 0.001
```

This converts:

- benchmark timestamps: SimpleSSD ps -> PopNet ns
- delayInfo timing: PopNet ns -> SimpleSSD ps

Updated result parsers to multiply raw `delayInfo.txt` PopNet cycles by
`1000.0` before reporting interconnect time in SimpleSSD cycles/ps.

Smoke test after the fix:

```text
config/legosim_pcie.yml, 4KB read, final cycle = 85576878
delayInfo raw PopNet cycles = 976 + 975
scaled link contribution ~= 1,951,000 ps
```

### Long Multi-Job Run Killed

The long `link_scaling_4m_128m_no_timeout_20260820` run was stopped.

Actions:

- Terminated the Python harness process group.
- Terminated surviving `interchiplet`/`popnet` child process groups.
- Verified no matching
  `run_link_scaling_extrapolate|link_scaling_4m_128m_no_timeout_20260820|interchiplet|popnet`
  processes remained.

The old partial outputs from that run are archived under
`results/tmp/pre_timescale_fix_20260821/`.

**PCIe-Only Link-Fraction Characterization Started**

Postponed direct PCIe-vs-UCIe comparison and started a PCIe-only
characterization sweep on the 42-channel SSD configuration.

Goal:

```text
(S, QD, hot/cold) -> p

p = T_link / T_request
```

Measured terms:

```text
T_request = final completion cycle
T_link    = sum(delayInfo.txt raw PopNet delays) * 1000
T_SSD     = T_request - T_link
p         = T_link / T_request
```

Sweep:

```text
request size = 4KB, 16KB, 64KB, 256KB, 1MB, 4MB
QD           = 1, 2, 4, 8, 16, 32
cases        = cold PCIe, hot PCIe
SSD config   = 42-channel
total cases  = 72
```

Harness:

```text
results/run_pcie_p_characterization.py
```

Outputs:

```text
results/pcie_p_characterization_42ch.csv
results/pcie_p_characterization_42ch.out
results/pcie_p_characterization_42ch.console.out
pcie_p_characterization_42ch/
```

The harness runs sequentially only. No `--jobs` parallelism is used, so PopNet
does not contend with other cases from this sweep.

`monitor.sh` now reads the characterization CSV and reports every planned case
as `PENDING`, `RUNNING`, `OK`, or `FAIL`. Completed cases show `done_at_taipei`
in UTC+8 (`Asia/Taipei`).

First confirmed completed case:

```text
cold_pcie_4096_qd1
T_request = 85576878
T_link    = 1951000
p         = 0.022798214256
done_at   = 2026-08-21 20:14:45 UTC+8
```

## 2026-08-20

**Llama 3 70B Layer-Weight QD1 Harness**

Added `results/run_llama70b_layer_qd1.py` for the workload-derived experiment:
one Llama 3 70B transformer block's FP16 weights as a single QD1 transfer.

Default workload:

- request size: `1,711,300,000` bytes
- queue depth: `1`
- cases: cold PCIe, cold UCIe, cache-hot PCIe, cache-hot UCIe
- run directories: created under the current working directory by default
- summary CSV: `results/llama70b_layer_qd1.csv`

The harness launches the four cases concurrently by default (`--jobs 4`) and
generates one isolated temporary run subdirectory per case. It also raises the
generated PopNet `-T` window to `1e13` cycles to avoid the known large-request
transaction-drop failure mode.

Validation:

- Smoke-tested the harness with `--size 4096 --jobs 4` in `/tmp`.
- All four cases completed and validated `bench.txt`, `delayInfo.txt`, and
  PopNet `Transaction count == total finished == 2`.

Follow-up 8-case workload harness:

- Added `results/run_llama70b_layer_workloads.py`.
- Workload 1: one monolithic QD1 read, `1,711,300,000` bytes.
- Workload 2: seven sequential QD1 matrix reads:
  Q, K, V, O, gate, up, down.
- Cases: cold/hot x PCIe/UCIe for both workloads, launched with `--jobs 8`.
- Smoke-tested all eight cases with 4KB request sizes in `/tmp`; all completed.

Full-size attempt:

- Started `python3 results/run_llama70b_layer_workloads.py --jobs 8`.
- Run directory: `llama70b_layer_workloads_20260820_092950`.
- All eight first-stage SSD/NPU runs reached PopNet phase 2.
- No PopNet case finished after several minutes; logs remained at
  `Transaction count: 2` with no `total finished`.
- Stopped the attempt with Ctrl-C before it burned the machine indefinitely.
  Conclusion: the harness is valid, but full GB-scale payloads through raw
  PopNet are not practical as an interactive 8-way run.

Scaling/extrapolation follow-up:

- Added `results/run_link_scaling_extrapolate.py` to measure bounded QD1
  scaling sizes and extrapolate Llama layer-sized transfers.
- A controlled single-worker `4MiB` cold PCIe probe timed out after `600s`
  before PopNet completed phase 2. This makes even the lower end of the
  proposed 4MiB-64MiB PopNet validation grid impractical in this environment.
- Added `results/extrapolate_llama70b_from_existing.py` to fit from the
  already validated QD1 sweep data through 4MiB:
  `results/pcie_vs_ucie_throughput.csv` and
  `results/pcie_vs_ucie_hot_qd1.csv`.
- Generated:
  - `results/llama70b_layer_existing_extrapolation.csv`
  - `results/llama70b_layer_existing_extrapolation.png`
- Fit uses the large-size tail (`>=512KiB`) by default. Cold total-cycle fits
  are strong (`R^2 ~= 0.997`). Hot total-cycle fits are weaker (`R^2 ~= 0.838`)
  because the SimpleSSD cache-hit path has the known large-size discontinuity.
- Estimated UCIe/PCIe end-to-end speedup remains about `1.0013x-1.0017x`;
  estimated interconnect fraction remains below about `0.23%`.

No-timeout PopNet scaling run:

- User requested accuracy over runtime, with timeout disabled and sizes through
  at least 64MiB/128MiB.
- Updated `results/run_link_scaling_extrapolate.py` so `--timeout 0` disables
  per-case timeout; timeout is now disabled by default.
- Started persistent single-worker run:
  `python3 -u results/run_link_scaling_extrapolate.py --sizes 4MiB,8MiB,16MiB,32MiB,64MiB,128MiB --jobs 1 --timeout 0`.
- Supervisor PID at launch: `333444` shell / `333445` Python.
- Run root: `link_scaling_4m_128m_no_timeout_20260820`.
- Progress log: `results/link_scaling_4m_128m_no_timeout_20260820.out`.
- Measurement CSV: `results/link_scaling_4m_128m_measurements_20260820.csv`.
- Estimate CSV: `results/llama70b_layer_4m_128m_estimates_20260820.csv`.

## 2026-08-16

**QD1 Cold NAND vs Cache-Hot Read Sweep**

Ran the requested QD1 4KB-4MB comparison with the corrected preconditioned
read path under two SSD modes:

- cold NAND: `sample_nocache.cfg`
- cache-hot: cache-enabled `sample.cfg` after the preconditioning write

Results are written to:

- `results/pcie_vs_ucie_hot_qd1.csv`
- `results/pcie_vs_ucie_hot_vs_cold_qd1_summary.csv`
- `results/pcie_vs_ucie_hot_vs_cold_qd1.png`
- `results/plot_hot_vs_cold_qd1.py`

Validation:

- Every hot run generated `2` bench records.
- Every hot run validated PopNet `Transaction count: 2` and
  `total finished: 2`.

Finding:

- Cache-hot reads are much faster than cold NAND for 4KB-16KB, and UCIe gain
  is more visible there: 0.0285%, 0.0487%, 0.0779%.
- At 32KB and above, SimpleSSD's cache-hit path shows a large internal
  service cost. The 32KB hot read log confirms `ICL::GenericCache: READ |
  Cache hit`, but the cache-hit service takes about 540M cycles. This means
  the cache-hot experiment is **not** an ideal "zero-latency staged data"
  model. It is specifically "SimpleSSD ICL cache-hit behavior after
  preconditioning write."
- The hot/cached mode still does not produce a PCIe-bottlenecked workload.
  Best hot gain in this QD1 sweep is 0.1287% at 2MB.

**Corrected Size x Queue-Depth Sweep**

Added a resumable two-dimensional sweep and plotter:

- `results/run_size_qd_sweep.py`
- `results/plot_size_qd_sweep.py`

Ran the first bounded grid:

- request size: 4KB, 16KB, 64KB, 256KB, 1MB
- queue depth: 1, 2, 4, 8
- variants: PCIe and UCIe

Results are written to:

- `results/pcie_vs_ucie_size_qd.csv`
- `results/pcie_vs_ucie_size_qd.png`
- raw run directories under `results/size_qd_runs/`

Validation:

- Each point validated `2 * QD` bench records.
- Each point validated PopNet `Transaction count` and `total finished` equal
  to `2 * QD`.

Finding:

- Throughput increases with QD and request size, so the sweep machinery is
  measuring useful concurrency behavior.
- UCIe remains nearly identical to PCIe end-to-end. The best UCIe/PCIe
  throughput ratio in this grid is `1.0012x` at 1MB/QD1.
- Therefore this corrected no-cache NAND-read grid still does not expose a
  PCIe-bottlenecked workload. The next direction should be either higher
  flash parallelism / cache-like IFP behavior or a workload that reuses SSD
  data after the initial flash read so the interconnect dominates more of the
  total time.

Follow-up 1MB-only QD line sweep:

- Extended the 1MB points through QD16 for both PCIe and UCIe.
- Generated `results/pcie_vs_ucie_1mb_qd_line.png`.
- QD32 was started after QD16 completed, but stopped because QD16 already
  took many minutes per variant in PopNet. QD32/QD64/QD128/QD256 are therefore
  not practical interactive runs with the current PopNet configuration.
- 1MB/QD16 result: PCIe `0.0050097` B/cycle, UCIe `0.0050106` B/cycle,
  UCIe/PCIe `1.00017x`, PCIe utilization only `0.0313%` of the modeled
  16 B/cycle PCIe peak. The QD trend still does not approach PCIe saturation.

**Corrected QD1 PCIe/UCIe Full Size Sweep Complete**

Ran the full queue-depth-1 PCIe/UCIe size sweep again after the Milestone 9
fixes: preconditioning writes before reads and `sample_nocache.cfg` to force
the measured read through NAND instead of the ICL cache.

Command pattern: temporary copies of `config/legosim_{pcie,ucie}.yml` with
NPU args set to `["<request_bytes>"]` and SimpleSSD `iterations = 1`.

Results are written to:

- `results/pcie_vs_ucie_throughput.csv`
- `results/pcie_vs_ucie_comparison.png`

| Size | PCIe final cycle | UCIe final cycle | Total gain | PCIe response delay | UCIe response delay |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 4KB | 83,627,829 | 83,626,412 | 0.0017% | 975 | 267 |
| 8KB | 84,329,686 | 84,326,924 | 0.0033% | 1,904 | 523 |
| 16KB | 85,733,461 | 85,727,948 | 0.0064% | 3,792 | 1,035 |
| 32KB | 88,540,949 | 88,529,996 | 0.0124% | 7,536 | 2,059 |
| 64KB | 94,855,989 | 94,834,092 | 0.0231% | 15,056 | 4,107 |
| 128KB | 107,486,006 | 107,442,284 | 0.0407% | 30,064 | 8,203 |
| 256KB | 132,746,101 | 132,658,668 | 0.0659% | 60,112 | 16,395 |
| 512KB | 211,962,108 | 211,787,314 | 0.0825% | 120,176 | 32,779 |
| 1MB | 291,298,305 | 290,948,728 | 0.1200% | 240,336 | 65,547 |
| 2MB | 489,049,826 | 488,350,745 | 0.1429% | 480,624 | 131,083 |
| 4MB | 945,473,743 | 944,075,590 | 0.1479% | 961,232 | 262,155 |

Validation:

- All 22 runs generated `2` bench records as expected for QD1: one request leg
  and one response leg.
- PopNet validity checks passed for every point: `Transaction count: 2` and
  `total finished: 2`.

Interpretation:

- The corrected run still shows UCIe reducing the modeled interconnect delay
  by about 3.6x.
- End-to-end gain remains small at QD1 because the corrected workload is now
  dominated by real SimpleSSD NAND service time.
- These numbers replace the old 2026-07-31 sweep results, which were based on
  non-representative unwritten-LPN reads.

## 2026-08-06

**Milestone 7 Basic Queue-Depth Path Implemented**

Implemented the first working multi-outstanding-request path needed to search
for a PCIe bottleneck.

### What Changed

- LegoSim normal READ/WRITE pairing now includes `desc` in the match key, not
  only source/destination/size. This prevents same-size concurrent transfers
  from being paired with the wrong peer command.
- LegoSim normal READ/WRITE acknowledgments now emit an optional descriptor:
  `[INTERCMD] SYNC <cycle> <desc>`. Existing parsers that read only `<cycle>`
  remain compatible; the new NPU/SimpleSSD paths use the descriptor.
- `DramLegoSim` now tracks request-arrival and response-completion state in
  descriptor-indexed pending queues instead of one FIFO pending queue.
- Replaced `DramLegoSim`'s stdin reader with a POSIX `read()` buffer. Root
  cause found during QD3 debugging: mixing `poll()` with `std::getline()` can
  leave extra SYNC lines in the C++ stream buffer while `poll()` sees no fd
  data, causing the NPU process to wait forever.
- `dram_legosim_driver` now accepts:
  `dram_legosim_driver <request_bytes> <request_count> [issue_gap]`.
- `simplessd-legosim` now treats `iterations` as queue depth for one batch:
  it emits all request legs, collects descriptor-bearing arrival SYNCs, submits
  all timed BIOs, emits response legs as storage completions occur, collects
  descriptor-bearing return SYNCs, and reports final `CYCLE` as the max return
  cycle.
- Descriptors use `8, 16, 24, ...`, avoiding LegoSim's reserved low descriptor
  bits (`ACK`, `PRE_SYNC`, `POST_SYNC`) and high control bits.

### Validation

- Rebuilt `interchiplet`, `simplessd-legosim`, and `dram_legosim_driver`.
- Unit test passes:
  `DramLegoSim_unit` emits descriptor `8` and completes.
- Direct NPU-driver QD4 stdin test passes, including out-of-order response
  SYNC descriptors.
- Full LegoSim + SimpleSSD + PopNet QD4 smoke passes:
  - temporary config: NPU args `["4096", "4"]`, SimpleSSD iterations `"4"`
  - 8 bench records generated (`4` request legs + `4` response legs)
  - descriptors in `bench.txt`: `8, 16, 24, 32`
  - round 1: `9,451,110` cycles
  - round 2: `9,451,374` cycles
  - convergence difference: `0.0027932446647439832%`

### Next

- Run the actual queue-depth sweep on `config/legosim_pcie.yml` vs
  `config/legosim_ucie.yml`, using the corrected cache-disabled read workload.
  Sweep `request_count` / SimpleSSD `iterations` together (`1, 2, 4, 8, ...`)
  and compare batch makespan/throughput to find where PCIe flattens before
  UCIe.

## 2026-07-31

**Corrected Cold-NAND Read Workload Identified**

Follow-up to Milestone 9 after the unwritten-LPN bug was found.

### What Changed

- Updated `SimpleSSD-Standalone/sim/legosim_main.cc`: a `read` benchmark now
  first submits an untimed/preconditioning WRITE to the same logical offset,
  then submits the timed READ to that offset. The completion cycle returned to
  LegoSim is computed from the timed operation's service latency added to the
  interconnect arrival cycle, so the warmup write creates the FTL mapping
  without being included in the reported read latency.
- Added `SimpleSSD-Standalone/simplessd/config/sample_nocache.cfg` and pointed
  `config/legosim_pcie.yml` / `config/legosim_ucie.yml` at it. This disables
  ICL read caching, read prefetch, and write caching. That is necessary because
  a preconditioning write with `sample.cfg` also warms the ICL cache; the
  measured read then becomes an ICL cache hit and still bypasses NAND.

### Sanity Check

- Built `simplessd-legosim` in `/tmp/sim_simplessd_build` because the in-tree
  CMake cache was created under `/Users/csld/...`.
- Direct synthetic-SYNC run, 4KB, `sample_nocache.cfg`, confirmed the measured
  read now reaches the NAND path:
  - preconditioning write logs `PAL::PALOLD: WRITE`
  - measured read logs `PAL::PALOLD: READ`
  - SimpleSSD emits the return-path command at cycle `83626877` for the timed
    4KB read.
- Full PCIe/UCIe rerun is blocked in this Linux workspace: the checked-in
  `interchiplet`, `popnet`, and `dram_legosim_driver` binaries are Mach-O
  arm64; rebuilding LegoSim/PopNet failed because Boost development
  libraries are missing, and `sudo apt-get install libboost-all-dev` could not
  proceed without an interactive password.

### Workload Direction

- A valid flash-backed PCIe-bottleneck workload is not "larger single read" in
  this current queue-depth-1 harness. The corrected 4KB cold NAND read already
  spends ~83.6M cycles in storage service, far above the ~1K-cycle PCIe
  interconnect scale previously measured at 4KB. Increasing size may raise
  interconnect delay, but it also raises flash work.
- The workload most likely to bottleneck PCIe is therefore: cache-disabled,
  prewritten, many outstanding independent reads, with offsets distributed
  across enough logical pages/channels/planes to exploit SimpleSSD's internal
  flash parallelism. That requires Milestone 7 (real queue depth / descriptors)
  before the PCIe-vs-UCIe gain can be fairly measured in a bandwidth-bound
  regime.

**Root Cause of the 4KB-32KB Flat Region + Concurrency Feasibility**

Same-day follow-up to the entry directly below. While explaining the sweep
results, a sharp question surfaced a real problem with the sweep itself:
across 4KB-32KB the numbers barely move, then grow almost perfectly linearly
from 64KB on -- multiple explanations were tried and rejected before finding
the actual mechanism. Separately, worked out whether Milestone 7
(concurrency) is architecturally possible at all given LegoSim's one-pipe-
per-simlet design.

### Finding 1: none of the measured "flash time" is real NAND timing

- Root cause: every benchmark run reads from the same address (offset 0),
  which has **never been written** -- each run issues exactly one op,
  `iterations=1`, `op` defaults to `OP_READ`, and `nextOffset` never advances.
- `PageMapping::readInternal` (`SimpleSSD-Standalone/simplessd/ftl/page_mapping.cc`)
  does `table.find(req.lpn)`; if the LPN was never written this returns
  `table.end()` and **the entire NAND-timing code path is skipped** -- there
  is no `else` branch. `tick` is left essentially unchanged.
- Consequence: `LSBRead`/`MSBRead`/etc. from `sample.cfg` (tens of
  microseconds per op, confirmed real NAND-datasheet-scale values once the
  tick unit was resolved -- see below) were **never actually invoked** in any
  run so far, including the whole 2026-07-29/07-31 PCIe-vs-UCIe sweep.
- Fix identified and confirmed valid: `writeInternal` has an explicit `else`
  branch for the unmapped case (creates a new mapping, proceeds to real PAL
  write timing regardless of prior state) -- so "write once (untimed), then
  read the same offset (timed)" is a correct precondition pattern. Captured
  as new **Milestone 9** in `PLAN.md`, not yet implemented.

### Finding 2: the real driver of the flat-then-linear pattern is ICL cache-line granularity, not NAND/channel parallelism

- Initially suspected the 128-way (`Channel x Package x Die x Plane` =
  8x4x2x2) parallelism ceiling explained the shape; this was wrong -- the
  observed transition (flat through 32KB, linear from 64KB) doesn't line up
  with 128 pages (2MB), or with the theoretical free-parallel width computed
  from `ioUnitInPage` (16 pages / 256KB) either.
- Actual mechanism, confirmed in `simplessd/icl/generic_cache.cc`: ICL read
  caching is enabled (`EnableReadCache = 1`), and cache line size =
  `pageSize(16384) x plane(2) = 32768 bytes = 32KB` (multi-plane operation is
  forced into the superblock/cacheline size calculation). The `readList` loop
  calls `pFTL->read()` once per missed cache line.
  - 4KB/8KB/16KB/32KB all fit inside **one** cache line -> one cache-miss
    handling pass each, roughly constant (tiny) overhead regardless of exact
    size within that range.
  - 64KB spans 2 cache lines, 128KB spans 4, etc. -- each additional cache
    line adds its own handling cost, compounding to the near-perfectly-linear
    growth seen from 64KB up through 4MB.
- Also resolved, as a side finding: 1 engine tick = 1 picosecond, confirmed
  via `pal/config.cc`: `tCK = 1.f / (dmaSpeed * 1048576) * 1e12`. `LSBRead =
  40000000` therefore really is 40µs, `Erase = 3500000000` really is 3.5ms --
  both consistent with real NAND datasheet magnitudes, once the correct
  (unexercised, per Finding 1) code path is what's being measured.
- Net effect: **the 2026-07-29/07-31 PCIe-vs-UCIe conclusion (gain stays
  under 0.2%) is not invalidated by the interconnect-side math, which is
  unaffected by any of this -- but the "flash dominates" framing needs
  re-verification once Milestone 9 is implemented**, since the dominant
  cost measured so far is ICL cache-lookup overhead, not real NAND array
  service time, and real NAND timing (tens of µs/op) could change the balance.

### Finding 3: Milestone 7 (concurrency) is architecturally possible without protocol changes

- Checked `LEGOSIM_MICRO/interchiplet/includes/sync_protocol.h` to resolve
  whether LegoSim's one-stdin/stdout-pipe-per-simlet design inherently
  prevents concurrent in-flight requests. It does not:
  - `SYNC <cycle>` carries no descriptor -- it is a **global barrier/clock**
    signal shared by all simlets ("time has reached cycle N"), not a
    per-request acknowledgment.
  - `READ`/`WRITE` commands already carry a `<desc>` field in the wire
    format, meant to distinguish concurrent in-flight messages -- but every
    request issued anywhere in this project so far hardcodes `desc=0`.
  - PopNet's `sim_protoengine.cc` already writes `delayInfo.txt` keyed by
    `protoDesc`, not arrival order -- PopNet's own bookkeeping already
    supports concurrent/tagged messages without modification.
- Conclusion: the pipe is a cheap, serial **transport** for short text
  messages, not a throughput bottleneck (nowhere near the cost of the
  NAND/interconnect timing being simulated), and real parallelism happens
  inside each simlet's own event engine, independent of how messages are
  physically piped in one at a time. Multiplexing many `desc`-tagged
  concurrent requests over the existing single pipe (comparable to HTTP/2
  stream IDs on one TCP connection, or NVMe command IDs on one queue) is the
  correct model -- **not** opening additional pipes/streams per concurrent
  request, which the architecture has no mechanism for anyway (one YAML
  `cmd:` entry launches exactly one process with one fixed stdin/stdout pair).
- Concrete gaps this implies for Milestone 7 (detail also added to
  `PLAN.md`): (1) actually assign unique `desc` values instead of `0`; (2)
  NPU-side `DramLegoSim` must replace FIFO-order SYNC-to-request matching
  (Milestone 5's known gap) with matching by `desc`; (3) SimpleSSD-side
  `legosim_main.cc`'s `runStorageIO` currently blocks
  (`while (!done) engine.doNextEvent()`) before the next iteration can start
  -- needs to become "submit N without waiting, check completions per SYNC";
  (4) `interchiplet`'s convergence check compares one scalar total-cycle
  number between rounds -- needs redefining for several independently
  completing requests.

### Setbacks

- Killed the "corrected 8MB" verification run (from the previous entry's
  `-T` fix) after 46+ minutes without completion -- not resolved, still an
  open item. Given Finding 1 above, this run's result would also have needed
  the Milestone 9 fix to be meaningful anyway, so not worth resuming as-is.

**PCIe vs. UCIe Full Size Sweep (4KB-4MB) + PopNet -T Bug**

Follow-up to the 2026-07-29 entry below. That entry answered the advisor's
go/no-go question with 3 sizes (4KB/64KB/1MB); this extends it to a full
12-point doubling sweep and fixes a correctness bug found along the way.

### What Changed

- Removed the per-run timeout used during earlier debugging and re-ran the
  size sweep on the **baseline** (8-channel) SimpleSSD config across every
  doubling from 4KB to 8MB (12 sizes x 2 variants = 24 runs).
- Side investigation (before the full sweep): tried raising SimpleSSD's
  `[pal] Channel` from 8 to 100 (`simplessd/config/sample_100ch.cfg`) to test
  whether the PCIe/UCIe gain grows once flash-side parallelism is less
  abundant. Result: **no effect**, even at 256KB (16 pages). Root cause:
  parallelism in this PAL model is `Channel x Package x Die x Plane`, and the
  baseline's `8 x 4 x 2 x 2 = 128`-way capacity already vastly exceeds what a
  single-request (queue depth 1) workload needs at these sizes -- Channel
  alone was the wrong lever. Not pursued further (would need either a
  request spanning >128 pages, i.e. >2MB, or deliberately shrinking
  Package/Die/Plane to isolate Channel's effect).
- Published permanent results (previously only in scratch/conversation) to
  `results/`: `pcie_vs_ucie_throughput.csv` (raw data),
  `plot_results.py` (regeneratable chart, run via
  `.venv/bin/python3 results/plot_results.py`), `pcie_vs_ucie_comparison.png`
  (3-panel: interconnect delay only, total end-to-end cycles, net gain %).
  `.venv/` added to `.gitignore`.

### Setbacks And Fixes

- Setback: 8MB (and only 8MB, out of all 12 sizes) produced a result that
  broke the pattern every other size followed exactly (total-cycle delta
  should equal exactly 2x the interconnect-delay delta, one per WRITE/READ
  leg -- true at every other size to the last digit). Reproduced twice,
  identically.
  Root cause: `popnet_0.log` showed `Transaction count: 2` but
  `total finished: 1`. The phase-2 `-T` flag (popnet's own internal
  simulated-cycle window) was hardcoded to `1000000000` (1e9). At 8MB the
  second transaction's start time in `bench.txt` is ~1.44e9 -- past the `-T`
  window -- so popnet's simulation ends before that transaction ever starts,
  silently dropping it from `delayInfo.txt` (round 2 then logs
  `Load 1 delay records` instead of `Load 2`) and corrupting convergence.
  Fix: bumped `-T` to `20000000000` (2e10) in both `config/legosim_pcie.yml`
  and `config/legosim_ucie.yml`, with a comment flagging this as something to
  re-check (`popnet_0.log`'s "total finished" vs "Transaction count") if
  sweeping past ~8MB again.
  **Status: fix applied, but a corrected 8MB re-run has not finished as of
  this entry** -- with `-T` corrected, popnet now actually simulates through
  to the second transaction's completion instead of being cut short, and
  wall-clock time scales worse than linearly with size (roughly ~4x runtime
  per 2x size in the 512KB-4MB range), so the corrected run is expected to
  take considerably longer than the (invalid) 1953s the truncated 8MB run
  originally reported. 8MB is excluded from `results/` pending that re-run.
- Setback (earlier, same session): a sweep script deleted each run's
  directory immediately after extracting its CSV row (to save disk on the
  large runs), which meant the anomalous 8MB result initially had no
  surviving logs to diagnose. Re-ran 8MB standalone (without deletion) to
  get the `popnet_0.log`/`bench.txt` evidence above.

### Result (4KB-4MB, 8MB excluded pending fix verification)

Interconnect-delay ratio (PCIe/UCIe) holds steady at ~3.66-3.67x across all
11 sizes. End-to-end gain ((PCIe-UCIe)/PCIe) grows with size but stays small
throughout:

| Size | End-to-end gain |
|---|---|
| 4KB | 0.014% |
| 64KB | 0.141% |
| 1MB | 0.190% |
| 4MB | 0.193% |

Growth is steepest between 16KB-64KB and clearly flattening out by 256KB-1MB
(0.164% -> 0.178% -> 0.186% -> 0.190%, diminishing increments). Consistent
with the 2026-07-29 conclusion: no meaningful gain from swapping PCIe for
UCIe in this pipeline, now confirmed across three orders of magnitude of
request size rather than a single point, with the growth trend itself
visibly plateauing rather than accelerating toward significance.

## 2026-07-29

**PCIe vs. UCIe Interconnect Throughput Gain (Advisor Ask)**

### What Changed

- Advisor asked for a go/no-go check: does swapping the NPU-flash chiplet
  interconnect from PCIe to UCIe yield a meaningful throughput gain? If not,
  no further investigation this cycle.
- Built two PopNet configs off `config/legosim_smoke.yml`:
  `config/legosim_pcie.yml` and `config/legosim_ucie.yml`, differing only in
  interconnect parameters (topology/workload/everything else held fixed):
  - Bandwidth via `-F` (flit size, 64-bit words/flit), at an assumed 1GHz
    link clock (1 cycle = 1ns, matching `dram_freq_mhz` elsewhere in the
    pipeline): PCIe 5.0 x4 target ~15.8 GB/s -> `-F 2` (16 GB/s actual);
    UCIe standard-package target ~64 GB/s -> `-F 8` (64 GB/s exact).
  - Latency via new topology files' edge `weight`
    (`SimpleSSD-Standalone/topology/line_2_{pcie,ucie}.gv`): PCIe raw
    controller/retimer latency ~30-40ns -> `weight=40`; UCIe die-to-die
    latency ~2-10ns midpoint -> `weight=6`. Deliberately used raw-link
    latency for both sides (not PCIe's full host-software-stack latency,
    ~750ns-1us) to keep the comparison apples-to-apples.
- Swept request size (4KB, 64KB, 1MB) x {PCIe, UCIe} through the full
  `dram_legosim_driver -> simplessd-legosim -> popnet` pipeline via
  `interchiplet`.

### Setbacks And Fixes

- Setback: initial runs at all three sizes showed identical PopNet
  "average Delay" (261 cycles) regardless of interconnect config -- the
  `.gv` edge weight had no effect.
  Fix: found that `-G <topofile>` alone does not activate graph-topology
  routing; the router defaults to plain XY mesh (`routing_alg=0`), which
  ignores the `.gv` file entirely. Added `-R 4` (`GRAPH_TOPO`, see
  `popnet_chiplet/index.h`) to both configs -- confirmed by re-run that
  PCIe/UCIe delays then diverge as expected (973 vs. 266 cycles at 4KB).
  Also confirmed separately that PopNet's `-L` (link_length) flag does
  *not* drive timing for this topology mode either -- it only feeds the
  power/energy model.
- Setback: a sweep script that patched request size only in the NPU
  driver's YAML line (`args: ["4096"]`) left SimpleSSD's own copy of the
  same value (`legosim_main.cc` argv[8], a separate line in the same args
  list) stale, desyncing the two sides of the protocol. Runs hung for
  ~60-90 minutes instead of failing fast.
  Fix: patch both lines; added a 60s per-run `timeout` so a future
  desync fails in seconds, not hours.
- Setback: even after the fix, the 1MB runs (both variants) timed out at
  60s -- not a bug, PopNet was still mid-simulation on ~65K flits when
  killed. Not pursued further (see Result below for why).

### Result

| Size | PCIe final cycle | UCIe final cycle | Total Δ | PCIe interconnect delay | UCIe interconnect delay | delay ratio |
|---|---|---|---|---|---|---|
| 4KB | 9,876,367 | 9,874,953 | 0.014% | 973 cycles | 266 cycles | 3.66x |
| 64KB | 15,504,527 | 15,482,633 | 0.141% | 15,053 cycles | 4,106 cycles | 3.67x |

- The PCIe/UCIe interconnect-delay ratio is consistent (~3.66x) across
  both sizes -- the config translation behaves sensibly.
- But total end-to-end latency barely moves (0.01-0.14%): SimpleSSD's
  flash-side simulation time (millions of cycles) dwarfs the interconnect's
  contribution (hundreds to tens of thousands of cycles) at these sizes.
  From 4KB->64KB (16x size increase), only ~0.25% of the *total* cycle
  increase was attributable to the interconnect; the rest was flash-side
  scaling.
- **Conclusion: at 4KB-64KB transfer sizes, swapping PCIe for UCIe yields
  a negligible end-to-end throughput gain, because flash service time, not
  the interconnect, dominates total latency.** Per the advisor's stated
  threshold, no further investigation warranted this cycle.
- **Known gap:** 1MB (a more bandwidth-bound regime) was not measured --
  PopNet did not finish within 60s at that flit count. Given flash-side
  latency scaled *faster* in absolute terms than interconnect delay between
  4KB and 64KB, extrapolation suggests 1MB is unlikely to flip the
  conclusion, but this is not verified. Flagged as a follow-up if the
  advisor wants to push further later.

## 2026-07-10

**09:45 CST - TOGSim DramLegoSim Backend**

### What Changed

- Added `PyTorchSim/TOGSim/include/DramLegoSim.h` and
  `PyTorchSim/TOGSim/src/DramLegoSim.cc`.
- Added a new `DramType::LEGOSIM` config option and parser support for:
  - `dram_type: legosim`
  - `legosim_npu_x`, `legosim_npu_y`
  - `legosim_ssd_x`, `legosim_ssd_y`
  - `legosim_desc`
  - `legosim_max_pending`
- Registered `DramLegoSim` in `Simulator.cc` using the same constructor branch
  pattern as `SimpleDRAM` and `DramRamulator2`.
- Added `PyTorchSim/configs/systolic_ws_8x8_c1_legosim.yml` as the normal
  PyTorchSim-side config knob for selecting the backend.
- Replaced the dummy NPU in `config/legosim_smoke.yml` with a lightweight
  standalone TOGSim `DramLegoSim` driver:

  ```text
  /Users/csld/ECLAB/SIM/PyTorchSim/TOGSim/tests/build/dram_legosim_driver
  ```

### Protocol Behavior

- `DramLegoSim::push()` accepts a `mem_fetch`, records its request cycle, and
  emits the NPU-side request leg:

  ```text
  [INTERCMD] WRITE <cycle> 0 0 1 0 <nbytes> 0
  ```

- `DramLegoSim::cycle()` polls stdin for LegoSim `SYNC` lines.
- On the first `SYNC`, it emits the NPU-side response receive leg:

  ```text
  [INTERCMD] READ <sync_cycle> 1 0 0 0 <nbytes> 0
  ```

- On the second `SYNC`, it calls `mem_fetch::set_reply()`, records
  `response_cycle`, and exposes the completed request through `top()`/`pop()`.
- Matching is FIFO/order based because the current SimpleSSD simlet emits
  descriptor `0`; the backend still records the internal `mem_fetch` request ID
  in the pending structure for debug/accounting.

### Setbacks And Fixes

- Setback: the normal TOGSim CMake path was not usable for this task because
  this checkout has no `PyTorchSim/TOGSim/build/conanbuildinfo.cmake`, and
  pulling or building the full runtime would violate the no-Docker/no-full-stack
  constraint.
  Fix: validated with standalone C++ harnesses that compile only
  `DramLegoSim.cc` plus a small test-only `Dram` base stub.

- Setback: TOGSim headers include Conan-provided dependencies (`robin_hood.h`,
  `spdlog`, `yaml-cpp`) and a Ramulator/Gem5 wrapper even when the LegoSim
  backend itself does not use them.
  Fix: added test-only stubs under `PyTorchSim/TOGSim/tests/stubs/` so the
  standalone harness can compile without Conan, Gem5, Ramulator, Docker, or the
  PyTorchSIM runtime image. Production code still includes the real TOGSim
  headers and remains wired into the normal build.

- Setback: a one-line request/complete protocol would not pair with the active
  `simplessd-legosim` simlet. The SSD side first emits `READ` for request
  arrival, runs flash after `SYNC`, then emits `WRITE` for the return path.
  Fix: made `DramLegoSim` mirror the old dummy NPU: request `WRITE`, wait for
  `SYNC`, response `READ`, wait for `SYNC`, then complete the `mem_fetch`.

- Setback: using the `mem_fetch` request ID as the LegoSim descriptor would make
  PopNet delay-order matching depend on a value that SimpleSSD does not echo.
  Fix: kept descriptor `0` by default for compatibility with the existing
  SimpleSSD simlet and delay records, while tracking request IDs internally.

### Validation

- Unit-level standalone test:

  ```text
  c++ -std=c++17 \
    PyTorchSim/TOGSim/tests/DramLegoSim_unit.cc \
    PyTorchSim/TOGSim/tests/DramLegoSim_base_stub.cc \
    PyTorchSim/TOGSim/src/DramLegoSim.cc \
    -IPyTorchSim/TOGSim/tests/stubs \
    -IPyTorchSim/TOGSim/include \
    -IPyTorchSim/TOGSim/include/scheduler \
    -IPyTorchSim/TOGSim/extern/ramulator2/src \
    -o /tmp/dram_legosim_unit && /tmp/dram_legosim_unit
  ```

- Result:

  ```text
  [INTERCMD] WRITE 3 0 0 1 0 4096 0
  [INTERCMD] READ 7 1 0 0 0 4096 0
  PASS DramLegoSim_unit
  ```

- Protocol-level LegoSim/PopNet/SimpleSSD smoke:

  ```text
  SIMULATOR_ROOT=/Users/csld/ECLAB/SIM/LEGOSIM_MICRO \
    /Users/csld/ECLAB/SIM/LEGOSIM_MICRO/interchiplet/bin/interchiplet \
    /Users/csld/ECLAB/SIM/config/legosim_smoke.yml \
    --cwd /Users/csld/ECLAB/SIM/PyTorchSim/TOGSim/tests/legosim_smoke_run \
    -t 3 -w 2 -f 2
  ```

- Result:
  - Round 1 total: `9875447` cycles.
  - Round 2 total: `9874943` cycles.
  - Convergence difference: `0.005103826928418726%`.
  - `delayInfo.txt` contains nonzero PopNet delays:

    ```text
    1 0 1 0 2 256 261
    9874934 1 0 0 2 256 261
    ```

  - `togsim_dram_legosim.log` shows the PopNet-refined request-arrival cycle:

    ```text
    round 1: [INTERCMD] READ 514 1 0 0 0 4096 0
    round 2: [INTERCMD] READ 257 1 0 0 0 4096 0
    ```

### Out Of Scope Honored

- Did not touch Docker.
- Did not run the full Python, `torch.compile`, Gem5, Spike, or PyTorchSIM
  model pipeline.
- Did not change `main.cc`, the trace-file interface, or the normal Python
  launch path.

## 2026-07-06

**22:56 CST**

### PopNet Phase-2 Integration

- Replaced the no-op phase-2 placeholder in
  `SimpleSSD-Standalone/legosim_smoke.yml` with a real PopNet invocation:

  ```text
  /Users/csld/ECLAB/SIM/LEGOSIM_MICRO/popnet_chiplet/build/popnet
  ```

- PopNet now consumes LegoSim's round-1 `bench.txt` and writes
  `delayInfo.txt` for the next round:

  ```text
  -I ../bench.txt
  -D ../delayInfo.txt
  ```

- Added a minimal two-node topology:

  ```text
  SimpleSSD-Standalone/topology/line_2.gv
  ```

  The graph maps node `0` to the dummy NPU at `(0,0)` and node `1` to the
  SimpleSSD simlet at `(1,0)`.

### PopNet Build Fixes

- Built PopNet at:

  ```text
  LEGOSIM_MICRO/popnet_chiplet/build/popnet
  ```

- Required small CMake portability fixes for the current CMake/Homebrew Boost
  environment:
  - `LEGOSIM_MICRO/popnet_chiplet/CMakeLists.txt`
  - `LEGOSIM_MICRO/popnet_chiplet/orion_power_beta_mar2003/power/CMakeLists.txt`
  - `LEGOSIM_MICRO/popnet_chiplet/graph_lib/CMakeLists.txt`
- Updated old `cmake_minimum_required` values to `3.5`.
- Restored Boost include discovery in `graph_lib`, which needs
  `boost/graph/adjacency_list.hpp`.

### Protocol Robustness Fix

- Round-2 PopNet testing exposed a parser issue: some SimpleSSD log output can
  reach stdout without a trailing newline, causing a protocol line such as
  `[INTERCMD] WRITE ...` to be appended after a log fragment.
- LegoSim only parses lines that start with `[INTERCMD]`.
- Updated `SimpleSSD-Standalone/sim/legosim_main.cc` so SimpleSSD protocol
  emissions start on a fresh line before `[INTERCMD]`.

### Cycle Reporting

- Added final `CYCLE` reports from:
  - `SimpleSSD-Standalone/sim/dummy_npu_main.cc`
  - `SimpleSSD-Standalone/sim/legosim_main.cc`
- This lets LegoSim's existing convergence check use a real benchmark cycle
  instead of reporting `0` or `nan`.

### Setbacks And Fixes

- Setback: PopNet was not actually built at the expected path.

  ```text
  LEGOSIM_MICRO/popnet_chiplet/build/popnet
  ```

  The first check showed the binary was missing, while
  `LEGOSIM_MICRO/interchiplet/bin/interchiplet` existed.

  Fix: built PopNet from the vendored `popnet_chiplet` source instead of
  assuming the binary was already present.

- Setback: PopNet could not even configure with the installed CMake.

  The first configure failed because several CMake files used old minimum
  versions:

  ```text
  cmake_minimum_required(VERSION 3.0)
  cmake_minimum_required(VERSION 2.6)
  ```

  Current CMake rejects compatibility below 3.5.

  Fix: bumped the minimum version to `3.5` in:

  ```text
  LEGOSIM_MICRO/popnet_chiplet/CMakeLists.txt
  LEGOSIM_MICRO/popnet_chiplet/orion_power_beta_mar2003/power/CMakeLists.txt
  LEGOSIM_MICRO/popnet_chiplet/graph_lib/CMakeLists.txt
  ```

- Setback: PopNet's `graph_lib` failed to compile because it could not find
  Boost graph headers:

  ```text
  fatal error: 'boost/graph/adjacency_list.hpp' file not found
  ```

  The top-level PopNet CMake found Boost, but `graph_lib` had its own Boost
  discovery commented out.

  Fix: restored `find_package(Boost REQUIRED COMPONENTS graph)` and
  `include_directories(${Boost_INCLUDE_DIRS})` inside
  `LEGOSIM_MICRO/popnet_chiplet/graph_lib/CMakeLists.txt`.

- Setback: there was no existing minimal two-node topology for the smoke test.

  The available graphs were mostly 4x4 or 6x6 meshes/stars, which would work
  but hide whether the two-node mapping was correct.

  Fix: created a minimal undirected DOT graph:

  ```text
  SimpleSSD-Standalone/topology/line_2.gv
  ```

  with:

  ```text
  graph line_2
  {
      edge[weight=1]
      node[pipeline_stage_delay=1]
      0--1
  }
  ```

- Setback: the first PopNet-backed multi-round run reached round 2 but then
  blocked after the SimpleSSD return path.

  Evidence:
  - round 2 loaded PopNet records:

    ```text
    Load 2 delay records.
    ```

  - dummy NPU emitted:

    ```text
    [INTERCMD] READ 257 1 0 0 0 4096 0
    ```

  - SimpleSSD emitted a return `WRITE`, but LegoSim did not complete the pair.

  Investigation showed the SimpleSSD log contained a protocol command appended
  to the end of a SimpleSSD trace line:

  ```text
  1492762: ICL: READ ... (8029420)[INTERCMD] WRITE 9874682 ...
  ```

  LegoSim only parses commands when the line starts with `[INTERCMD]`, so this
  embedded command was invisible to the coordinator.

  Fix: changed `SimpleSSD-Standalone/sim/legosim_main.cc` so every protocol
  emission starts with a newline before `[INTERCMD]`. After this, LegoSim could
  parse the return `WRITE` reliably.

- Setback: before adding final `CYCLE` reports, LegoSim's convergence math was
  meaningless.

  Earlier runs showed:

  ```text
  Benchmark elapses 0 cycle.
  Difference related to pervious round is nan%.
  ```

  This happened because the smoke endpoints completed their handshake but never
  emitted a final `CYCLE` command, so LegoSim's global cycle tracker stayed at
  zero.

  Fix: added final `CYCLE` commands to both:

  ```text
  SimpleSSD-Standalone/sim/dummy_npu_main.cc
  SimpleSSD-Standalone/sim/legosim_main.cc
  ```

  After that, LegoSim reported real cycle counts and could detect convergence.

- Setback: a two-round run is required to see PopNet timing take effect.

  Round 1 has no `delayInfo.txt`, so LegoSim uses its default timing and only
  records `bench.txt`. PopNet runs in phase 2 and writes the delay records.
  The PopNet delays are consumed by round 2.

  Fix: validate with `-t 3` or at least `-t 2`, not `-t 1`. The successful run
  exited after round 2 because convergence was detected before round 3.

### Verification

- Built SimpleSSD endpoints:

  ```text
  cd /Users/csld/ECLAB/SIM/SimpleSSD-Standalone
  cmake --build build --target simplessd-legosim simplessd-dummy-npu -j4
  ```

- Built PopNet:

  ```text
  cd /Users/csld/ECLAB/SIM/LEGOSIM_MICRO
  cmake -S popnet_chiplet -B popnet_chiplet/build
  cmake --build popnet_chiplet/build -j4
  ```

- Ran the clean PopNet-backed smoke test:

  ```text
  cd /Users/csld/ECLAB/SIM/SimpleSSD-Standalone
  mkdir -p popnet_smoke_run2
  SIMULATOR_ROOT=/Users/csld/ECLAB/SIM/LEGOSIM_MICRO \
    ../LEGOSIM_MICRO/interchiplet/bin/interchiplet \
    /Users/csld/ECLAB/SIM/SimpleSSD-Standalone/legosim_smoke.yml \
    --cwd /Users/csld/ECLAB/SIM/SimpleSSD-Standalone/popnet_smoke_run2 \
    -t 3 -w 2 -f 2
  ```

- Round 1 had no delay records and used default timing:

  ```text
  Benchmark elapses 9875447 cycle.
  ```

- PopNet phase 2 produced real delay records:

  ```text
  1 0 1 0 2 256 261
  9874934 1 0 0 2 256 261
  ```

- PopNet log reported:

  ```text
  Transaction count: 2
  average Delay:        261
  ```

- Round 2 loaded the PopNet records:

  ```text
  Load 2 delay records.
  ```

- Round 2 timing changed from the default baseline and converged:

  ```text
  Benchmark elapses 9874943 cycle.
  Difference related to pervious round is 0.005103826928418726%.
  Quit simulation because simulation cycle has converged.
  ```

- Round-2 dummy NPU log showed the request completion changed from baseline
  `514` to PopNet-refined `257`:

  ```text
  [INTERCMD] WRITE 1 0 0 1 0 4096 0
  [INTERCMD] READ 257 1 0 0 0 4096 0
  [INTERCMD] RESULT 4 requests 1 last_cycle 9874943
  [INTERCMD] CYCLE 9874943
  ```

- Round-2 SimpleSSD log showed the return path and final cycle:

  ```text
  [INTERCMD] WRITE 9874682 1 0 0 0 4096 0
  [INTERCMD] RESULT 10 reads 1 writes 0 bytes_read 4096 bytes_written 0 completed 1
  [INTERCMD] CYCLE 9874938
  ```

### Current Status

- The SimpleSSD smoke harness now uses real PopNet phase-2 delay generation.
- The round-based LegoSim loop is functioning:
  - round 1 records traffic;
  - PopNet writes `delayInfo.txt`;
  - round 2 consumes those delay records;
  - LegoSim detects convergence and exits.

## 2026-07-02

**20:53 CST**

### Active LegoSim Handshake

- Reworked `SimpleSSD-Standalone/sim/legosim_main.cc` from a replay/reactive
  protocol core into an active LegoSim-style simlet.
- The SimpleSSD simlet now follows the same timing shape as existing LegoSim
  accelerator examples such as `mnsim.cpp`:

  ```text
  emit [INTERCMD] READ  ...  # SSD is ready to receive an NPU request
  wait for [INTERCMD] SYNC   # request arrival time after interconnect delay
  run SimpleSSD flash timing
  emit [INTERCMD] WRITE ...  # SSD sends result back to NPU
  wait for [INTERCMD] SYNC   # return-path completion
  repeat
  ```

- The first version is intentionally queue-depth 1. It validates the handshake
  and timing boundary before supporting multiple outstanding SSD requests.
- The flash operation defaults to a logical read, with an optional final
  argument of `read` or `write`.
- Command-line shape is now:

  ```text
  simplessd-legosim <sim.cfg> <ssd.cfg> <output_dir> \
    [ssd_x] [ssd_y] [npu_x] [npu_y] [request_bytes] [iterations] \
    [clock_rate] [start_offset] [read|write]
  ```

### Dummy NPU Peer

- Added `SimpleSSD-Standalone/sim/dummy_npu_main.cc`.
- Added CMake target:

  ```text
  simplessd-dummy-npu
  ```

- The dummy NPU mirrors the SSD endpoint:

  ```text
  emit [INTERCMD] WRITE ...  # send request to SSD
  wait for [INTERCMD] SYNC
  emit [INTERCMD] READ  ...  # receive SSD result
  wait for [INTERCMD] SYNC
  ```

### LegoSim Smoke Harness

- Added `SimpleSSD-Standalone/legosim_smoke.yml`.
- The YAML launches two phase-1 processes:
  - `simplessd-dummy-npu`
  - `simplessd-legosim`
- Phase 2 is `/usr/bin/true` for now, so LegoSim uses default packet timing and
  does not require PopNet for this handshake smoke test.

### LegoSim Coordinator Build Fixes

- `LEGOSIM_MICRO/interchiplet/CMakeLists.txt`
  - Removed the unconditional CUDA language requirement because the active
    `interchiplet` target does not compile CUDA sources.
- `LEGOSIM_MICRO/interchiplet/srcs/interchiplet.cpp`
  - Replaced Linux-only `get_current_dir_name()` with a portable `getcwd()`
    helper.
  - Fixed `delete` to `delete[]` for a buffer allocated with `new[]`.
- `LEGOSIM_MICRO/interchiplet/includes/sync_protocol.h`
  - Fixed `delete` to `delete[]` for a buffer allocated with `new[]`.

### Verification

- Built SimpleSSD targets:

  ```text
  cd /Users/csld/ECLAB/SIM/SimpleSSD-Standalone
  cmake -S . -B build
  cmake --build build --target simplessd-legosim simplessd-dummy-npu -j4
  ```

- Ran synthetic-SYNC smoke tests for both endpoints.
- Built LegoSim coordinator:

  ```text
  cd /Users/csld/ECLAB/SIM/LEGOSIM_MICRO
  cmake -S interchiplet -B interchiplet/build
  cmake --build interchiplet/build -j4
  ```

- Ran full LegoSim handshake smoke test:

  ```text
  cd /Users/csld/ECLAB/SIM/SimpleSSD-Standalone
  SIMULATOR_ROOT=/Users/csld/ECLAB/SIM/LEGOSIM_MICRO \
    ../LEGOSIM_MICRO/interchiplet/bin/interchiplet ./legosim_smoke.yml \
    --cwd . -t 1 -w 2 -f 2
  ```

- The run completed successfully.
- `bench.txt` contained two packet records:

  ```text
  1 1 0 1 257 0
  9874934 514 1 0 257 0
  ```

- The first record is the NPU request path (`0 -> 1`), and the second is the
  SimpleSSD return path (`1 -> 0`).
- `proc_r1_p1_t0/dummy_npu.log` showed:

  ```text
  [INTERCMD] WRITE 1 0 0 1 0 4096 0
  [INTERCMD] READ 514 1 0 0 0 4096 0
  [INTERCMD] RESULT 4 requests 1 last_cycle 9875447
  ```

- `proc_r1_p1_t1/simplessd.log` showed:

  ```text
  [INTERCMD] READ 1 0 0 1 0 4096 0
  [INTERCMD] WRITE 9874934 1 0 0 0 4096 0
  [INTERCMD] RESULT 10 reads 1 writes 0 bytes_read 4096 bytes_written 0 completed 1
  ```

### Next Work

- Replace the dummy NPU with the real PytorchSIM/LegoSim-side request source.
- Replace the `/usr/bin/true` phase-2 placeholder with the intended PopNet
  phase once network delay generation is needed.
- Extend the request protocol to carry logical offset/LBA instead of relying on
  the SimpleSSD simlet's internal sequential offset cursor.

## 2026-06-30

**16:06 CST**

### Goal/Architecture Updates

- Re-read `CONTEXT.md` and `GOAL.md` to ground the integration work.
- Inspected `LEGOSIM_MICRO`, especially:
  - `interchiplet/srcs/interchiplet.cpp`
  - `interchiplet/includes/sync_protocol.h`
  - `interchiplet/srcs/cmd_handler.cpp`
  - `interchiplet/includes/net_bench.h`
  - `interchiplet/includes/net_delay.h`
- Confirmed LegoSim's native protocol is text lines beginning with
  `[INTERCMD]`, not JSON.
- Updated `GOAL.md` to reject the JSON protocol for first integration.
- Recorded that SimpleSSD should remain a sibling project next to
  `LEGOSIM_MICRO`, not be vendored under LegoSim, because LegoSim launches
  external simulator processes from YAML.

### SimpleSSD LegoSim Simlet

- Added a new SimpleSSD-Standalone executable:

  ```text
  simplessd-legosim
  ```

- Added source file:

  ```text
  SimpleSSD-Standalone/sim/legosim_main.cc
  ```

- Added CMake target in:

  ```text
  SimpleSSD-Standalone/CMakeLists.txt
  ```

- The new binary:
  - initializes `Engine`, `ConfigReader`, `SIL::None::Driver`, and
    `BIL::BlockIOEntry`;
  - bypasses the existing internal workload generator (`IGL`);
  - reads LegoSim-shaped commands from stdin;
  - accepts:

    ```text
    [INTERCMD] READ  <cycle> <src_x> <src_y> <dst_x> <dst_y> <nbytes> <desc>
    [INTERCMD] WRITE <cycle> <src_x> <src_y> <dst_x> <dst_y> <nbytes> <desc>
    [INTERCMD] INFO
    [INTERCMD] STATS
    [INTERCMD] SHUTDOWN
    ```

  - maps `READ`/`WRITE` to logical `BIL::BIO` requests;
  - submits through the active SSD path:

    ```text
    BIL -> SIL::None -> HIL -> ICL -> FTL -> PAL
    ```

  - emits completions on stdout as:

    ```text
    [INTERCMD] SYNC <completion_cycle>
    ```

  - keeps stdout protocol-clean and sends SimpleSSD logs to stderr.

### Current Offset Convention

- LegoSim's built-in `READ`/`WRITE` command does not include logical offset or
  LBA.
- The first simlet uses an internal sequential logical offset cursor:

  ```text
  offset = next internal cursor
  size   = nbytes
  ```

- This is only for bring-up and timing validation. A later protocol extension
  or descriptor convention should carry explicit logical offsets.

### Build/Portability Fixes

The project was built on macOS with AppleClang. Several existing upstream
SimpleSSD/McPAT sources required narrow portability fixes:

- `SimpleSSD-Standalone/CMakeLists.txt`
  - Avoid `-rdynamic` on Apple platforms.
  - Suppress AppleClang warnings promoted to errors for vendored/legacy code:
    `-Wno-unused-private-field` and `-Wno-deprecated-declarations`.

- `SimpleSSD-Standalone/simplessd/CMakeLists.txt`
  - Avoid `-rdynamic` on Apple platforms.
  - Suppress AppleClang warnings promoted to errors:
    `-Wno-unused-lambda-capture` and `-Wno-deprecated-declarations`.

- `SimpleSSD-Standalone/simplessd/lib/mcpat/cacti/nuca.cc`
  - Removed a repeated default argument from a constructor definition.

- `SimpleSSD-Standalone/simplessd/util/bitset.hh`
  - Fixed binary bitset operators to return by value instead of returning a
    reference to a temporary stack object.

- `SimpleSSD-Standalone/simplessd/ftl/page_mapping.cc`
  - Initialized `beginAt` in garbage collection to avoid uninitialized use.

- `SimpleSSD-Standalone/simplessd/hil/ufs/def.cc`
  - Added macOS endian helper mappings using `libkern/OSByteOrder.h`.

### Verification

- Configured and built:

  ```text
  cd /Users/csld/ECLAB/SIM/SimpleSSD-Standalone
  cmake -S . -B build
  cmake --build build --target simplessd-legosim -j4
  ```

- Build succeeded.

- Ran a smoke test:

  ```text
  printf '[INTERCMD] INFO\n[INTERCMD] WRITE 0 0 0 1 0 4096 0\n[INTERCMD] READ 1000 0 0 1 0 4096 0\n[INTERCMD] STATS\n' \
    | ./build/simplessd-legosim config/sample.cfg simplessd/config/sample.cfg build
  ```

- Verified stdout-only protocol output by redirecting stdout and stderr
  separately.

- Clean stdout observed:

  ```text
  [INTERCMD] RESULT 4 capacity 412316860416 min_io_size 512
  [INTERCMD] RESULT 10 reads 0 writes 0 bytes_read 0 bytes_written 0 completed 0
  [INTERCMD] SYNC 4916280
  [INTERCMD] SYNC 6465080
  [INTERCMD] RESULT 10 reads 1 writes 1 bytes_read 4096 bytes_written 4096 completed 2
  ```

### Known Caveat / Next Work

- `simplessd-legosim` currently works as a SimpleSSD-side protocol core and
  direct replay binary.
- A full LegoSim run still needs the exact phase-process wiring decided:
  LegoSim normally parses child stdout and writes responses to child stdin.
  The SimpleSSD process either needs a driver process that emits matching
  `READ`/`WRITE` requests into LegoSim, or the LegoSim command flow must be
  extended so storage requests can be delivered to the SimpleSSD simlet in the
  desired direction.
- Next recommended step: create the smallest LegoSim benchmark/YAML harness
  with one NPU-side requester and the SimpleSSD simlet, then decide whether a
  thin storage-request driver process is enough or whether LegoSim needs a
  storage-specific command extension.
