#!/usr/bin/env python3
"""Plot PCIe/UCIe throughput versus QD for the 1MB request-size sweep."""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


BASE = Path(__file__).parent
CSV_PATH = BASE / "pcie_vs_ucie_size_qd.csv"
OUT_PATH = BASE / "pcie_vs_ucie_1mb_qd_line.png"
SIZE = 1024 * 1024

COLOR_PCIE = "#2a78d6"
COLOR_UCIE = "#eb6834"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
MUTED = "#898781"
GRID = "#e1e0d9"


def load_rows():
    with CSV_PATH.open(newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["status"] == "OK"]
    return [r for r in rows if int(r["size_bytes"]) == SIZE]


def main():
    rows = load_rows()
    qds = sorted({int(r["queue_depth"]) for r in rows})
    pcie = [
        float(next(r for r in rows if r["variant"] == "pcie" and int(r["queue_depth"]) == qd)["throughput_bytes_per_cycle"])
        for qd in qds
    ]
    ucie = [
        float(next(r for r in rows if r["variant"] == "ucie" and int(r["queue_depth"]) == qd)["throughput_bytes_per_cycle"])
        for qd in qds
    ]
    speedup = [u / p for p, u in zip(pcie, ucie)]

    fig, (ax_tput, ax_speed) = plt.subplots(1, 2, figsize=(12, 4.6))
    fig.patch.set_facecolor(SURFACE)

    for ax in (ax_tput, ax_speed):
        ax.set_facecolor(SURFACE)
        ax.set_xscale("log", basex=2)
        ax.set_xticks(qds)
        ax.set_xticklabels([str(qd) for qd in qds], color=INK)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.tick_params(colors=MUTED)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.spines["left"].set_color(MUTED)
        ax.spines["bottom"].set_color(MUTED)
        ax.set_xlabel("queue depth", color=MUTED)

    ax_tput.plot(qds, pcie, marker="o", linewidth=2, color=COLOR_PCIE, label="PCIe")
    ax_tput.plot(qds, ucie, marker="o", linewidth=2, color=COLOR_UCIE, label="UCIe")
    ax_tput.set_ylabel("throughput, bytes/cycle", color=MUTED)
    ax_tput.set_title("1MB request throughput vs QD", color=INK)
    legend = ax_tput.legend(frameon=False, fontsize=8)
    for text in legend.get_texts():
        text.set_color(INK)

    ax_speed.plot(qds, speedup, marker="o", linewidth=2, color=COLOR_PCIE)
    ax_speed.axhline(1.0, color=MUTED, linewidth=1, linestyle="--")
    ax_speed.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.4fx"))
    ax_speed.set_ylabel("UCIe / PCIe throughput", color=MUTED)
    ax_speed.set_title("Speedup from swapping PCIe to UCIe", color=INK)
    for qd, value in zip(qds, speedup):
        ax_speed.annotate(f"{value:.4f}x", (qd, value), textcoords="offset points",
                          xytext=(0, 6), ha="center", fontsize=7, color=INK)

    fig.suptitle("1MB corrected read workload: QD sweep", color=INK, fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(OUT_PATH, dpi=200, facecolor=SURFACE)
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
