#!/usr/bin/env python3
"""Run one Llama-3-70B transformer-block weight streaming test.

The default request size is the FP16 parameter payload for one transformer
block: 1,711,300,000 bytes. The harness launches four independent cases:

- cold PCIe
- cold UCIe
- hot PCIe
- hot UCIe

Each case gets its own run directory under the current working directory by
default, while the summary CSV is written under results/.
"""
import argparse
import csv
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POPNET_TO_SIM_CYCLE = 1000.0
RESULTS = ROOT / "results"
DEFAULT_SIZE = 1_711_300_000
DEFAULT_QD = 1
DEFAULT_POPNET_WINDOW = 10_000_000_000_000

FIELDNAMES = [
    "memory_mode",
    "variant",
    "size_bytes",
    "queue_depth",
    "total_bytes",
    "final_cycle",
    "throughput_bytes_per_cycle",
    "avg_interconnect_delay",
    "interconnect_fraction_est",
    "bench_records",
    "popnet_tx_count",
    "popnet_finished",
    "status",
    "run_dir",
]


def parse_size(text):
    raw = text.strip().lower().replace("_", "")
    scales = [
        ("gib", 1024**3),
        ("gb", 1000**3),
        ("mib", 1024**2),
        ("mb", 1000**2),
        ("kib", 1024),
        ("kb", 1000),
    ]
    for suffix, scale in scales:
        if raw.endswith(suffix):
            return int(float(raw[: -len(suffix)]) * scale)
    return int(raw, 0)


def patch_config(template, out_path, size, qd, memory_mode, popnet_window):
    text = template.read_text()
    text = re.sub(r'args: \["4096"(?:,\s*"[0-9]+")?\]', f'args: ["{size}", "{qd}"]', text)
    text = re.sub(
        r'(\n      - ")(?:4096)("\n      - ")(?:[0-9]+)(")',
        f"\\g<1>{size}\\g<2>{qd}\\g<3>",
        text,
        count=1,
    )
    ssd_cfg = (
        f"{ROOT}/SimpleSSD-Standalone/simplessd/config/sample.cfg"
        if memory_mode == "hot"
        else f"{ROOT}/SimpleSSD-Standalone/simplessd/config/sample_nocache.cfg"
    )
    text = re.sub(
        rf'"{re.escape(str(ROOT))}/SimpleSSD-Standalone/simplessd/config/sample(?:_nocache)?\.cfg"',
        f'"{ssd_cfg}"',
        text,
        count=1,
    )
    text = re.sub(r'(\n      - "-T"\n      - ")([0-9]+)(")', f"\\g<1>{popnet_window}\\g<3>", text, count=1)
    out_path.write_text(text)


def parse_run(run_dir, size, qd):
    out_path = run_dir / "interchiplet.out"
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

    avg_delay = sum(delays) * POPNET_TO_SIM_CYCLE / len(delays)
    total_bytes = size * qd
    return {
        "size_bytes": size,
        "queue_depth": qd,
        "total_bytes": total_bytes,
        "final_cycle": final_cycle,
        "throughput_bytes_per_cycle": f"{total_bytes / final_cycle:.12g}",
        "avg_interconnect_delay": f"{avg_delay:.6g}",
        "interconnect_fraction_est": f"{avg_delay / final_cycle:.12g}",
        "bench_records": bench_records,
        "popnet_tx_count": tx_count,
        "popnet_finished": finished,
        "status": "OK",
        "run_dir": str(run_dir),
    }


def run_one(memory_mode, variant, size, qd, run_root, popnet_window):
    case = f"{memory_mode}_{variant}_{size}_qd{qd}"
    run_dir = run_root / case
    cfg = run_dir / f"{case}.yml"
    run_dir.mkdir(parents=True, exist_ok=True)
    patch_config(ROOT / "config" / f"legosim_{variant}.yml", cfg, size, qd, memory_mode, popnet_window)

    cmd = [
        str(ROOT / "LEGOSIM_MICRO/interchiplet/bin/interchiplet"),
        str(cfg.resolve()),
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

    with (run_dir / "interchiplet.out").open("w") as out:
        proc = subprocess.run(cmd, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        raise RuntimeError(f"interchiplet failed with exit code {proc.returncode}; see {run_dir / 'interchiplet.out'}")

    row = parse_run(run_dir, size, qd)
    row["memory_mode"] = memory_mode
    row["variant"] = variant
    return row


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["memory_mode"], r["variant"])):
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", default=str(DEFAULT_SIZE), help="Request size, e.g. 1711300000, 1.7113GB, 1.594GiB")
    parser.add_argument("--qd", type=int, default=DEFAULT_QD)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--run-root", default="")
    parser.add_argument("--csv", default=str(RESULTS / "llama70b_layer_qd1.csv"))
    parser.add_argument("--popnet-window", type=int, default=DEFAULT_POPNET_WINDOW)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    size = parse_size(args.size)
    run_root = (Path(args.run_root) if args.run_root else ROOT / f"llama70b_layer_qd1_runs_{time.strftime('%Y%m%d_%H%M%S')}").resolve()
    cases = [("cold", "pcie"), ("cold", "ucie"), ("hot", "pcie"), ("hot", "ucie")]

    print(f"run_root={run_root}")
    print(f"size_bytes={size} qd={args.qd} jobs={args.jobs} popnet_window={args.popnet_window}")
    for memory_mode, variant in cases:
        print(f"case={memory_mode}_{variant}")
    if args.dry_run:
        return

    rows = []
    failures = []
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {
            executor.submit(run_one, memory_mode, variant, size, args.qd, run_root, args.popnet_window): (memory_mode, variant)
            for memory_mode, variant in cases
        }
        for future in as_completed(futures):
            memory_mode, variant = futures[future]
            try:
                row = future.result()
                rows.append(row)
                write_csv(Path(args.csv), rows)
                print(
                    f"done {memory_mode}_{variant}: cycles={row['final_cycle']} "
                    f"avg_link_delay={row['avg_interconnect_delay']} "
                    f"link_fraction_est={row['interconnect_fraction_est']}",
                    flush=True,
                )
            except Exception as exc:
                failures.append((memory_mode, variant, exc))
                print(f"ERROR {memory_mode}_{variant}: {exc}", file=sys.stderr, flush=True)

    if rows:
        write_csv(Path(args.csv), rows)
        print(f"wrote {args.csv}")
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
