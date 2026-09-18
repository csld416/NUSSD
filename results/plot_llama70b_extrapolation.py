#!/usr/bin/env python3
"""Plot Llama-3-70B layer extrapolation summary."""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


BASE = Path(__file__).parent
CSV_PATH = BASE / "llama70b_layer_existing_extrapolation.csv"
OUT_PATH = BASE / "llama70b_layer_existing_extrapolation.png"

SURFACE = "#fcfcfb"
INK = "#101010"
MUTED = "#77736c"
GRID = "#dedbd2"
PCIE = "#2a78d6"
UCIE = "#eb6834"


def label(row):
    w = "W1 mono" if row["workload"].startswith("w1") else "W2 seq"
    m = "cold" if row["memory_mode"] == "cold" else "hot"
    return f"{w}\n{m}"


def main():
    with CSV_PATH.open(newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["estimated_total_cycle"] = float(row["estimated_total_cycle"])
        row["interconnect_fraction_est"] = float(row["interconnect_fraction_est"])
        row["speedup_vs_pcie"] = float(row["speedup_vs_pcie"])

    pairs = []
    for workload in ("w1_monolithic_qd1", "w2_matrix_seq_qd1"):
        for memory_mode in ("cold", "hot"):
            pcie = next(r for r in rows if r["workload"] == workload and r["memory_mode"] == memory_mode and r["variant"] == "pcie")
            ucie = next(r for r in rows if r["workload"] == workload and r["memory_mode"] == memory_mode and r["variant"] == "ucie")
            pairs.append((pcie, ucie))

    x = list(range(len(pairs)))
    labels = [label(pcie) for pcie, _ in pairs]
    pcie_inter = [pcie["interconnect_fraction_est"] * 100 for pcie, _ in pairs]
    ucie_inter = [ucie["interconnect_fraction_est"] * 100 for _, ucie in pairs]
    speedup = [ucie["speedup_vs_pcie"] for _, ucie in pairs]

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    fig.patch.set_facecolor(SURFACE)

    ax = axes[0]
    ax.set_facecolor(SURFACE)
    width = 0.36
    ax.bar([i - width / 2 for i in x], pcie_inter, width=width, color=PCIE, label="PCIe")
    ax.bar([i + width / 2 for i in x], ucie_inter, width=width, color=UCIE, label="UCIe")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, color=INK)
    ax.set_ylabel("interconnect / total (%)", color=MUTED)
    ax.set_title("Estimated Link Fraction", color=INK)
    ax.grid(axis="y", color=GRID)
    ax.legend(frameon=False)

    ax = axes[1]
    ax.set_facecolor(SURFACE)
    ax.bar(x, speedup, color=UCIE, width=0.5)
    ax.axhline(1.0, color=MUTED, linewidth=1)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, color=INK)
    ax.set_ylabel("UCIe / PCIe speedup", color=MUTED)
    ax.set_title("Estimated End-to-End Speedup", color=INK)
    ax.grid(axis="y", color=GRID)
    ax.set_ylim(1.0, max(speedup) * 1.0004)
    for i, value in enumerate(speedup):
        ax.text(i, value, f"{value:.6f}x", ha="center", va="bottom", fontsize=8, color=INK)

    for ax in axes:
        ax.tick_params(colors=MUTED)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.spines["left"].set_color(MUTED)
        ax.spines["bottom"].set_color(MUTED)

    fig.suptitle("Llama 3 70B Layer Streaming: Extrapolated From Validated QD1 Sweeps", color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(OUT_PATH, dpi=200, facecolor=SURFACE)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
