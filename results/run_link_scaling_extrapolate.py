#!/usr/bin/env python3
"""Measure PopNet scaling at tractable sizes and extrapolate to Llama layer size.

This runner measures QD1 monolithic transfers for cold/hot x PCIe/UCIe at a
bounded size list, then fits a linear model per case:

  cycles(size) = intercept + slope * bytes

The fitted model is used to estimate:

- W1: one monolithic Llama-3-70B transformer block transfer.
- W2: seven sequential matrix transfers summed by the same model.
"""
import argparse
import csv
import math
import os
import re
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
DEFAULT_SIZES = "4MiB,8MiB,16MiB,32MiB,64MiB"
DEFAULT_POPNET_WINDOW = 10_000_000_000_000
DEFAULT_TIMEOUT = 0
POPNET_TO_SIM_CYCLE = 1000.0

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

MEASURE_FIELDS = [
    "memory_mode",
    "variant",
    "size_bytes",
    "final_cycle",
    "throughput_bytes_per_cycle",
    "interconnect_time_est",
    "interconnect_fraction_est",
    "bench_records",
    "popnet_tx_count",
    "popnet_finished",
    "status",
    "error",
    "run_dir",
]

ESTIMATE_FIELDS = [
    "workload",
    "memory_mode",
    "variant",
    "total_bytes",
    "request_count",
    "estimated_total_cycle",
    "estimated_interconnect_cycle",
    "interconnect_fraction_est",
    "speedup_vs_pcie",
    "fit_points",
    "fit_r2_total",
    "fit_slope_total_cycle_per_byte",
    "fit_intercept_total_cycle",
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


def parse_sizes(text):
    return [parse_size(part) for part in text.split(",") if part.strip()]


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


def parse_run(run_dir, size):
    output = (run_dir / "interchiplet.out").read_text(errors="replace")
    cycles = re.findall(r"Benchmark elapses ([0-9]+) cycle\.", output)
    if not cycles:
        raise RuntimeError("missing final cycle")
    final_cycle = int(cycles[-1])

    bench_records = len((run_dir / "bench.txt").read_text().splitlines())
    if bench_records != 2:
        raise RuntimeError(f"bench records {bench_records}, expected 2")

    delays = []
    for line in (run_dir / "delayInfo.txt").read_text().splitlines():
        parts = line.split()
        if parts:
            delays.append(float(parts[-1]))
    if len(delays) != 2:
        raise RuntimeError(f"delay records {len(delays)}, expected 2")

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
        raise RuntimeError(f"PopNet finished {finished}/{tx_count}, expected 2")

    interconnect = sum(delays) * POPNET_TO_SIM_CYCLE
    return {
        "size_bytes": size,
        "final_cycle": final_cycle,
        "throughput_bytes_per_cycle": f"{size / final_cycle:.12g}",
        "interconnect_time_est": f"{interconnect:.6g}",
        "interconnect_fraction_est": f"{interconnect / final_cycle:.12g}",
        "bench_records": bench_records,
        "popnet_tx_count": tx_count,
        "popnet_finished": finished,
        "status": "OK",
        "error": "",
    }


def run_one(memory_mode, variant, size, run_root, popnet_window, timeout):
    run_dir = run_root / f"{memory_mode}_{variant}_{size}"
    cfg = run_dir / f"{memory_mode}_{variant}_{size}.yml"
    run_dir.mkdir(parents=True, exist_ok=True)
    patch_config(ROOT / "config" / f"legosim_{variant}.yml", cfg, size, memory_mode, popnet_window)

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

    proc = None
    try:
        with (run_dir / "interchiplet.out").open("w") as out:
            proc = subprocess.Popen(
                cmd,
                cwd=ROOT,
                env=env,
                stdout=out,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            proc.wait(timeout=None if timeout <= 0 else timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"interchiplet failed with exit code {proc.returncode}")
        row = parse_run(run_dir, size)
    except subprocess.TimeoutExpired:
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=10)
            except Exception:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    pass
        row = {
            "size_bytes": size,
            "final_cycle": "",
            "throughput_bytes_per_cycle": "",
            "interconnect_time_est": "",
            "interconnect_fraction_est": "",
            "bench_records": "",
            "popnet_tx_count": "",
            "popnet_finished": "",
            "status": "TIMEOUT",
            "error": f"timeout after {timeout}s",
        }
    except Exception as exc:
        row = {
            "size_bytes": size,
            "final_cycle": "",
            "throughput_bytes_per_cycle": "",
            "interconnect_time_est": "",
            "interconnect_fraction_est": "",
            "bench_records": "",
            "popnet_tx_count": "",
            "popnet_finished": "",
            "status": "FAIL",
            "error": str(exc),
        }

    row["memory_mode"] = memory_mode
    row["variant"] = variant
    row["run_dir"] = str(run_dir)
    return row


def read_existing(path):
    if not path.exists():
        return {}
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return {
        (row["memory_mode"], row["variant"], int(row["size_bytes"])): row
        for row in rows
        if row.get("status") == "OK"
    }


def write_measurements(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MEASURE_FIELDS)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["size_bytes"], r["memory_mode"], r["variant"])):
            writer.writerow(row)
    tmp.replace(path)


