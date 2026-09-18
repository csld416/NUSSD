#!/usr/bin/env python3
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "pcie_qd1_cold_slc_cmd64_20260827"
IN_CSV = ROOT / "results" / "pcie_qd1_cold_slc_cmd64_20260827.csv"
OUT_CSV = ROOT / "results" / "pcie_qd1_cold_slc_cmd64_20260827_per_leg.csv"

POPNET_TO_PS = 1000.0


def parse_bench(path):
    rows = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 6:
            rows.append({
                "cycle": int(parts[0]),
                "src_x": int(parts[1]),
                "src_y": None,
                "dst_x": int(parts[2]),
                "dst_y": int(parts[3]),
                "packet_size_flits": int(parts[4]),
                "desc": int(parts[5]),
            })
        elif len(parts) >= 7:
            rows.append({
                "cycle": int(parts[0]),
                "src_x": int(parts[1]),
                "src_y": int(parts[2]),
                "dst_x": int(parts[3]),
                "dst_y": int(parts[4]),
                "packet_size_flits": int(parts[5]),
                "desc": int(parts[6]),
            })
    return rows


def parse_delay(path):
    rows = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) < 7:
            continue
        rows.append({
            "cycle": int(float(parts[0])),
            "src_x": int(parts[1]),
            "src_y": int(parts[2]),
            "dst_x": int(parts[3]),
            "dst_y": int(parts[4]),
            "packet_size_flits": int(parts[5]),
            "delay_ps": float(parts[6]) * POPNET_TO_PS,
        })
    return rows


def main():
    rows = []
    with IN_CSV.open(newline="") as f:
        for row in csv.DictReader(f):
            if row["status"] != "OK":
                continue
            size = int(row["size_bytes"])
            run_dir = Path(row["run_dir"])
            bench = parse_bench(run_dir / "bench.txt")
            delays = parse_delay(run_dir / "delayInfo.txt")
            if len(bench) != 2 or len(delays) != 2:
                raise RuntimeError(f"{run_dir} expected 2 bench/delay rows")

            request_delay = delays[0]["delay_ps"]
            response_delay = delays[1]["delay_ps"]
            total_link = request_delay + response_delay
            final_cycle = float(row["final_cycle"])
            ssd_cycle = final_cycle - total_link

            rows.append({
                "size_bytes": size,
                "request_flits": bench[0]["packet_size_flits"],
                "request_link_ps": request_delay,
                "response_flits": bench[1]["packet_size_flits"],
                "response_link_ps": response_delay,
                "total_link_ps": total_link,
                "final_cycle_ps": final_cycle,
                "ssd_cycle_ps": ssd_cycle,
                "p_measured": total_link / final_cycle,
                "run_dir": str(run_dir),
            })

    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    for row in rows:
        print(
            f"{row['size_bytes']},"
            f"req_flits={row['request_flits']},req_us={row['request_link_ps']/1e6:.6f},"
            f"resp_flits={row['response_flits']},resp_us={row['response_link_ps']/1e6:.6f},"
            f"ssd_us={row['ssd_cycle_ps']/1e6:.6f},"
            f"total_us={row['final_cycle_ps']/1e6:.6f},"
            f"p={row['p_measured']:.12g}"
        )


if __name__ == "__main__":
    main()
