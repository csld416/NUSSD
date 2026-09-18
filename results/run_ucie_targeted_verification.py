#!/usr/bin/env python3
"""Targeted UCIe verification for selected PCIe-characterized points."""
import argparse
import csv
import os
import re
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
POPNET_TO_SIM_CYCLE = 1000.0

DEFAULT_PCIE_CSV = RESULTS / "pcie_p_characterization_8ch_onfi52.csv"
DEFAULT_CSV = RESULTS / "ucie_targeted_verification.csv"
DEFAULT_LOG = RESULTS / "ucie_targeted_verification.out"
DEFAULT_RUN_ROOT = ROOT / "ucie_targeted_verification"
DEFAULT_POINTS = (
    "cold:4KB:8,"
    "cold:64KB:16,"
    "cold:4MB:4,"
    "hot:64KB:1,"
    "hot:16KB:8,"
    "hot:4MB:16"
)
DEFAULT_LINK_SPEEDUP = 3.66

FIELDNAMES = [
    "memory_mode",
    "variant",
    "size_bytes",
    "queue_depth",
    "total_bytes",
    "status",
    "started_at_taipei",
    "done_at_taipei",
    "final_cycle",
    "t_request_cycle",
    "t_link_occupied_cycle",
    "t_link_sum_cycle",
    "t_nonlink_wall_cycle",
    "p_link_occupied_fraction",
    "link_sum_over_request",
    "throughput_bytes_per_cycle",
    "bench_records",
    "delay_records",
    "popnet_tx_count",
    "popnet_finished",
    "error",
    "run_dir",
    "pcie_final_cycle",
    "pcie_p_wall",
    "predicted_ucie_cycle",
    "predicted_speedup",
    "measured_speedup",
    "speedup_error_fraction",
]


def now_taipei():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 8 * 3600))


def parse_size(text):
    raw = text.strip().lower().replace("_", "")
    scales = [
        ("gib", 1024**3),
        ("gb", 1000**3),
        ("mib", 1024**2),
        ("mb", 1024**2),
        ("kib", 1024),
        ("kb", 1024),
    ]
    for suffix, scale in scales:
        if raw.endswith(suffix):
            return int(float(raw[: -len(suffix)]) * scale)
    return int(raw, 0)


def parse_points(text):
    points = []
    for raw in text.split(","):
        raw = raw.strip()
        if not raw:
            continue
        mode, size, qd = raw.split(":")
        if mode not in ("cold", "hot"):
            raise ValueError(f"invalid memory mode: {mode}")
        points.append((mode, parse_size(size), int(qd, 0)))
    return points


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def load_existing(path):
    if not path.exists():
        return {}
    with path.open(newline="") as f:
        return {
            (row["memory_mode"], int(row["size_bytes"]), int(row["queue_depth"])): row
            for row in csv.DictReader(f)
        }


def load_pcie_rows(path):
    with path.open(newline="") as f:
        rows = {}
        for row in csv.DictReader(f):
            key = (row["memory_mode"], int(row["size_bytes"]), int(row["queue_depth"]))
            rows[key] = row
    return rows


def patch_config(template, out_path, size, qd):
    text = template.read_text()
    text = re.sub(r'args: \["4096"(?:,\s*"[0-9]+")?\]', f'args: ["{size}", "{qd}"]', text, count=1)
    text = re.sub(
        r'(\n      - ")(?:4096)("\n      - ")(?:[0-9]+)(")',
        f"\\g<1>{size}\\g<2>{qd}\\g<3>",
        text,
        count=1,
    )
    out_path.write_text(text)


def parse_popnet_counts(run_dir):
    tx_count = ""
    finished = ""
    for log in sorted(run_dir.glob("proc_r*_p2_t0/popnet_0.log")):
        text = log.read_text(errors="replace")
        tx = re.findall(r"Transaction count:\s+([0-9]+)", text)
        fin = re.findall(r"total finished:\s+([0-9]+)", text)
        if tx:
            tx_count = int(tx[-1])
        if fin:
            finished = int(fin[-1])
    return tx_count, finished


