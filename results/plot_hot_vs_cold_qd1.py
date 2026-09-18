#!/usr/bin/env python3
"""Plot corrected cold-NAND versus cache-hot QD1 PCIe/UCIe sweeps."""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


BASE = Path(__file__).parent
COLD_CSV = BASE / "pcie_vs_ucie_throughput.csv"
HOT_CSV = BASE / "pcie_vs_ucie_hot_qd1.csv"
SUMMARY_CSV = BASE / "pcie_vs_ucie_hot_vs_cold_qd1_summary.csv"
OUT_PATH = BASE / "pcie_vs_ucie_hot_vs_cold_qd1.png"

INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
GREEN = "#2ca25f"
RED = "#d94841"


def read_rows(path):
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["size_bytes"] = int(row["size_bytes"])
        row["final_cycle"] = int(row["final_cycle"])
        row["avg_interconnect_delay"] = float(row["avg_interconnect_delay"])
    return rows


def size_label(size):
    if size >= 1024 * 1024:
        return f"{size // (1024 * 1024)}MB"
    return f"{size // 1024}KB"


def by_variant(rows, variant, field, sizes):
    return [next(r[field] for r in rows if r["variant"] == variant and r["size_bytes"] == size) for size in sizes]


def style_axis(ax):
    ax.set_facecolor(SURFACE)
    ax.set_xscale("log", basex=2)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(colors=MUTED)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)


def write_summary(cold, hot, sizes):
    with SUMMARY_CSV.open("w", newline="") as f:
        fields = [
            "size_bytes",
            "cold_pcie_cycle",
            "cold_ucie_cycle",
            "cold_gain_pct",
            "hot_pcie_cycle",
            "hot_ucie_cycle",
            "hot_gain_pct",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for size in sizes:
            cp = next(r for r in cold if r["variant"] == "pcie" and r["size_bytes"] == size)
            cu = next(r for r in cold if r["variant"] == "ucie" and r["size_bytes"] == size)
            hp = next(r for r in hot if r["variant"] == "pcie" and r["size_bytes"] == size)
            hu = next(r for r in hot if r["variant"] == "ucie" and r["size_bytes"] == size)
            writer.writerow({
                "size_bytes": size,
                "cold_pcie_cycle": cp["final_cycle"],
                "cold_ucie_cycle": cu["final_cycle"],
                "cold_gain_pct": f"{(cp['final_cycle'] - cu['final_cycle']) / cp['final_cycle'] * 100:.6f}",
                "hot_pcie_cycle": hp["final_cycle"],
                "hot_ucie_cycle": hu["final_cycle"],
                "hot_gain_pct": f"{(hp['final_cycle'] - hu['final_cycle']) / hp['final_cycle'] * 100:.6f}",
            })


def main():
    cold = read_rows(COLD_CSV)
    hot = read_rows(HOT_CSV)
    sizes = sorted({r["size_bytes"] for r in cold} & {r["size_bytes"] for r in hot})
    write_summary(cold, hot, sizes)

    cold_pcie = by_variant(cold, "pcie", "final_cycle", sizes)
    cold_ucie = by_variant(cold, "ucie", "final_cycle", sizes)
    hot_pcie = by_variant(hot, "pcie", "final_cycle", sizes)
    hot_ucie = by_variant(hot, "ucie", "final_cycle", sizes)
    cold_gain = [(p - u) / p * 100 for p, u in zip(cold_pcie, cold_ucie)]
    hot_gain = [(p - u) / p * 100 for p, u in zip(hot_pcie, hot_ucie)]

    fig, (ax_total, ax_gain) = plt.subplots(1, 2, figsize=(13, 4.8))
    fig.patch.set_facecolor(SURFACE)

    style_axis(ax_total)
    ax_total.set_yscale("log")
    ax_total.plot(sizes, cold_pcie, marker="o", color=BLUE, linewidth=2, label="Cold PCIe")
    ax_total.plot(sizes, cold_ucie, marker="o", color=ORANGE, linewidth=2, label="Cold UCIe")
    ax_total.plot(sizes, hot_pcie, marker="s", color=GREEN, linewidth=2, label="Hot PCIe")
    ax_total.plot(sizes, hot_ucie, marker="s", color=RED, linewidth=2, label="Hot UCIe")
    ax_total.set_xticks(sizes)
    ax_total.set_xticklabels([size_label(s) for s in sizes], rotation=45, ha="right", color=INK)
    ax_total.xaxis.set_minor_locator(mticker.NullLocator())
    ax_total.set_ylabel("final cycle", color=MUTED)
    ax_total.set_title("QD1 end-to-end cycles", color=INK)
    legend = ax_total.legend(frameon=False, fontsize=8)
    for text in legend.get_texts():
        text.set_color(INK)

    style_axis(ax_gain)
    ax_gain.plot(sizes, cold_gain, marker="o", color=BLUE, linewidth=2, label="Cold NAND")
    ax_gain.plot(sizes, hot_gain, marker="s", color=GREEN, linewidth=2, label="Cache-hot")
    ax_gain.set_xticks(sizes)
    ax_gain.set_xticklabels([size_label(s) for s in sizes], rotation=45, ha="right", color=INK)
    ax_gain.xaxis.set_minor_locator(mticker.NullLocator())
    ax_gain.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=2))
    ax_gain.set_ylabel("end-to-end gain, (PCIe-UCIe)/PCIe", color=MUTED)
    ax_gain.set_title("UCIe gain", color=INK)
    legend = ax_gain.legend(frameon=False, fontsize=8)
    for text in legend.get_texts():
        text.set_color(INK)

    fig.suptitle("QD1 PCIe vs UCIe: corrected cold NAND versus cache-hot preconditioned reads",
                 color=INK, fontsize=12)
    fig.text(0.5, 0.01,
             "Hot mode uses cache-enabled SimpleSSD after preconditioning write; 32KB+ includes SimpleSSD cache-hit behavior, not an ideal zero-latency source.",
             ha="center", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    fig.savefig(OUT_PATH, dpi=200, facecolor=SURFACE)
    print(f"Wrote {SUMMARY_CSV}")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
