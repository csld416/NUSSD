#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# User toggles: edit this section, then run ./run.sh
# =============================================================================
NUSSD_PROTOCOL_TRACE="${NUSSD_PROTOCOL_TRACE:-1}"  # 1: monitor events, 0: off
REQUEST_OFFSET_BYTES="${REQUEST_OFFSET_BYTES:-0}"
REQUEST_LENGTH_BYTES="${REQUEST_LENGTH_BYTES:-4096}"
MONITOR_ATTACH_DELAY_SECONDS="${MONITOR_ATTACH_DELAY_SECONDS:-5}"
MONITOR_REFRESH_SECONDS="${MONITOR_REFRESH_SECONDS:-1}"
REBUILD_SIMPLESSD="${REBUILD_SIMPLESSD:-0}"        # 1: rebuild before run
# =============================================================================

NUSSD_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LEGOSIM_ROOT="${NUSSD_ROOT}/LEGOSIM_MICRO"
SIMPLESSD_ROOT="${NUSSD_ROOT}/SimpleSSD-Standalone"
RESULT_ROOT="${NUSSD_ROOT}/runtime_results"
BUILD_DIR="${RESULT_ROOT}/.protocol_demo_build"
LATEST_LINK="${RESULT_ROOT}/protocol_demo_latest"
CLIENT_SOURCE="${NUSSD_ROOT}/demo/runtime_protocol_client.cc"
CLIENT_BIN="${BUILD_DIR}/runtime_protocol_client"
INTERCHIPLET_BIN="${LEGOSIM_ROOT}/interchiplet/bin/interchiplet"
SIMPLESSD_BIN="${SIMPLESSD_ROOT}/build/simplessd-legosim"

show_usage() {
    echo "Usage:"
    echo "  ./run.sh          Run one NPU-to-SimpleSSD protocol demonstration"
    echo "  ./run.sh monitor  Monitor the latest demonstration"
    echo "  ./run.sh path     Print the latest run directory"
}

monitor_latest() {
    if [ ! -e "$LATEST_LINK" ]; then
        echo "No protocol demo exists yet. Run ./run.sh first." >&2
        exit 1
    fi
    exec env MONITOR_MODE=bridge \
        RUN_DIR="$LATEST_LINK" \
        INTERVAL="$MONITOR_REFRESH_SECONDS" \
        "${NUSSD_ROOT}/monitor.sh"
}

case "${1:-run}" in
    monitor)
        monitor_latest
        ;;
    path)
        if [ ! -e "$LATEST_LINK" ]; then
            echo "No protocol demo exists yet." >&2
            exit 1
        fi
        readlink -f "$LATEST_LINK"
        exit 0
        ;;
    run)
        ;;
    -h|--help|help)
        show_usage
        exit 0
        ;;
    *)
        show_usage >&2
        exit 2
        ;;
esac

for toggle in NUSSD_PROTOCOL_TRACE REBUILD_SIMPLESSD; do
    value="${!toggle}"
    if [ "$value" != "0" ] && [ "$value" != "1" ]; then
        echo "$toggle must be 0 or 1, got: $value" >&2
        exit 2
    fi
done

for required_file in \
    "$INTERCHIPLET_BIN" \
    "${LEGOSIM_ROOT}/interchiplet/lib/libinterchiplet_c.a" \
    "$CLIENT_SOURCE"; do
    if [ ! -e "$required_file" ]; then
        echo "Required file is missing: $required_file" >&2
        exit 1
    fi
done

if [ "$REBUILD_SIMPLESSD" = "1" ] || [ ! -x "$SIMPLESSD_BIN" ]; then
    cmake --build "${SIMPLESSD_ROOT}/build" \
        --target simplessd-legosim -j2
fi
if [ ! -x "$SIMPLESSD_BIN" ]; then
    echo "SimpleSSD runtime wrapper is missing: $SIMPLESSD_BIN" >&2
    exit 1
fi

mkdir -p "$BUILD_DIR" "$RESULT_ROOT"
if [ ! -x "$CLIENT_BIN" ] || \
   [ "$CLIENT_SOURCE" -nt "$CLIENT_BIN" ] || \
   [ "${NUSSD_ROOT}/protocol/ssd_ipc_protocol.h" -nt "$CLIENT_BIN" ] || \
   [ "${NUSSD_ROOT}/protocol/ssd_ipc_trace.h" -nt "$CLIENT_BIN" ]; then
    c++ -std=c++17 -O2 \
        -I"${NUSSD_ROOT}/protocol" \
        -I"${LEGOSIM_ROOT}/interchiplet/includes" \
        "$CLIENT_SOURCE" \
        "${LEGOSIM_ROOT}/interchiplet/lib/libinterchiplet_c.a" \
        -pthread -o "$CLIENT_BIN"
fi

RUN_STAMP="$(date -u '+%Y%m%dT%H%M%SZ')_$$"
RUN_DIR="${RESULT_ROOT}/protocol_demo_${RUN_STAMP}"
TRACE_DIR="${RUN_DIR}/live"
SSD_OUTPUT_DIR="${RUN_DIR}/simplessd"
YAML_PATH="${RUN_DIR}/legosim.yml"
mkdir -p "$TRACE_DIR" "$SSD_OUTPUT_DIR" "${RUN_DIR}/work"
ln -sfn "$RUN_DIR" "$LATEST_LINK"

cat >"$YAML_PATH" <<EOF
phase1:
  - cmd: "$CLIENT_BIN"
    args: ["$REQUEST_OFFSET_BYTES", "$REQUEST_LENGTH_BYTES"]
    log: "npu-client.log"
    is_to_stdout: false
    clock_rate: 0.7
  - cmd: "$SIMPLESSD_BIN"
    args:
      - "${SIMPLESSD_ROOT}/config/sample.cfg"
      - "${SIMPLESSD_ROOT}/simplessd/config/sample_nocache.cfg"
      - "$SSD_OUTPUT_DIR"
      - "--runtime-ipc"
      - "1"
      - "0"
      - "0"
      - "0"
      - "1000"
    log: "simplessd.log"
    is_to_stdout: false
    clock_rate: 1.0
phase2:
  - cmd: "/bin/true"
    args: []
    log: "noop.log"
    is_to_stdout: false
    clock_rate: 1.0
EOF

echo "NUSSD protocol demonstration"
echo "  run directory: $RUN_DIR"
echo "  read: offset=$REQUEST_OFFSET_BYTES bytes=$REQUEST_LENGTH_BYTES"
echo "  tracing: $NUSSD_PROTOCOL_TRACE"
if [ "$NUSSD_PROTOCOL_TRACE" = "1" ]; then
    echo
    echo "In a second terminal, run:"
    echo "  cd $NUSSD_ROOT && ./run.sh monitor"
    if [ "$MONITOR_ATTACH_DELAY_SECONDS" -gt 0 ]; then
        echo
        echo "Waiting ${MONITOR_ATTACH_DELAY_SECONDS}s for the monitor to attach..."
        sleep "$MONITOR_ATTACH_DELAY_SECONDS"
    fi
fi

env NUSSD_PROTOCOL_TRACE="$NUSSD_PROTOCOL_TRACE" \
    NUSSD_TRACE_DIR="$TRACE_DIR" \
    SIMULATOR_ROOT="$LEGOSIM_ROOT" \
    "$INTERCHIPLET_BIN" "$YAML_PATH" \
    --cwd "${RUN_DIR}/work" -t 1 -w 3 -f 2 \
    2>&1 | tee "${RUN_DIR}/interchiplet.console.log"

echo
echo "Protocol demonstration finished successfully."
echo "Inspect it at any time with: ./run.sh monitor"
