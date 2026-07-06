# Project Log

## 2026-07-02 20:53 CST

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

## 2026-06-30 16:06 CST

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