def union_length(intervals):
    if not intervals:
        return 0.0
    intervals = sorted(intervals)
    total = 0.0
    cur_start, cur_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            total += cur_end - cur_start
            cur_start, cur_end = start, end
    total += cur_end - cur_start
    return total


def build_rows(points, run_root, existing, pcie_rows, link_speedup, force):
    rows = []
    for mode, size, qd in points:
        key = (mode, size, qd)
        if key not in pcie_rows:
            raise KeyError(f"missing PCIe baseline for {key}")
        if key in existing and not force and existing[key].get("status") == "OK":
            rows.append(existing[key])
            continue

        pcie = pcie_rows[key]
        pcie_final = float(pcie["final_cycle"])
        pcie_p = float(pcie["p_link_occupied_fraction"])
        predicted_speedup = 1.0 / (1.0 - pcie_p + pcie_p / link_speedup)
        predicted_ucie = pcie_final / predicted_speedup
        run_dir = run_root / f"{mode}_ucie_{size}_qd{qd}"
        rows.append({
            "memory_mode": mode,
            "variant": "ucie",
            "size_bytes": size,
            "queue_depth": qd,
            "total_bytes": size * qd,
            "status": "PENDING",
            "started_at_taipei": "",
            "done_at_taipei": "",
            "final_cycle": "",
            "t_request_cycle": "",
            "t_link_occupied_cycle": "",
            "t_link_sum_cycle": "",
            "t_nonlink_wall_cycle": "",
            "p_link_occupied_fraction": "",
            "link_sum_over_request": "",
            "throughput_bytes_per_cycle": "",
            "bench_records": "",
            "delay_records": "",
            "popnet_tx_count": "",
            "popnet_finished": "",
            "error": "",
            "run_dir": str(run_dir),
            "pcie_final_cycle": pcie["final_cycle"],
            "pcie_p_wall": pcie["p_link_occupied_fraction"],
            "predicted_ucie_cycle": f"{predicted_ucie:.6f}",
            "predicted_speedup": f"{predicted_speedup:.12g}",
            "measured_speedup": "",
            "speedup_error_fraction": "",
        })
    return rows


