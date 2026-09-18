#!/usr/bin/env python3
"""Validate and plot the PCIe-only p-characterization sweep."""
import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "results" / "pcie_p_characterization_8ch_onfi52.csv"
DEFAULT_VALIDATION = ROOT / "results" / "pcie_p_characterization_8ch_onfi52_validation.csv"
DEFAULT_HEATMAP = ROOT / "results" / "pcie_p_characterization_8ch_onfi52_p_heatmap.png"
DEFAULT_LINES = ROOT / "results" / "pcie_p_characterization_8ch_onfi52_p_lines.png"


def size_label(size):
    size = int(size)
    units = [("MB", 1024 * 1024), ("KB", 1024)]
    for suffix, scale in units:
        if size % scale == 0:
            return f"{size // scale}{suffix}"
    return f"{size}B"


def load_rows(path):
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["size_bytes"] = int(row["size_bytes"])
        row["queue_depth"] = int(row["queue_depth"])
        row["final_cycle"] = int(row["final_cycle"])
        row["p_link_occupied_fraction"] = float(row["p_link_occupied_fraction"])
        row["bench_records"] = int(row["bench_records"])
        row["delay_records"] = int(row["delay_records"])
        row["popnet_tx_count"] = int(row["popnet_tx_count"])
        row["popnet_finished"] = int(row["popnet_finished"])
    return rows


def write_validation(rows, path):
    fields = [
        "memory_mode",
        "size_bytes",
        "queue_depth",
        "expected_records",
        "bench_records",
        "delay_records",
        "popnet_tx_count",
        "popnet_finished",
        "status",
        "valid",
        "issue",
    ]
    summary = []
    for row in rows:
        expected = 2 * row["queue_depth"]
        issues = []
        if row["status"] != "OK":
            issues.append(f"status={row['status']}")
        for field in ("bench_records", "delay_records", "popnet_tx_count", "popnet_finished"):
            if row[field] != expected:
                issues.append(f"{field}={row[field]} expected={expected}")
        summary.append({
            "memory_mode": row["memory_mode"],
            "size_bytes": row["size_bytes"],
            "queue_depth": row["queue_depth"],
            "expected_records": expected,
            "bench_records": row["bench_records"],
            "delay_records": row["delay_records"],
            "popnet_tx_count": row["popnet_tx_count"],
            "popnet_finished": row["popnet_finished"],
            "status": row["status"],
            "valid": "yes" if not issues else "no",
            "issue": "; ".join(issues),
        })

    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary)
    return summary


def plot_heatmap(rows, path):
    sizes = sorted({row["size_bytes"] for row in rows})
    qds = sorted({row["queue_depth"] for row in rows})
    modes = ["cold", "hot"]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    vmax = max(row["p_link_occupied_fraction"] for row in rows)

    for ax, mode in zip(axes, modes):
        table = {
            (row["size_bytes"], row["queue_depth"]): row["p_link_occupied_fraction"]
            for row in rows
            if row["memory_mode"] == mode
        }
        matrix = [[table[(size, qd)] for qd in qds] for size in sizes]
        im = ax.imshow(matrix, origin="lower", aspect="auto", vmin=0, vmax=vmax, cmap="viridis")
        ax.set_title(f"{mode.capitalize()} PCIe link occupation")
        ax.set_xlabel("Queue depth")
        ax.set_ylabel("Request size")
        ax.set_xticks(range(len(qds)), [str(qd) for qd in qds])
        ax.set_yticks(range(len(sizes)), [size_label(size) for size in sizes])
        for y, size in enumerate(sizes):
            for x, qd in enumerate(qds):
                value = table[(size, qd)]
                color = "white" if value > vmax * 0.5 else "black"
                ax.text(x, y, f"{value:.2f}", ha="center", va="center", fontsize=8, color=color)

    cbar = fig.colorbar(im, ax=axes, shrink=0.9)
    cbar.set_label("p_wall = link occupied / request time")
    fig.savefig(path, dpi=200)
    plt.close(fig)


def plot_lines(rows, path):
    sizes = sorted({row["size_bytes"] for row in rows})
    qds = sorted({row["queue_depth"] for row in rows})
    modes = ["cold", "hot"]

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True, constrained_layout=True)
    markers = ["o", "s", "^", "D", "v", "P"]

    for ax, mode in zip(axes, modes):
        for idx, qd in enumerate(qds):
            ys = [
                row["p_link_occupied_fraction"]
                for size in sizes
                for row in rows
                if row["memory_mode"] == mode and row["size_bytes"] == size and row["queue_depth"] == qd
            ]
            ax.plot(
                [size_label(size) for size in sizes],
                ys,
                marker=markers[idx % len(markers)],
                linewidth=1.8,
                label=f"QD{qd}",
            )
        ax.set_title(f"{mode.capitalize()} PCIe")
        ax.set_xlabel("Request size")
        ax.grid(True, alpha=0.3)
        ax.set_ylim(0, 1.0)
        ax.tick_params(axis="x", rotation=30)

    axes[0].set_ylabel("p_wall = link occupied / request time")
    axes[1].legend(title="Queue depth", loc="center left", bbox_to_anchor=(1.02, 0.5))
    fig.savefig(path, dpi=200)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--validation", default=str(DEFAULT_VALIDATION))
    parser.add_argument("--heatmap", default=str(DEFAULT_HEATMAP))
    parser.add_argument("--lines", default=str(DEFAULT_LINES))
    args = parser.parse_args()

    rows = load_rows(Path(args.input))
    validation = write_validation(rows, Path(args.validation))
    invalid = [row for row in validation if row["valid"] != "yes"]
    plot_heatmap(rows, Path(args.heatmap))
    plot_lines(rows, Path(args.lines))

    print(f"rows={len(rows)} invalid={len(invalid)}")
    print(f"validation={args.validation}")
    print(f"heatmap={args.heatmap}")
    print(f"lines={args.lines}")
    if invalid:
        for row in invalid[:10]:
            print(f"INVALID {row}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
