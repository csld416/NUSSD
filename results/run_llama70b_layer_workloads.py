#!/usr/bin/env python3
"""Run Llama-3-70B layer streaming workloads across cold/hot PCIe/UCIe.

Workload 1:
  One monolithic QD1 read for a full transformer block.

Workload 2:
  Seven sequential QD1 reads, one per major transformer-block matrix. This is
  intentionally not QD7; it models matrix-by-matrix layer streaming.
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
DEFAULT_POPNET_WINDOW = 10_000_000_000_000

W1_SIZE = 1_711_300_000
W2_MATRICES = [
    ("q", 8192 * 8192 * 2),
    ("k", 8192 * 1024 * 2),
    ("v", 8192 * 1024 * 2),
    ("o", 8192 * 8192 * 2),
    ("gate", 8192 * 28672 * 2),
    ("up", 8192 * 28672 * 2),
    ("down", 28672 * 8192 * 2),
]

FIELDNAMES = [
    "workload",
    "memory_mode",
    "variant",
    "size_bytes",
    "request_count",
    "total_bytes",
    "total_cycle",
    "interconnect_time_est",
    "interconnect_fraction_est",
    "speedup_vs_pcie",
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


def parse_matrix_list(text):
    matrices = []
    for idx, part in enumerate(text.split(",")):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            name, size = part.split(":", 1)
            name = name.strip()
        else:
            name = f"m{idx}"
            size = part
        matrices.append((name, parse_size(size)))
    if not matrices:
        raise ValueError("empty matrix list")
    return matrices


def patch_config(template, out_path, size, memory_mode, popnet_window):
    text = template.read_text()
    text = re.sub(r'args: \["4096"(?:,\s*"[0-9]+")?\]', f'args: ["{size}", "1"]', text)
    text = re.sub(
        r'(\n      - ")(?:4096)("\n      - ")(?:[0-9]+)(")',
        f"\\g<1>{size}\\g<2>1\\g<3>",
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


def parse_one_run(run_dir):
    output = (run_dir / "interchiplet.out").read_text(errors="replace")
    cycles = re.findall(r"Benchmark elapses ([0-9]+) cycle\.", output)
    if not cycles:
        raise RuntimeError(f"missing final cycle in {run_dir}")
    final_cycle = int(cycles[-1])

    bench_records = len((run_dir / "bench.txt").read_text().splitlines())
    if bench_records != 2:
        raise RuntimeError(f"{run_dir}: bench records {bench_records}, expected 2")

    delays = []
    for line in (run_dir / "delayInfo.txt").read_text().splitlines():
        parts = line.split()
        if parts:
            delays.append(float(parts[-1]))
    if len(delays) != 2:
        raise RuntimeError(f"{run_dir}: delay records {len(delays)}, expected 2")

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
    if tx_count != 2 or finished != 2:
        raise RuntimeError(f"{run_dir}: PopNet finished {finished}/{tx_count}, expected 2")

    return final_cycle, sum(delays) * POPNET_TO_SIM_CYCLE


def run_interchiplet(run_dir, cfg):
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
    return parse_one_run(run_dir)


def run_request(parent_dir, label, variant, memory_mode, size, popnet_window):
    run_dir = parent_dir / label
    cfg = run_dir / f"{label}.yml"
    run_dir.mkdir(parents=True, exist_ok=True)
    patch_config(ROOT / "config" / f"legosim_{variant}.yml", cfg, size, memory_mode, popnet_window)
    cycle, interconnect_time = run_interchiplet(run_dir, cfg)
    return {
        "label": label,
        "size": size,
        "cycle": cycle,
        "interconnect_time": interconnect_time,
        "run_dir": str(run_dir),
    }


def run_case(workload, memory_mode, variant, sizes, run_root, popnet_window):
    case_dir = run_root / f"{workload}_{memory_mode}_{variant}"
    request_rows = []
    for name, size in sizes:
        request_rows.append(run_request(case_dir, name, variant, memory_mode, size, popnet_window))

    total_cycle = sum(r["cycle"] for r in request_rows)
    interconnect_time = sum(r["interconnect_time"] for r in request_rows)
    total_bytes = sum(r["size"] for r in request_rows)
    return {
        "workload": workload,
        "memory_mode": memory_mode,
        "variant": variant,
        "size_bytes": total_bytes,
        "request_count": len(request_rows),
        "total_bytes": total_bytes,
        "total_cycle": total_cycle,
        "interconnect_time_est": f"{interconnect_time:.6g}",
        "interconnect_fraction_est": f"{interconnect_time / total_cycle:.12g}",
        "speedup_vs_pcie": "",
        "status": "OK",
        "run_dir": str(case_dir),
    }


def add_speedups(rows):
    by_key = {(r["workload"], r["memory_mode"], r["variant"]): r for r in rows}
    for row in rows:
        if row["variant"] == "pcie":
            row["speedup_vs_pcie"] = "1"
            continue
        pcie = by_key.get((row["workload"], row["memory_mode"], "pcie"))
        if pcie:
            row["speedup_vs_pcie"] = f"{pcie['total_cycle'] / row['total_cycle']:.12g}"


def write_csv(path, rows):
    add_speedups(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["workload"], r["memory_mode"], r["variant"])):
            writer.writerow(row)
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--w1-size", default=str(W1_SIZE))
    parser.add_argument(
        "--w2-matrices",
        default=",".join(f"{name}:{size}" for name, size in W2_MATRICES),
        help="Comma list of name:size entries. Suffixes like MB/GiB are accepted.",
    )
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--run-root", default="")
    parser.add_argument("--csv", default=str(RESULTS / "llama70b_layer_workloads.csv"))
    parser.add_argument("--popnet-window", type=int, default=DEFAULT_POPNET_WINDOW)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    workloads = {
        "w1_monolithic_qd1": [("layer", parse_size(args.w1_size))],
        "w2_matrix_seq_qd1": parse_matrix_list(args.w2_matrices),
    }
    cases = [
        (workload, memory_mode, variant)
        for workload in workloads
        for memory_mode in ("cold", "hot")
        for variant in ("pcie", "ucie")
    ]
    run_root = (Path(args.run_root) if args.run_root else ROOT / f"llama70b_layer_workloads_{time.strftime('%Y%m%d_%H%M%S')}").resolve()

    print(f"run_root={run_root}")
    print(f"jobs={args.jobs} popnet_window={args.popnet_window}")
    for workload, sizes in workloads.items():
        print(f"{workload}: requests={len(sizes)} total_bytes={sum(size for _, size in sizes)}")
    for workload, memory_mode, variant in cases:
        print(f"case={workload}_{memory_mode}_{variant}")
    if args.dry_run:
        return 0

    rows = []
    failures = []
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {
            executor.submit(run_case, workload, memory_mode, variant, workloads[workload], run_root, args.popnet_window): (
                workload,
                memory_mode,
                variant,
            )
            for workload, memory_mode, variant in cases
        }
        for future in as_completed(futures):
            workload, memory_mode, variant = futures[future]
            try:
                row = future.result()
                rows.append(row)
                write_csv(Path(args.csv), rows)
                print(
                    f"done {workload}_{memory_mode}_{variant}: "
                    f"cycles={row['total_cycle']} inter={row['interconnect_time_est']} "
                    f"inter/total={row['interconnect_fraction_est']}",
                    flush=True,
                )
            except Exception as exc:
                failures.append((workload, memory_mode, variant, exc))
                print(f"ERROR {workload}_{memory_mode}_{variant}: {exc}", file=sys.stderr, flush=True)

    if rows:
        write_csv(Path(args.csv), rows)
        print(f"wrote {args.csv}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
