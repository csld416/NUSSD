#!/usr/bin/env python3
"""Run a resumable PCIe/UCIe sweep over request size and queue depth.

Default grid is intentionally bounded because large request sizes at high QD
make PopNet very slow. Use --sizes/--qds to extend the matrix.
"""
import argparse
import csv
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POPNET_TO_SIM_CYCLE = 1000.0
RESULTS = ROOT / "results"
CSV_PATH = RESULTS / "pcie_vs_ucie_size_qd.csv"
RUN_ROOT = RESULTS / "size_qd_runs"

VARIANTS = ("pcie", "ucie")
DEFAULT_SIZES = [4096, 16384, 65536, 262144, 1048576]
DEFAULT_QDS = [1, 2, 4, 8]

FIELDNAMES = [
    "variant",
    "size_bytes",
    "queue_depth",
    "total_bytes",
    "final_cycle",
    "throughput_bytes_per_cycle",
    "avg_interconnect_delay",
    "bench_records",
    "popnet_tx_count",
    "popnet_finished",
    "status",
    "run_dir",
]


def parse_int_list(text):
    values = []
    for part in text.split(","):
        part = part.strip().lower()
        if not part:
            continue
        scale = 1
        if part.endswith("kb"):
            scale = 1024
            part = part[:-2]
        elif part.endswith("mb"):
            scale = 1024 * 1024
            part = part[:-2]
        values.append(int(part, 0) * scale)
    return values


def load_existing(path):
    if not path.exists():
        return {}
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return {
        (row["variant"], int(row["size_bytes"]), int(row["queue_depth"])): row
        for row in rows
        if row.get("status") == "OK"
    }


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    tmp.replace(path)


def patch_config(template, out_path, size, qd):
    text = template.read_text()
    text = re.sub(r'args: \["4096"(?:,\s*"[0-9]+")?\]', f'args: ["{size}", "{qd}"]', text)
    text = re.sub(
        r'(\n      - ")(?:4096)("\n      - ")(?:[0-9]+)(")',
        f'\\g<1>{size}\\g<2>{qd}\\g<3>',
        text,
        count=1,
    )
    out_path.write_text(text)


def run_one(variant, size, qd):
    run_dir = RUN_ROOT / f"run_{variant}_{size}_qd{qd}"
    cfg = RUN_ROOT / f"{variant}_{size}_qd{qd}.yml"
    run_dir.mkdir(parents=True, exist_ok=True)
    patch_config(ROOT / "config" / f"legosim_{variant}.yml", cfg, size, qd)

    out_path = run_dir / "interchiplet.out"
    cmd = [
        str(ROOT / "LEGOSIM_MICRO/interchiplet/bin/interchiplet"),
        str(cfg),
        "--cwd",
        str(run_dir),
        "-t",
        "3",
        "-w",
        "2",
        "-f",
        "2",
    ]
    env = dict(os.environ)
    env["SIMULATOR_ROOT"] = str(ROOT / "LEGOSIM_MICRO")

    with out_path.open("w") as out:
        proc = subprocess.run(cmd, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"interchiplet failed with exit code {proc.returncode}")

    output = out_path.read_text(errors="replace")
    cycles = re.findall(r"Benchmark elapses ([0-9]+) cycle\.", output)
    if not cycles:
        raise RuntimeError("missing final cycle")
    final_cycle = int(cycles[-1])

    bench_path = run_dir / "bench.txt"
    delay_path = run_dir / "delayInfo.txt"
    bench_records = len(bench_path.read_text().splitlines())
    expected = 2 * qd
    if bench_records != expected:
        raise RuntimeError(f"bench records {bench_records}, expected {expected}")

    delays = []
    for line in delay_path.read_text().splitlines():
        parts = line.split()
        if parts:
            delays.append(float(parts[-1]))
    if len(delays) != expected:
        raise RuntimeError(f"delay records {len(delays)}, expected {expected}")

    tx_count = None
    finished = None
    for log in sorted(run_dir.glob("proc_r*_p2_t0/popnet_0.log")):
        text = log.read_text(errors="replace")
        tx = re.findall(r"Transaction count:\s+([0-9]+)", text)
        fin = re.findall(r"total finished:\s+([0-9]+)", text)
        if tx:
            tx_count = int(tx[-1])
        if fin:
            finished = int(fin[-1])
    if tx_count != expected or finished != expected:
        raise RuntimeError(f"PopNet finished {finished}/{tx_count}, expected {expected}")

    total_bytes = size * qd
    return {
        "variant": variant,
        "size_bytes": size,
        "queue_depth": qd,
        "total_bytes": total_bytes,
        "final_cycle": final_cycle,
        "throughput_bytes_per_cycle": f"{total_bytes / final_cycle:.12g}",
        "avg_interconnect_delay": f"{sum(delays) * POPNET_TO_SIM_CYCLE / len(delays):.6g}",
        "bench_records": bench_records,
        "popnet_tx_count": tx_count,
        "popnet_finished": finished,
        "status": "OK",
        "run_dir": str(run_dir),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default=",".join(str(x) for x in DEFAULT_SIZES))
    parser.add_argument("--qds", default=",".join(str(x) for x in DEFAULT_QDS))
    parser.add_argument("--variants", default=",".join(VARIANTS))
    parser.add_argument("--csv", default=str(CSV_PATH))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    sizes = parse_int_list(args.sizes)
    qds = parse_int_list(args.qds)
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    csv_path = Path(args.csv)

    existing = {} if args.force else load_existing(csv_path)
    rows = list(existing.values())

    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    for size in sizes:
        for qd in qds:
            for variant in variants:
                key = (variant, size, qd)
                if key in existing:
                    print(f"skip variant={variant} size={size} qd={qd}", flush=True)
                    continue
                print(f"run variant={variant} size={size} qd={qd}", flush=True)
                row = run_one(variant, size, qd)
                rows.append(row)
                rows.sort(key=lambda r: (int(r["size_bytes"]), int(r["queue_depth"]), r["variant"]))
                write_rows(csv_path, rows)
                print(
                    f"done variant={variant} size={size} qd={qd} "
                    f"cycles={row['final_cycle']} tput={row['throughput_bytes_per_cycle']}",
                    flush=True,
                )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
