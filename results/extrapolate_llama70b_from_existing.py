#!/usr/bin/env python3
"""Extrapolate Llama-3-70B layer streaming from existing validated QD1 sweeps."""
import argparse
import csv
from pathlib import Path


BASE = Path(__file__).parent
COLD_CSV = BASE / "pcie_vs_ucie_throughput.csv"
HOT_CSV = BASE / "pcie_vs_ucie_hot_qd1.csv"
OUT_CSV = BASE / "llama70b_layer_existing_extrapolation.csv"

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

FIELDS = [
    "workload",
    "memory_mode",
    "variant",
    "total_bytes",
    "request_count",
    "estimated_total_cycle",
    "estimated_interconnect_cycle",
    "interconnect_fraction_est",
    "speedup_vs_pcie",
    "fit_min_size",
    "fit_points",
    "fit_r2_total",
    "fit_slope_total_cycle_per_byte",
    "fit_intercept_total_cycle",
]


def read_rows(path, memory_mode):
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for row in rows:
        out.append({
            "memory_mode": memory_mode,
            "variant": row["variant"],
            "size_bytes": int(row["size_bytes"]),
            "final_cycle": int(row["final_cycle"]),
            "interconnect": float(row["avg_interconnect_delay"]) * 2.0,
        })
    return out


def fit_linear(points):
    n = len(points)
    if n < 2:
        raise ValueError("need at least two points")
    xs = [float(x) for x, _ in points]
    ys = [float(y) for _, y in points]
    mx = sum(xs) / n
    my = sum(ys) / n
    ssx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / ssx
    intercept = my - slope * mx
    pred = [intercept + slope * x for x in xs]
    sst = sum((y - my) ** 2 for y in ys)
    sse = sum((y - p) ** 2 for y, p in zip(ys, pred))
    r2 = 1.0 if sst == 0 else 1.0 - sse / sst
    return intercept, slope, r2


def estimate(rows, min_fit_size):
    estimates = []
    workloads = [
        ("w1_monolithic_qd1", [W1_SIZE]),
        ("w2_matrix_seq_qd1", [size for _, size in W2_MATRICES]),
    ]
    for memory_mode in ("cold", "hot"):
        for variant in ("pcie", "ucie"):
            subset = [
                r for r in rows
                if r["memory_mode"] == memory_mode
                and r["variant"] == variant
                and r["size_bytes"] >= min_fit_size
            ]
            total_i, total_s, total_r2 = fit_linear([(r["size_bytes"], r["final_cycle"]) for r in subset])
            inter_i, inter_s, _ = fit_linear([(r["size_bytes"], r["interconnect"]) for r in subset])
            for workload, sizes in workloads:
                total = sum(total_i + total_s * size for size in sizes)
                inter = sum(inter_i + inter_s * size for size in sizes)
                estimates.append({
                    "workload": workload,
                    "memory_mode": memory_mode,
                    "variant": variant,
                    "total_bytes": sum(sizes),
                    "request_count": len(sizes),
                    "estimated_total_cycle": f"{total:.6f}",
                    "estimated_interconnect_cycle": f"{inter:.6f}",
                    "interconnect_fraction_est": f"{inter / total:.12g}",
                    "speedup_vs_pcie": "",
                    "fit_min_size": min_fit_size,
                    "fit_points": len(subset),
                    "fit_r2_total": f"{total_r2:.12g}",
                    "fit_slope_total_cycle_per_byte": f"{total_s:.12g}",
                    "fit_intercept_total_cycle": f"{total_i:.6f}",
                })

    by_key = {(r["workload"], r["memory_mode"], r["variant"]): r for r in estimates}
    for row in estimates:
        if row["variant"] == "pcie":
            row["speedup_vs_pcie"] = "1"
            continue
        pcie = by_key[(row["workload"], row["memory_mode"], "pcie")]
        row["speedup_vs_pcie"] = f"{float(pcie['estimated_total_cycle']) / float(row['estimated_total_cycle']):.12g}"
    return estimates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-fit-size", type=int, default=524288)
    parser.add_argument("--out", default=str(OUT_CSV))
    args = parser.parse_args()

    rows = read_rows(COLD_CSV, "cold") + read_rows(HOT_CSV, "hot")
    estimates = estimate(rows, args.min_fit_size)

    out = Path(args.out)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in sorted(estimates, key=lambda r: (r["workload"], r["memory_mode"], r["variant"])):
            writer.writerow(row)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
