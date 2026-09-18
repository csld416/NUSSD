#!/usr/bin/env python3
"""Sequential baseline-link characterization of link fraction p.

This harness sweeps request size, queue depth, and hot/cold SSD behavior using
the active 8-channel ONFI-5.2-approx configs. It intentionally runs one
simulation at a time so PopNet jobs do not contend with each other on the host.
"""
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
DEFAULT_SIZES = "4KB,16KB,64KB,256KB,1MB,4MB"
DEFAULT_QDS = "1,2,4,8,16"
DEFAULT_VARIANT = "ufs4"
DEFAULT_RUN_ROOT = ROOT / "ufs4_p_characterization_8ch_onfi52"
DEFAULT_CSV = RESULTS / "ufs4_p_characterization_8ch_onfi52.csv"
DEFAULT_LOG = RESULTS / "ufs4_p_characterization_8ch_onfi52.out"

FLIT_WORDS = {
    "pcie": 2,
    "ufs4": 1,
    "ucie": 8,
}

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


def parse_list(text, parser):
    return [parser(part) for part in text.split(",") if part.strip()]


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    tmp.replace(path)


def load_existing(path):
    if not path.exists():
        return {}
    with path.open(newline="") as f:
        return {
            (
                row["memory_mode"],
                row.get("variant", "pcie"),
                int(row["size_bytes"]),
                int(row["queue_depth"]),
            ): row
            for row in csv.DictReader(f)
        }


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


def phase2_cycle_ps(config_path):
    """Return picoseconds per PopNet cycle from the phase2 clock rate."""
    in_phase2 = False
    for line in config_path.read_text().splitlines():
        stripped = line.strip()
        if stripped == "phase2:":
            in_phase2 = True
            continue
        if in_phase2 and stripped.startswith("clock_rate:"):
            rate = float(stripped.split(":", 1)[1].strip())
            if rate <= 0:
                raise RuntimeError(f"invalid phase2 clock_rate {rate}")
            return 1.0 / rate
    raise RuntimeError(f"missing phase2 clock_rate in {config_path}")


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


def run_sim(row):
    memory_mode = row["memory_mode"]
    variant = row["variant"]
    size = int(row["size_bytes"])
    qd = int(row["queue_depth"])
    run_dir = Path(row["run_dir"])
    cfg = run_dir / f"{memory_mode}_{variant}_{size}_qd{qd}.yml"
    template = ROOT / "config" / f"legosim_{variant}{'_hot' if memory_mode == 'hot' else ''}.yml"

    run_dir.mkdir(parents=True, exist_ok=True)
    patch_config(template, cfg, size, qd)
    popnet_to_sim_cycle = phase2_cycle_ps(cfg)

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
        str(FLIT_WORDS[variant]),
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
            start_cycle = float(parts[0]) * popnet_to_sim_cycle
            delay_cycle = float(parts[-1]) * popnet_to_sim_cycle
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
    t_nonlink_wall = final_cycle - t_link_occupied
    total_bytes = size * qd

    row.update({
        "status": "OK",
        "done_at_taipei": now_taipei(),
        "final_cycle": final_cycle,
        "t_request_cycle": final_cycle,
        "t_link_occupied_cycle": f"{t_link_occupied:.6f}",
        "t_link_sum_cycle": f"{t_link_sum:.6f}",
        "t_nonlink_wall_cycle": f"{t_nonlink_wall:.6f}",
        "p_link_occupied_fraction": f"{t_link_occupied / final_cycle:.12g}",
        "link_sum_over_request": f"{t_link_sum / final_cycle:.12g}",
        "throughput_bytes_per_cycle": f"{total_bytes / final_cycle:.12g}",
        "bench_records": bench_records,
        "delay_records": len(delays),
        "popnet_tx_count": tx_count,
        "popnet_finished": finished,
        "error": "",
    })


def parse_modes(text):
    modes = [part.strip().lower() for part in text.split(",") if part.strip()]
    invalid = [mode for mode in modes if mode not in ("cold", "hot")]
    if invalid:
        raise ValueError(f"invalid mode(s): {','.join(invalid)}")
    return modes


def build_rows(sizes, qds, modes, variants, run_root, existing, force):
    rows = []
    for memory_mode in modes:
        for size in sizes:
            for qd in qds:
                for variant in variants:
                    key = (memory_mode, variant, size, qd)
                    run_dir = run_root / f"{memory_mode}_{variant}_{size}_qd{qd}"
                    if key in existing and not force and existing[key].get("status") == "OK":
                        rows.append(existing[key])
                        continue
                    rows.append({
                        "memory_mode": memory_mode,
                        "variant": variant,
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
                    })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default=DEFAULT_SIZES)
    parser.add_argument("--qds", default=DEFAULT_QDS)
    parser.add_argument("--modes", default="cold,hot")
    parser.add_argument("--variant", choices=tuple(FLIT_WORDS), default=DEFAULT_VARIANT)
    parser.add_argument("--variants", help="comma-separated variants; overrides --variant")
    parser.add_argument("--run-root", default=str(DEFAULT_RUN_ROOT))
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--log", default=str(DEFAULT_LOG))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sizes = parse_list(args.sizes, parse_size)
    qds = parse_list(args.qds, lambda s: int(s.strip(), 0))
    modes = parse_modes(args.modes)
    variants = parse_list(args.variants, str.strip) if args.variants else [args.variant]
    invalid_variants = [variant for variant in variants if variant not in FLIT_WORDS]
    if invalid_variants:
        parser.error(f"invalid variant(s): {','.join(invalid_variants)}")
    run_root = Path(args.run_root).resolve()
    csv_path = Path(args.csv).resolve()
    log_path = Path(args.log).resolve()

    existing = {} if args.force else load_existing(csv_path)
    rows = build_rows(sizes, qds, modes, variants, run_root, existing, args.force)
    write_rows(csv_path, rows)

    print(f"run_root={run_root}", flush=True)
    print(f"csv={csv_path}", flush=True)
    print(f"sizes={','.join(str(s) for s in sizes)}", flush=True)
    print(f"qds={','.join(str(q) for q in qds)}", flush=True)
    print(f"modes={','.join(modes)}", flush=True)
    print(f"variants={','.join(variants)}", flush=True)
    print(f"cases={len(rows)} sequential=true", flush=True)
    if args.dry_run:
        return 0

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as log:
        log.write(f"start {now_taipei()} cases={len(rows)} sequential=true\n")

    failures = 0
    for idx, row in enumerate(rows, start=1):
        if row.get("status") == "OK" and not args.force:
            print(
                f"skip {idx}/{len(rows)} {row['memory_mode']}_{row['variant']}_{row['size_bytes']}_qd{row['queue_depth']}",
                flush=True,
            )
            continue

        case_name = f"{row['memory_mode']}_{row['variant']}_{row['size_bytes']}_qd{row['queue_depth']}"
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
                f"link_occupied={row['t_link_occupied_cycle']} "
                f"p_wall={row['p_link_occupied_fraction']} "
                f"link_sum/request={row['link_sum_over_request']} "
                f"done_at={row['done_at_taipei']}",
                flush=True,
            )
            with log_path.open("a") as log:
                log.write(
                    f"done {case_name}: cycles={row['final_cycle']} "
                    f"link_occupied={row['t_link_occupied_cycle']} "
                    f"p_wall={row['p_link_occupied_fraction']} "
                    f"link_sum/request={row['link_sum_over_request']} "
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
