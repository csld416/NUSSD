#!/usr/bin/env python3
"""Plot the verified QD1 cold-read UFS4 versus UCIe sweep."""

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "results/ufs4_vs_ucie_e2e_qd1.csv"
OUTPUT = ROOT / "results/ufs4_vs_ucie_e2e_qd1.png"
SIZE_LABELS = {
    4096: "4KB",
    16384: "16KB",
    65536: "64KB",
    262144: "256KB",
    1048576: "1MB",
    4194304: "4MB",
}


def load_rows():
    by_size = {}
    with INPUT.open(newline="") as source:
        for row in csv.DictReader(source):
            if row["memory_mode"] != "cold" or int(row["queue_depth"]) != 1:
                continue
            if row["status"] != "OK":
                continue
            by_size.setdefault(int(row["size_bytes"]), {})[row["variant"]] = row

    missing = [size for size in SIZE_LABELS if set(by_size.get(size, {})) != {"ufs4", "ucie"}]
    if missing:
        raise RuntimeError(f"missing complete UFS4/UCIe pairs for sizes: {missing}")
    return by_size


def annotate(ax, xs, ys, color, suffix, offsets):
    for x, y, offset in zip(xs, ys, offsets):
        ax.annotate(
            f"{y:.2f}{suffix}",
            (x, y),
            xytext=(0, offset),
            textcoords="offset points",
            ha="center",
            va="bottom" if offset >= 0 else "top",
            fontsize=8,
            color=color,
        )


def main():
    by_size = load_rows()
    sizes = sorted(SIZE_LABELS)
    x = list(range(len(sizes)))

    ufs_total = [float(by_size[size]["ufs4"]["final_cycle"]) / 1e6 for size in sizes]
    ucie_total = [float(by_size[size]["ucie"]["final_cycle"]) / 1e6 for size in sizes]
    ssd_service = [
        (
            float(by_size[size]["ufs4"]["t_nonlink_wall_cycle"])
            + float(by_size[size]["ucie"]["t_nonlink_wall_cycle"])
        )
        / 2e6
        for size in sizes
    ]
    speedup = [ufs / ucie for ufs, ucie in zip(ufs_total, ucie_total)]

    # S is in bytes and all theoretical latency terms below are in us.
    ssd_theory = [3.13 + 6.993 * size / 32768 for size in sizes]
    ucie_theory = [
        ssd + (64 + size) / 64000
        for size, ssd in zip(sizes, ssd_theory)
    ]
    ufs_theory = [
        ssd + (64 + size) / (0.091 * 64000)
        for size, ssd in zip(sizes, ssd_theory)
    ]
    speedup_theory = [ufs / ucie for ufs, ucie in zip(ufs_theory, ucie_theory)]

    colors = {
        "ufs": "#1F77B4",
        "ucie": "#2E8B57",
        "ssd": "#E67E22",
        "speedup": "#C23B33",
    }
    fig, ax_latency = plt.subplots(figsize=(10.8, 5.8), constrained_layout=True)
    ax_speedup = ax_latency.twinx()

    ax_latency.plot(
        x, ufs_total, marker="o", linewidth=2.3, color=colors["ufs"],
        label="UFS4 measured total",
    )
    ax_latency.plot(
        x, ufs_theory, marker="o", markerfacecolor="white", linewidth=2.0,
        linestyle=":", color=colors["ufs"], label="UFS4 theoretical total",
    )
    ax_latency.plot(
        x, ucie_total, marker="s", linewidth=2.3, color=colors["ucie"],
        label="UCIe measured total",
    )
    ax_latency.plot(
        x, ucie_theory, marker="s", markerfacecolor="white", linewidth=2.0,
        linestyle=":", color=colors["ucie"], label="UCIe theoretical total",
    )
    ax_latency.plot(
        x, ssd_service, marker="^", linewidth=2.3, color=colors["ssd"],
        label="SSD measured response time",
    )
    ax_latency.plot(
        x, ssd_theory, marker="^", markerfacecolor="white", linewidth=2.0,
        linestyle=":", color=colors["ssd"],
        label="SSD theoretical response time",
    )
    ax_latency.set_yscale("log")
    ax_latency.set_xticks(x)
    ax_latency.set_xticklabels([SIZE_LABELS[size] for size in sizes])
    ax_latency.set_xlabel("Read request size")
    ax_latency.set_ylabel("Latency (us, log scale)")
    ax_latency.set_title("QD1 cold-read latency and UFS4-to-UCIe speedup")
    ax_latency.grid(True, which="both", linewidth=0.6, alpha=0.3)

    ax_speedup.plot(
        x, speedup, marker="D", linewidth=2.4,
        color=colors["speedup"], label="Measured speedup",
    )
    ax_speedup.plot(
        x, speedup_theory, marker="D", markerfacecolor="white", linewidth=2.2,
        linestyle=":", color=colors["speedup"], label="Theoretical speedup",
    )
    ax_speedup.axhline(1.0, color="#555555", linewidth=1, linestyle="--")
    ax_speedup.set_ylim(0.95, max(speedup + speedup_theory) * 1.14)
    ax_speedup.set_ylabel("Speedup (UFS4 time / UCIe time)")
    measured_offsets = [-12 if measured < theoretical else 9
                        for measured, theoretical in zip(speedup, speedup_theory)]
    theoretical_offsets = [9 if theoretical > measured else -12
                           for measured, theoretical in zip(speedup, speedup_theory)]
    annotate(ax_speedup, x, speedup, colors["speedup"], "x", measured_offsets)
    annotate(
        ax_speedup, x, speedup_theory, colors["speedup"], "x",
        theoretical_offsets,
    )

    latency_handles, latency_labels = ax_latency.get_legend_handles_labels()
    speedup_handles, speedup_labels = ax_speedup.get_legend_handles_labels()
    ax_latency.legend(
        latency_handles + speedup_handles,
        latency_labels + speedup_labels,
        frameon=False,
        loc="upper left",
    )

    fig.savefig(OUTPUT, dpi=180)
    print(OUTPUT)


if __name__ == "__main__":
    main()
