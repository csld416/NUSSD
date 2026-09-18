#!/usr/bin/env python3
"""Plot completed UFS4/UCIe pairs from the 128 KB cold-read QD sweep."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "results/ufs4_vs_ucie_qd_sweep_128kb.csv"
OUTPUT = ROOT / "results/ufs4_vs_ucie_qd_sweep_128kb.png"
EXPECTED_QDS = [1, 2, 4, 8, 16, 32, 64, 128]


def load_complete_pairs():
    by_qd = {}
    with INPUT.open(newline="") as source:
        for row in csv.DictReader(source):
            if row["status"] != "OK" or int(row["size_bytes"]) != 128 * 1024:
                continue
            by_qd.setdefault(int(row["queue_depth"]), {})[row["variant"]] = row

    complete = {
        qd: variants
        for qd, variants in by_qd.items()
        if set(variants) >= {"ufs4", "ucie"}
    }
    if not complete:
        raise RuntimeError("no complete UFS4/UCIe QD pairs found")
    return complete


def main():
    pairs = load_complete_pairs()
    qds = sorted(pairs)
    missing = [qd for qd in EXPECTED_QDS if qd not in pairs]

    # The harness records bytes/ps. One byte/ps equals 1000 GB/s.
    ufs_tput = [
        float(pairs[qd]["ufs4"]["throughput_bytes_per_cycle"]) * 1000
        for qd in qds
    ]
    ucie_tput = [
        float(pairs[qd]["ucie"]["throughput_bytes_per_cycle"]) * 1000
        for qd in qds
    ]
    speedup = [ucie / ufs for ufs, ucie in zip(ufs_tput, ucie_tput)]

    colors = {"ufs": "#1F77B4", "ucie": "#2E8B57", "speedup": "#C23B33"}
    fig, (ax_tput, ax_speedup) = plt.subplots(
        1, 2, figsize=(11.5, 4.8), constrained_layout=True
    )

    for ax in (ax_tput, ax_speedup):
        ax.set_xscale("log", basex=2)
        ax.set_xticks(EXPECTED_QDS)
        ax.set_xticklabels([str(qd) for qd in EXPECTED_QDS])
        ax.set_xlabel("Queue depth")
        ax.grid(True, linewidth=0.6, alpha=0.3)

    ax_tput.plot(
        qds, ufs_tput, marker="o", linewidth=2.3,
        color=colors["ufs"], label="UFS4 measured",
    )
    ax_tput.plot(
        qds, ucie_tput, marker="s", linewidth=2.3,
        color=colors["ucie"], label="UCIe measured",
    )
    ax_tput.set_ylabel("Aggregate throughput (GB/s)")
    ax_tput.set_title("Throughput saturation")
    ax_tput.legend(frameon=False)

    for qd, ufs, ucie in zip(qds, ufs_tput, ucie_tput):
        ax_tput.annotate(
            f"{ufs:.2f}", (qd, ufs), xytext=(0, -13),
            textcoords="offset points", ha="center", fontsize=8,
            color=colors["ufs"],
        )
        ax_tput.annotate(
            f"{ucie:.2f}", (qd, ucie), xytext=(0, 7),
            textcoords="offset points", ha="center", fontsize=8,
            color=colors["ucie"],
        )

    ax_speedup.plot(
        qds, speedup, marker="D", linewidth=2.3, color=colors["speedup"]
    )
    ax_speedup.axhline(1.0, color="#555555", linewidth=1, linestyle="--")
    ax_speedup.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2fx"))
    ax_speedup.set_ylabel("Throughput speedup (UCIe / UFS4)")
    ax_speedup.set_title("Benefit from replacing UFS4")
    for qd, value in zip(qds, speedup):
        ax_speedup.annotate(
            f"{value:.3f}x", (qd, value), xytext=(0, 7),
            textcoords="offset points", ha="center", fontsize=8,
            color=colors["speedup"],
        )

    suffix = ""
    if missing:
        suffix = f" (completed pairs only; missing QD {', '.join(map(str, missing))})"
    fig.suptitle(f"128 KB QD1-128 cold-read sweep{suffix}", fontsize=12)
    fig.savefig(OUTPUT, dpi=180)
    print(OUTPUT)
    if missing:
        print(f"warning: missing complete pairs for QD {missing}")


if __name__ == "__main__":
    main()
