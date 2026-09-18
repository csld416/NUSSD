#!/usr/bin/env python3
"""Plot the PCIe/UCIe request-size x queue-depth sweep."""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


BASE = Path(__file__).parent
CSV_PATH = BASE / "pcie_vs_ucie_size_qd.csv"
OUT_PATH = BASE / "pcie_vs_ucie_size_qd.png"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#898781"


def size_label(n):
    if n >= 1024 * 1024:
        return f"{n // (1024 * 1024)}MB"
    return f"{n // 1024}KB"


def load_rows():
    with CSV_PATH.open(newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["status"] == "OK"]
    for row in rows:
        row["size_bytes"] = int(row["size_bytes"])
        row["queue_depth"] = int(row["queue_depth"])
        row["final_cycle"] = int(row["final_cycle"])
        row["throughput_bytes_per_cycle"] = float(row["throughput_bytes_per_cycle"])
        row["avg_interconnect_delay"] = float(row["avg_interconnect_delay"])
    return rows


def grid(rows, variants, sizes, qds, field):
    data = []
    for qd in qds:
        line = []
        for size in sizes:
            vals = [
                r[field]
                for r in rows
                if r["variant"] == variants and r["size_bytes"] == size and r["queue_depth"] == qd
            ]
            line.append(vals[0] if vals else float("nan"))
        data.append(line)
    return data


def main():
    rows = load_rows()
    sizes = sorted({r["size_bytes"] for r in rows})
    qds = sorted({r["queue_depth"] for r in rows})

    pcie = grid(rows, "pcie", sizes, qds, "throughput_bytes_per_cycle")
    ucie = grid(rows, "ucie", sizes, qds, "throughput_bytes_per_cycle")
    speedup = []
    for y, qd in enumerate(qds):
        line = []
        for x, size in enumerate(sizes):
            p = pcie[y][x]
            u = ucie[y][x]
            line.append(u / p if p else float("nan"))
        speedup.append(line)

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    fig.patch.set_facecolor(SURFACE)

    panels = [
        (axes[0], pcie, "PCIe throughput", "bytes/cycle"),
        (axes[1], ucie, "UCIe throughput", "bytes/cycle"),
        (axes[2], speedup, "UCIe / PCIe throughput", "speedup"),
    ]

    for ax, data, title, cbar_label in panels:
        ax.set_facecolor(SURFACE)
        image = ax.imshow(data, aspect="auto", origin="lower", cmap="viridis")
        ax.set_title(title, color=INK, fontsize=11)
        ax.set_xticks(range(len(sizes)))
        ax.set_xticklabels([size_label(s) for s in sizes], rotation=45, ha="right", color=INK)
        ax.set_yticks(range(len(qds)))
        ax.set_yticklabels([str(qd) for qd in qds], color=INK)
        ax.set_xlabel("request size", color=MUTED)
        ax.set_ylabel("queue depth", color=MUTED)
        ax.tick_params(colors=MUTED)
        for spine in ax.spines.values():
            spine.set_color(MUTED)
        cbar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label(cbar_label, color=MUTED)
        cbar.ax.tick_params(colors=MUTED)
        if cbar_label == "speedup":
            cbar.formatter = mticker.FormatStrFormatter("%.3fx")
            cbar.update_ticks()

    fig.suptitle(
        "Corrected PCIe vs UCIe sweep over host read size and outstanding requests",
        color=INK,
        fontsize=12,
    )
    fig.text(
        0.5,
        0.01,
        "Throughput = total bytes / final cycle; each point validates 2*QD bench records and PopNet finished transactions.",
        ha="center",
        fontsize=8,
        color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    fig.savefig(OUT_PATH, dpi=200, facecolor=SURFACE)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
