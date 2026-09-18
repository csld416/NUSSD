#!/usr/bin/env python3
"""Measure isolated one-hop PopNet latency as a function of payload size."""

import argparse
import csv
import math
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POPNET = ROOT / "LEGOSIM_MICRO/popnet_chiplet/build/popnet"
RESULTS = ROOT / "results"

VARIANTS = {
    "ufs4": {
        "flit_words": 1,
        "clock_rate": 0.000725,
        "topology": ROOT / "SimpleSSD-Standalone/topology/line_2_ufs4.gv",
    },
    "ucie": {
        "flit_words": 8,
        "clock_rate": 0.001,
        "topology": ROOT / "SimpleSSD-Standalone/topology/line_2_ucie.gv",
    },
}

STANDARD_SIZES = [4096, 16384, 65536, 262144, 1048576, 4194304]


def parse_size(value):
    raw = value.strip().lower().replace("_", "")
    scales = (("mib", 1024**2), ("mb", 1024**2), ("kib", 1024), ("kb", 1024))
    for suffix, scale in scales:
        if raw.endswith(suffix):
            return int(float(raw[: -len(suffix)]) * scale)
    return int(raw, 0)


def parse_sizes(value):
    return [parse_size(part) for part in value.split(",") if part.strip()]


def read_delay(path):
    rows = path.read_text().splitlines()
    if len(rows) != 1:
        raise RuntimeError(f"expected one delay record, found {len(rows)}")
    parts = rows[0].split()
    if len(parts) < 7:
        raise RuntimeError(f"malformed delay record: {rows[0]}")
    return int(parts[-1])


def run_case(variant, size, run_root):
    settings = VARIANTS[variant]
    flit_bytes = 8 * settings["flit_words"]
    packet_flits = math.ceil(size / flit_bytes) + 1
    case_dir = run_root / f"s_{size}"
    case_dir.mkdir(parents=True, exist_ok=True)
    trace = case_dir / "bench.txt"
    delay = case_dir / "delayInfo.txt"
    stdout_log = case_dir / "stdout.log"
    event_log = case_dir / "popnet.log"

    # Sync-protocol trace: src_time dst_time src dst packet_flits descriptor.
    trace.write_text(f"0 0 0 1 {packet_flits} 8\n")
    if delay.exists():
        delay.unlink()
    if event_log.exists() or event_log.is_symlink():
        event_log.unlink()
    # PopNet logs every router event here; suppressing it does not affect timing.
    event_log.symlink_to("/dev/null")

    sim_cycles = max(100000, packet_flits * 8)
    cmd = [
        str(POPNET),
        "-A", "2",
        "-c", "1",
        "-V", "3",
        "-B", "12",
        "-O", "12",
        "-F", str(settings["flit_words"]),
        "-L", "1000",
        "-T", str(sim_cycles),
        "-r", "1",
        "-I", str(trace),
        "-G", str(settings["topology"]),
        "-R", "4",
        "-D", str(delay),
        "-P",
    ]
    with stdout_log.open("w") as output:
        proc = subprocess.run(cmd, cwd=case_dir, stdout=output, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"PopNet exited with {proc.returncode}; see {stdout_log}")

    delay_cycles = read_delay(delay)
    cycle_ps = 1.0 / settings["clock_rate"]
    latency_ns = delay_cycles * cycle_ps / 1000.0
    return {
        "variant": variant,
        "size_bytes": size,
        "flit_bytes": flit_bytes,
        "packet_flits": packet_flits,
        "delay_cycles": delay_cycles,
        "cycle_ps": f"{cycle_ps:.12g}",
        "latency_ns": f"{latency_ns:.12g}",
        "effective_gbps": f"{size / latency_ns:.12g}",
        "run_dir": str(case_dir),
    }


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "variant", "size_bytes", "flit_bytes", "packet_flits", "delay_cycles",
        "cycle_ps", "latency_ns", "effective_gbps", "run_dir",
    ]
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path, variant, sizes):
    if not path.exists():
        return []
    with path.open(newline="") as source:
        return [
            row for row in csv.DictReader(source)
            if row["variant"] == variant and int(row["size_bytes"]) in sizes
        ]


def write_plot(path, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    standard = [row for row in rows if int(row["size_bytes"]) in STANDARD_SIZES]
    standard.sort(key=lambda row: int(row["size_bytes"]))
    x = [int(row["size_bytes"]) / 1024 for row in standard]
    y = [float(row["latency_ns"]) / 1000 for row in standard]

    fig, ax = plt.subplots(figsize=(7.2, 4.5), constrained_layout=True)
    ax.plot(x, y, marker="o", linewidth=2, color="#176B87")
    ax.set_xscale("log", basex=4)
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(["4KB", "16KB", "64KB", "256KB", "1MB", "4MB"])
    ax.set_xlabel("Request size")
    ax.set_ylabel("One-way PopNet latency (us)")
    ax.set_title("UFS4-equivalent isolated one-hop link latency")
    ax.grid(True, which="both", linewidth=0.6, alpha=0.35)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="ufs4")
    parser.add_argument("--sizes", default=",".join(str(size) for size in STANDARD_SIZES))
    parser.add_argument("--dense-max-flits", type=int, default=61)
    parser.add_argument("--run-root")
    parser.add_argument("--csv")
    parser.add_argument("--plot")
    args = parser.parse_args()

    settings = VARIANTS[args.variant]
    flit_bytes = 8 * settings["flit_words"]
    dense_sizes = [flit_bytes * (flits - 1) for flits in range(2, args.dense_max_flits + 1)]
    sizes = sorted(set(dense_sizes + parse_sizes(args.sizes)))
    run_root = Path(args.run_root or ROOT / f"{args.variant}_popnet_link_sweep").resolve()
    csv_path = Path(args.csv or RESULTS / f"{args.variant}_popnet_link_sweep.csv").resolve()
    plot_path = Path(args.plot or RESULTS / f"{args.variant}_popnet_link_sweep.png").resolve()

    rows = read_csv(csv_path, args.variant, sizes)
    completed_sizes = {int(row["size_bytes"]) for row in rows}
    for index, size in enumerate(sizes, 1):
        if size in completed_sizes:
            print(f"skip {index}/{len(sizes)} {args.variant} size={size}B", flush=True)
            continue
        print(f"run {index}/{len(sizes)} {args.variant} size={size}B", flush=True)
        row = run_case(args.variant, size, run_root)
        rows.append(row)
        rows.sort(key=lambda item: int(item["size_bytes"]))
        write_csv(csv_path, rows)
        print(
            f"done size={size}B flits={row['packet_flits']} "
            f"cycles={row['delay_cycles']} latency_ns={row['latency_ns']}",
            flush=True,
        )

    if args.variant == "ufs4" and all(size in sizes for size in STANDARD_SIZES):
        write_plot(plot_path, rows)
    print(f"csv={csv_path}")
    if plot_path.exists():
        print(f"plot={plot_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