def run_sim(row):
    mode = row["memory_mode"]
    size = int(row["size_bytes"])
    qd = int(row["queue_depth"])
    run_dir = Path(row["run_dir"])
    cfg = run_dir / f"{mode}_ucie_{size}_qd{qd}.yml"
    template = ROOT / "config" / f"legosim_ucie{'_hot' if mode == 'hot' else ''}.yml"

    run_dir.mkdir(parents=True, exist_ok=True)
    patch_config(template, cfg, size, qd)

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

    out_path = run_dir / "interchiplet.out"
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
    delays = []
    link_intervals = []
    for line in delay_path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 7:
            start_cycle = float(parts[0]) * POPNET_TO_SIM_CYCLE
            delay_cycle = float(parts[-1]) * POPNET_TO_SIM_CYCLE
            end_cycle = start_cycle + delay_cycle
            delays.append(delay_cycle)
            clipped_start = max(0.0, start_cycle)
            clipped_end = min(float(final_cycle), end_cycle)
            if clipped_end > clipped_start:
                link_intervals.append((clipped_start, clipped_end))

    expected = 2 * qd
    if bench_records != expected:
        raise RuntimeError(f"bench records {bench_records}, expected {expected}")
    if len(delays) != expected:
        raise RuntimeError(f"delay records {len(delays)}, expected {expected}")

    tx_count, finished = parse_popnet_counts(run_dir)
    if tx_count != expected or finished != expected:
        raise RuntimeError(f"PopNet finished {finished}/{tx_count}, expected {expected}")

    t_link_sum = sum(delays)
    t_link_occupied = union_length(link_intervals)
    total_bytes = size * qd
    pcie_final = float(row["pcie_final_cycle"])
    predicted_speedup = float(row["predicted_speedup"])
    measured_speedup = pcie_final / final_cycle

    row.update({
        "status": "OK",
        "done_at_taipei": now_taipei(),
        "final_cycle": final_cycle,
        "t_request_cycle": final_cycle,
        "t_link_occupied_cycle": f"{t_link_occupied:.6f}",
        "t_link_sum_cycle": f"{t_link_sum:.6f}",
        "t_nonlink_wall_cycle": f"{final_cycle - t_link_occupied:.6f}",
        "p_link_occupied_fraction": f"{t_link_occupied / final_cycle:.12g}",
        "link_sum_over_request": f"{t_link_sum / final_cycle:.12g}",
        "throughput_bytes_per_cycle": f"{total_bytes / final_cycle:.12g}",
        "bench_records": bench_records,
        "delay_records": len(delays),
        "popnet_tx_count": tx_count,
        "popnet_finished": finished,
        "error": "",
        "measured_speedup": f"{measured_speedup:.12g}",
        "speedup_error_fraction": f"{(measured_speedup - predicted_speedup) / predicted_speedup:.12g}",
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--points", default=DEFAULT_POINTS)
    parser.add_argument("--pcie-csv", default=str(DEFAULT_PCIE_CSV))
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    parser.add_argument("--link-speedup", type=float, default=DEFAULT_LINK_SPEEDUP)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    points = parse_points(args.points)
    csv_path = Path(args.csv).resolve()
    log_path = Path(args.log).resolve()
    run_root = Path(args.run_root).resolve()
    existing = {} if args.force else load_existing(csv_path)
    pcie_rows = load_pcie_rows(Path(args.pcie_csv))
    rows = build_rows(points, run_root, existing, pcie_rows, args.link_speedup, args.force)
    write_rows(csv_path, rows)

    print(f"run_root={run_root}", flush=True)
    print(f"csv={csv_path}", flush=True)
    print(f"cases={len(rows)} sequential=true link_speedup={args.link_speedup}", flush=True)
    if args.dry_run:
        return 0

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as log:
        log.write(f"start {now_taipei()} cases={len(rows)} sequential=true link_speedup={args.link_speedup}\n")

    failures = 0
    for idx, row in enumerate(rows, start=1):
        if row.get("status") == "OK" and not args.force:
            print(
                f"skip {idx}/{len(rows)} {row['memory_mode']}_ucie_{row['size_bytes']}_qd{row['queue_depth']}",
                flush=True,
            )
            continue

        case_name = f"{row['memory_mode']}_ucie_{row['size_bytes']}_qd{row['queue_depth']}"
        row["status"] = "RUNNING"
        row["started_at_taipei"] = now_taipei()
        row["done_at_taipei"] = ""
        row["error"] = ""
        write_rows(csv_path, rows)
        print(f"run {idx}/{len(rows)} {case_name}", flush=True)
        with log_path.open("a") as log:
            log.write(f"run {idx}/{len(rows)} {case_name} started_at={row['started_at_taipei']}\n")

        try:
            run_sim(row)
            print(
                f"done {case_name}: cycles={row['final_cycle']} "
                f"pred_speedup={row['predicted_speedup']} "
                f"meas_speedup={row['measured_speedup']} "
                f"p_wall_ucie={row['p_link_occupied_fraction']} "
                f"done_at={row['done_at_taipei']}",
                flush=True,
            )
            with log_path.open("a") as log:
                log.write(
                    f"done {case_name}: cycles={row['final_cycle']} "
                    f"pred_speedup={row['predicted_speedup']} "
                    f"meas_speedup={row['measured_speedup']} "
                    f"p_wall_ucie={row['p_link_occupied_fraction']} "
                    f"done_at={row['done_at_taipei']}\n"
                )
        except Exception as exc:
            failures += 1
            row["status"] = "FAIL"
            row["done_at_taipei"] = now_taipei()
            row["error"] = str(exc)
            print(f"FAIL {case_name}: {exc}", file=sys.stderr, flush=True)
            with log_path.open("a") as log:
                log.write(f"FAIL {case_name}: {exc} done_at={row['done_at_taipei']}\n")
        finally:
            write_rows(csv_path, rows)

    with log_path.open("a") as log:
        log.write(f"finish {now_taipei()} failures={failures}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
