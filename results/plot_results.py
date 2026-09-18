#!/usr/bin/env python3
"""Plot PCIe vs UCIe throughput comparison from pcie_vs_ucie_throughput.csv.

Run with:
    .venv/bin/python3 results/plot_results.py

Sweep covers 4KB-4MB (11 sizes). 8MB remains deliberately excluded from this
plot; the corrected 4KB-4MB rerun is complete and each reported run validated
that PopNet finished both expected transactions.

Produces results/pcie_vs_ucie_comparison.png with three panels, all sharing
a log-scale x-axis (request size):
  1. interconnect-only delay (PCIe vs UCIe) -- log y
  2. total end-to-end simulated cycles (PCIe vs UCIe) -- log y
  3. end-to-end gain % ((pcie-ucie)/pcie) -- linear y
Panels 1+2 together are the point: the interconnect delay gap is real and
consistent, but it barely moves the end-to-end total because flash service
time dominates. Panel 3 makes the (small, size-dependent) net effect explicit.
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

CSV_PATH = Path(__file__).parent / "pcie_vs_ucie_throughput.csv"
OUT_PATH = Path(__file__).parent / "pcie_vs_ucie_comparison.png"

COLOR_PCIE = "#2a78d6"   # categorical slot 1 (blue)
COLOR_UCIE = "#eb6834"   # categorical slot 2 (orange)
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"


def load_rows():
    rows = []
    with open(CSV_PATH) as f:
        for row in csv.DictReader(f):
            if row["final_cycle"] in ("TIMEOUT", "RUN_FAILED", "SED_FAILED", "NA"):
                continue
            rows.append({
                "variant": row["variant"],
                "size_bytes": int(row["size_bytes"]),
                "final_cycle": int(row["final_cycle"]),
                "avg_delay": float(row["avg_interconnect_delay"]),
            })
    return rows


def size_label(n):
    if n >= 1024 * 1024:
        return f"{n // (1024 * 1024)}MB"
    return f"{n // 1024}KB"


def style_axis(ax):
    ax.set_facecolor(SURFACE)
    ax.set_xscale("log", basex=2)
    ax.grid(axis="y", color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED)


def main():
    rows = load_rows()
    sizes = sorted(set(r["size_bytes"] for r in rows))
    pcie_delay = [next(r["avg_delay"] for r in rows if r["variant"] == "pcie" and r["size_bytes"] == s) for s in sizes]
    ucie_delay = [next(r["avg_delay"] for r in rows if r["variant"] == "ucie" and r["size_bytes"] == s) for s in sizes]
    pcie_total = [next(r["final_cycle"] for r in rows if r["variant"] == "pcie" and r["size_bytes"] == s) for s in sizes]
    ucie_total = [next(r["final_cycle"] for r in rows if r["variant"] == "ucie" and r["size_bytes"] == s) for s in sizes]
    gain_pct = [(p - u) / p * 100 for p, u in zip(pcie_total, ucie_total)]

    fig, (ax_delay, ax_total, ax_gain) = plt.subplots(1, 3, figsize=(15, 4.5))
    fig.patch.set_facecolor(SURFACE)

    for ax, pcie_vals, ucie_vals, title, ylabel, log, ucie_style in (
        (ax_delay, pcie_delay, ucie_delay, "Interconnect delay only", "cycles", True, "-"),
        (ax_total, pcie_total, ucie_total, "Total end-to-end simulated time\n(lines nearly overlap -- that's the point)", "cycles", True, "--"),
    ):
        style_axis(ax)
        if log:
            ax.set_yscale("log")
        ax.plot(sizes, pcie_vals, marker="o", markersize=5, linewidth=2, color=COLOR_PCIE, label="PCIe")
        ax.plot(sizes, ucie_vals, ucie_style, marker="o", markersize=4, linewidth=2, color=COLOR_UCIE, label="UCIe")
        ax.set_xticks(sizes)
        ax.set_xticklabels([size_label(s) for s in sizes], color=INK, rotation=45, ha="right", fontsize=8)
        ax.xaxis.set_minor_locator(mticker.NullLocator())
        ax.set_ylabel(ylabel, color=MUTED)
        ax.set_title(title, color=INK, fontsize=10, pad=10)
        legend = ax.legend(frameon=False, fontsize=8)
        for text in legend.get_texts():
            text.set_color(INK)

    style_axis(ax_gain)
    ax_gain.plot(sizes, gain_pct, marker="o", markersize=5, linewidth=2, color=COLOR_PCIE)
    ax_gain.set_xticks(sizes)
    ax_gain.set_xticklabels([size_label(s) for s in sizes], color=INK, rotation=45, ha="right", fontsize=8)
    ax_gain.xaxis.set_minor_locator(mticker.NullLocator())
    ax_gain.set_ylabel("end-to-end gain, (PCIe−UCIe)/PCIe", color=MUTED)
    ax_gain.set_title("Net gain from swapping PCIe→UCIe", color=INK, fontsize=11, pad=10)
    ax_gain.yaxis.set_major_formatter(mticker.PercentFormatter(decimals=2))
    for xi, yi in zip(sizes, gain_pct):
        ax_gain.annotate(f"{yi:.3f}%", (xi, yi), textcoords="offset points",
                          xytext=(0, 6), ha="center", fontsize=7, color=INK)

    fig.suptitle("PCIe vs UCIe across 4KB–4MB — interconnect gap is real, "
                 "end-to-end gain stays small but grows with size",
                 fontsize=12, color=INK)
    fig.text(0.5, 0.01,
              "Corrected QD1 read workload: preconditioned offsets, no ICL read cache/prefetch, "
              "and PopNet transaction-count validation for every point.",
              ha="center", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    fig.savefig(OUT_PATH, dpi=200, facecolor=SURFACE)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
