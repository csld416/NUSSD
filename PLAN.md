# Project Plan

Milestones toward the GOAL.md research question:

> If a chiplet interconnect is used between an NPU and flash, how should the
> in-flash processing (IFP) module be designed? Should it remain, change, or
> be removed?

Flow under test: `PytorchSIM -> LegoSim -> SimpleSSD-Standalone`

---

## Milestone 1: Understand the goal and SimpleSSD architecture (DONE)

- Reviewed SimpleSSD internals: BIL (block I/O entry point) -> SIL -> HIL ->
  ICL -> FTL -> PAL. (DONE)
- Reviewed LegoSim's native protocol: text lines beginning with `[INTERCMD]`,
  parsed via `interchiplet/includes/sync_protocol.h`,
  `interchiplet/srcs/interchiplet.cpp`, `interchiplet/srcs/cmd_handler.cpp`.
  (DONE)
- Confirmed architecture split: LegoSim owns NPU-to-flash-controller
  interconnect timing; SimpleSSD owns active SSD service time (HIL, ICL, FTL,
  PAL, queueing, GC). (DONE)
- Rejected an earlier JSON-protocol draft in favor of LegoSim's native
  `[INTERCMD]` text protocol. (DONE)

## Milestone 2: Connect SimpleSSD-Standalone to LegoSim as a separate simlet (DONE)

- Built `simplessd-legosim` binary: initializes Engine/ConfigReader/
  SIL::None::Driver/BIL::BlockIOEntry, bypasses the internal workload
  generator (IGL). (DONE)
- Reworked it from a passive reactive core into an **active** LegoSim simlet
  that emits its own `READ`/`WRITE` to initiate the handshake, not just reply
  to input. (DONE)
- Built `simplessd-dummy-npu` as a stand-in request source to pair with, since
  the real PytorchSIM side isn't wired in yet. (DONE)
- Wrote a YAML harness (`legosim_smoke.yml`) launching both as LegoSim
  phase-1 processes. (DONE)
- Verified end-to-end: real LegoSim coordinator run, `READ`/`WRITE` paired
  correctly, real SimpleSSD flash simulation executed (FTL, cache, PAL
  timing), completion returned through LegoSim back to the NPU stand-in.
  (DONE)
- Fixed macOS/AppleClang portability issues blocking the build (CMake flags,
  `bitset.hh`, `page_mapping.cc`, `hil/ufs/def.cc`, `mcpat/cacti/nuca.cc`,
  `interchiplet.cpp`, `sync_protocol.h`). (DONE)
- Consolidated the project into a single flat git repository (previously 14
  nested repos across 3 `.gitmodules` files), preserving the above fixes.
  (DONE — infrastructure, not itself part of the research goal)

## Milestone 3a: Phase-2 interconnect delay via PopNet (DONE)

- Replaced the phase-2 placeholder (`/usr/bin/true`) with a real invocation of
  the vendored PopNet chiplet interconnect simulator
  (`popnet_chiplet/build/popnet`), against a minimal 2-node topology
  (`SimpleSSD-Standalone/topology/line_2.gv`). (DONE)
- Fixed a protocol robustness bug found during multi-round testing:
  `legosim_main.cc` could emit `[INTERCMD]` output onto the same line as a
  trace log fragment with no newline, making the command invisible to
  LegoSim's line-based parser. (DONE)
- Added final `CYCLE` reporting to both `dummy_npu_main.cc` and
  `legosim_main.cc` so LegoSim's round-to-round convergence check has a real
  benchmark cycle to compare, instead of `0`/`nan`. (DONE)
- Verified (independently re-run, exact match): round 1 has no delay
  information and the request completes at cycle 514; PopNet computes a real
  average delay of 261 cycles from the recorded trace; round 2 uses that
  refined delay and the same request now completes at cycle 257; LegoSim
  detects convergence and exits. (DONE)

## Milestone 3b: Real NPU-side traffic via PytorchSIM (NOT STARTED)

- [ ] Determine whether PytorchSIM already speaks LegoSim's `[INTERCMD]`
      protocol, or whether an adapter needs to be built for it (as was done
      for SimpleSSD).
- [ ] Replace `simplessd-dummy-npu` with the real PytorchSIM-side request
      source (or, if PytorchSIM isn't ready, a more realistic synthetic NPU
      workload generator as an intermediate step).
- [ ] Re-validate the phase-1/phase-2 round-based loop with real traffic
      patterns instead of the single fixed-size dummy request.

## Milestone 3c: Real logical offset/LBA addressing (NOT STARTED)

- [ ] Extend the request protocol to carry an explicit logical offset/LBA,
      instead of relying on SimpleSSD's internal sequential offset cursor
      (LegoSim's built-in `READ`/`WRITE` command has no offset field today).
- [ ] Validate realistic, non-sequential access patterns once explicit
      addressing exists.

## Milestone 3d: Concurrency / multiple outstanding requests (NOT STARTED)

- [ ] Support queue depth > 1 in `simplessd-legosim` (current implementation
      is intentionally queue-depth 1 for bring-up).
- [ ] Validate out-of-order completion (completion order need not match
      submission order; requests are matched by ID).

## Milestone 4: Add IFP support after the baseline is stable (BLOCKED on M3b-3d)

- [ ] Design in-flash processing (IFP) module placement options (remain in
      flash, change, or remove) now that a working, validated timing baseline
      exists.
- [ ] Implement and simulate at least one IFP variant through the same
      LegoSim <-> SimpleSSD path.
- [ ] Compare IFP-on-flash vs IFP-removed (or relocated) results to answer the
      core GOAL.md question.

---

**Current position: Milestones 1, 2, and 3a complete. 3b, 3c, 3d not yet
started (any order); Milestone 4 blocked until those three are done.**
