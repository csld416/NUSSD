SIM_ROOT := $(CURDIR)
RUN_DIR ?= /tmp/sim_run

.PHONY: build build-dummy-npu build-simplessd build-legosim build-popnet run clean-run clean

build: build-dummy-npu build-simplessd build-legosim build-popnet

build-dummy-npu:
	cmake -S dummy_npu -B dummy_npu/build
	cmake --build dummy_npu/build -j4

build-simplessd:
	cmake -S SimpleSSD-Standalone -B SimpleSSD-Standalone/build
	cmake --build SimpleSSD-Standalone/build --target simplessd-legosim -j4

build-legosim:
	cmake -S LEGOSIM_MICRO/interchiplet -B LEGOSIM_MICRO/interchiplet/build
	cmake --build LEGOSIM_MICRO/interchiplet/build -j4

build-popnet:
	cmake -S LEGOSIM_MICRO/popnet_chiplet -B LEGOSIM_MICRO/popnet_chiplet/build
	cmake --build LEGOSIM_MICRO/popnet_chiplet/build -j4

# Override the output location with: make run RUN_DIR=/some/other/path
run:
	mkdir -p $(RUN_DIR)
	SIMULATOR_ROOT=$(SIM_ROOT)/LEGOSIM_MICRO \
	  $(SIM_ROOT)/LEGOSIM_MICRO/interchiplet/bin/interchiplet \
	  $(SIM_ROOT)/config/legosim_smoke.yml \
	  --cwd $(RUN_DIR) -t 3 -w 2 -f 2

# Wipes RUN_DIR (leftover bench.txt/delayInfo.txt/logs from a previous run).
# Run this yourself before `make run` whenever you want round 1 to start
# genuinely cold — RUN_DIR is never cleared automatically.
clean-run:
	rm -rf $(RUN_DIR)

# Wipes compiled binaries only (dummy_npu/, SimpleSSD-Standalone/,
# interchiplet/, popnet_chiplet/ build dirs). Does NOT touch RUN_DIR.
clean:
	rm -rf dummy_npu/build SimpleSSD-Standalone/build \
	  LEGOSIM_MICRO/interchiplet/build LEGOSIM_MICRO/popnet_chiplet/build