def fit_linear(points):
    n = len(points)
    if n < 2:
        return None
    xs = [float(x) for x, _ in points]
    ys = [float(y) for _, y in points]
    mx = sum(xs) / n
    my = sum(ys) / n
    ssx = sum((x - mx) ** 2 for x in xs)
    if ssx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / ssx
    intercept = my - slope * mx
    pred = [intercept + slope * x for x in xs]
    sst = sum((y - my) ** 2 for y in ys)
    sse = sum((y - p) ** 2 for y, p in zip(ys, pred))
    r2 = 1.0 if sst == 0 else 1.0 - sse / sst
    return intercept, slope, r2


def estimate_workloads(measured_rows):
    ok = [r for r in measured_rows if r.get("status") == "OK"]
    estimates = []
    for memory_mode in ("cold", "hot"):
        for variant in ("pcie", "ucie"):
            rows = [r for r in ok if r["memory_mode"] == memory_mode and r["variant"] == variant]
            total_fit = fit_linear([(int(r["size_bytes"]), int(r["final_cycle"])) for r in rows])
            inter_fit = fit_linear([(int(r["size_bytes"]), float(r["interconnect_time_est"])) for r in rows])
            if not total_fit or not inter_fit:
                continue
            total_i, total_s, total_r2 = total_fit
            inter_i, inter_s, _ = inter_fit

            workloads = [
                ("w1_monolithic_qd1", [W1_SIZE]),
                ("w2_matrix_seq_qd1", [size for _, size in W2_MATRICES]),
            ]
            for workload, sizes in workloads:
                total_cycle = sum(total_i + total_s * size for size in sizes)
                inter_cycle = sum(inter_i + inter_s * size for size in sizes)
                estimates.append({
                    "workload": workload,
                    "memory_mode": memory_mode,
                    "variant": variant,
                    "total_bytes": sum(sizes),
                    "request_count": len(sizes),
                    "estimated_total_cycle": f"{total_cycle:.6f}",
                    "estimated_interconnect_cycle": f"{inter_cycle:.6f}",
                    "interconnect_fraction_est": f"{inter_cycle / total_cycle:.12g}" if total_cycle else "",
                    "speedup_vs_pcie": "",
                    "fit_points": len(rows),
                    "fit_r2_total": f"{total_r2:.12g}",
                    "fit_slope_total_cycle_per_byte": f"{total_s:.12g}",
                    "fit_intercept_total_cycle": f"{total_i:.6f}",
                })

    by_key = {(r["workload"], r["memory_mode"], r["variant"]): r for r in estimates}
    for row in estimates:
        if row["variant"] == "pcie":
            row["speedup_vs_pcie"] = "1"
            continue
        pcie = by_key.get((row["workload"], row["memory_mode"], "pcie"))
        if pcie:
            row["speedup_vs_pcie"] = f"{float(pcie['estimated_total_cycle']) / float(row['estimated_total_cycle']):.12g}"
    return estimates


def write_estimates(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ESTIMATE_FIELDS)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["workload"], r["memory_mode"], r["variant"])):
            writer.writerow(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default=DEFAULT_SIZES)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--run-root", default="")
    parser.add_argument("--measure-csv", default=str(RESULTS / "link_scaling_measurements.csv"))
    parser.add_argument("--estimate-csv", default=str(RESULTS / "llama70b_layer_estimates.csv"))
    parser.add_argument("--popnet-window", type=int, default=DEFAULT_POPNET_WINDOW)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Per-case timeout in seconds; 0 disables timeout.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sizes = parse_sizes(args.sizes)
    run_root = (Path(args.run_root) if args.run_root else ROOT / f"link_scaling_runs_{time.strftime('%Y%m%d_%H%M%S')}").resolve()
    cases = [(memory_mode, variant, size) for size in sizes for memory_mode in ("cold", "hot") for variant in ("pcie", "ucie")]

    print(f"run_root={run_root}")
    timeout_label = "disabled" if args.timeout <= 0 else f"{args.timeout}s"
    print(f"sizes={','.join(str(s) for s in sizes)} jobs={args.jobs} timeout={timeout_label}")
    print(f"cases={len(cases)}")
    if args.dry_run:
        return 0

    measure_csv = Path(args.measure_csv)
    existing = {} if args.force else read_existing(measure_csv)
    rows = list(existing.values())
    failures = []

    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {}
        for memory_mode, variant, size in cases:
            key = (memory_mode, variant, size)
            if key in existing:
                print(f"skip {memory_mode}_{variant}_{size}", flush=True)
                continue
            futures[executor.submit(run_one, memory_mode, variant, size, run_root, args.popnet_window, args.timeout)] = key

        for future in as_completed(futures):
            memory_mode, variant, size = futures[future]
            row = future.result()
            rows.append(row)
            write_measurements(measure_csv, rows)
            if row["status"] == "OK":
                print(
                    f"done {memory_mode}_{variant}_{size}: cycles={row['final_cycle']} "
                    f"inter={row['interconnect_time_est']} inter/total={row['interconnect_fraction_est']}",
                    flush=True,
                )
            else:
                failures.append(row)
                print(f"{row['status']} {memory_mode}_{variant}_{size}: {row['error']}", file=sys.stderr, flush=True)

    estimates = estimate_workloads(rows)
    if estimates:
        write_estimates(Path(args.estimate_csv), estimates)
        print(f"wrote {args.estimate_csv}")
    print(f"wrote {args.measure_csv}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
