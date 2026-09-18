#!/usr/bin/env python3
"""Clearer cold-vs-hot QD1 visualization.

This avoids putting all four total-cycle lines into one crowded axis. The hot
cache-hit path has a large discontinuity at 32KB, so the panels keep totals
separate from PCIe-to-UCIe savings.
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


BASE = Path(__file__).parent
SUMMARY_CSV = BASE / "pcie_vs_ucie_hot_vs_cold_qd1_summary.csv"
OUT_PATH = BASE / "pcie_vs_ucie_hot_vs_cold_qd1_clear.png"

INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
PCIE = "#2a78d6"
UCIE = "#eb6834"
COLD = "#4c78a8"
HOT = "#2ca25f"


def size_label(size):
    if size >= 1024 * 1024:
        return f"{size // (1024 * 1024)}MB"
    return f"{size // 1024}KB"


def read_summary():
    with SUMMARY_CSV.open(newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key in row:
            row[key] = float(row[key]) if key.endswith("_pct") else int(row[key])
    return rows


def style_axis(ax, sizes):
    ax.set_facecolor(SURFACE)
    ax.set_xscale("log", basex=2)
    ax.set_xticks(sizes)
    ax.set_xticklabels([size_label(s) for s in sizes], rotation=45, ha="right", color=INK)
    ax.xaxis.set_minor_locator(mticker.NullLocator())
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(colors=MUTED)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)


def color_legend(ax):
    legend = ax.legend(frameon=False, fontsize=8)
    for text in legend.get_texts():
        text.set_color(INK)


def main():
    rows = read_summary()
    sizes = [r["size_bytes"] for r in rows]

    cold_pcie = [r["cold_pcie_cycle"] for r in rows]
    cold_ucie = [r["cold_ucie_cycle"] for r in rows]
    hot_pcie = [r["hot_pcie_cycle"] for r in rows]
    hot_ucie = [r["hot_ucie_cycle"] for r in rows]
    cold_delta = [p - u for p, u in zip(cold_pcie, cold_ucie)]
    hot_delta = [p - u for p, u in zip(hot_pcie, hot_ucie)]
    cold_gain = [r["cold_gain_pct"] for r in rows]
    hot_gain = [r["hot_gain_pct"] for r in rows]

    fig, axes = plt.subplots(2, 2, figsize=(13.5, 8.0))
    fig.patch.set_facecolor(SURFACE)
    ax_cold, ax_hot, ax_delta, ax_gain = axes.ravel()

    style_axis(ax_cold, sizes)
    ax_cold.set_yscale("log")
    ax_cold.plot(sizes, cold_pcie, marker="o", linewidth=2, color=PCIE, label="PCIe")
    ax_cold.plot(sizes, cold_ucie, marker="o", linewidth=2, color=UCIE, label="UCIe")
    ax_cold.set_title("Cold NAND: total cycles", color=INK)
    ax_cold.set_ylabel("final cycle", color=MUTED)
    color_legend(ax_cold)

    style_axis(ax_hot, sizes)
    ax_hot.set_yscale("log")
    ax_hot.plot(sizes, hot_pcie, marker="s", linewidth=2, color=PCIE, label="PCIe")
    ax_hot.plot(sizes, hot_ucie, marker="s", linewidth=2, color=UCIE, label="UCIe")
    ax_hot.axvline(32768, color=MUTED, linewidth=1, linestyle="--")
    ax_hot.text(32768, max(hot_pcie) * 0.7, "32KB cache-hit jump",
                rotation=90, va="top", ha="right", fontsize=8, color=MUTED)
    ax_hot.set_title("Cache-hot: total cycles", color=INK)
    ax_hot.set_ylabel("final cycle", color=MUTED)
    color_legend(ax_hot)

    style_axis(ax_delta, sizes)
    ax_delta.plot(sizes, cold_delta, marker="o", linewidth=2, color=COLD, label="Cold NAND")
    ax_delta.plot(sizes, hot_delta, marker="s", linewidth=2, color=HOT, label="Cache-hot")
    ax_delta.set_title("Absolute cycle saving from UCIe", color=INK)
    ax_delta.set_ylabel("PCIe cycle - UCIe cycle", color=MUTED)
    color_legend(ax_delta)

    style_axis(ax_gain, sizes)
    ax_gain.plot(sizes, cold_gain, marker="o", linewidth=2, color=COLD, label="Cold NAND")
    ax_gain.plot(sizes, hot_gain, marker="s", linewidth=2, color=HOT, label="Cache-hot")
    ax_gain.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=2))
    ax_gain.set_title("Percent end-to-end gain", color=INK)
    ax_gain.set_ylabel("(PCIe - UCIe) / PCIe", color=MUTED)
    color_legend(ax_gain)

    fig.suptitle("QD1 PCIe vs UCIe: cold NAND and SimpleSSD cache-hot read paths",
                 color=INK, fontsize=13)
    fig.text(
        0.5,
        0.012,
        "Cache-hot means SimpleSSD ICL cache-hit after preconditioning write; it is not an ideal staged-data source.",
        ha="center",
        fontsize=8,
        color=MUTED,
    )
    fig.tight_layout(rect=(0, 0.035, 1, 0.94))
    fig.savefig(OUT_PATH, dpi=200, facecolor=SURFACE)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
