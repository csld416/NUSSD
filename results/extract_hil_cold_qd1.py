#!/usr/bin/env python3
import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "hil_cold_qd1_instrumentation"
CURRENT_CSV = ROOT / "results" / "hil_cold_qd1_instrumentation.csv"
BASELINE_CSV = ROOT / "results" / "pcie_p_characterization_8ch_onfi52.csv"
OUT_CSV = ROOT / "results" / "hil_cold_qd1_summary.csv"

SIZES = [4096, 16384, 65536, 262144, 1048576, 4194304]

MEASURE_RE = re.compile(
    r"MEASURE_READ \| REQ\s+(?P<req>\d+) \| BYTE (?P<byte>\d+) "
    r"\| HIL_SUBMIT (?P<hil_submit>\d+) \| HIL_BEGIN (?P<hil_begin>\d+) "
    r"\| HIL_CPU (?P<hil_cpu>\d+) \| ICL_BEGIN (?P<icl_begin>\d+) "
    r"\| ICL_END (?P<icl_end>\d+) \| ICL_ELAPSED (?P<icl_elapsed>\d+) "
    r"\| HIL_END (?P<hil_end>\d+) \| HIL_BODY_EXCLUSIVE (?P<hil_body_exclusive>\d+) "
    r"\| HIL_EXCLUSIVE (?P<hil_exclusive>\d+)"
)


def load_timing(path):
    out = {}
    if not path.exists():
        return out

    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            if (
                row.get("memory_mode") == "cold"
                and row.get("variant") == "pcie"
                and int(row.get("queue_depth", "0") or 0) == 1
                and row.get("status") == "OK"
            ):
                size = int(row["size_bytes"])
                final = float(row["final_cycle"])
                link = float(row["t_link_occupied_cycle"])
                out[size] = {
                    "final_cycle": final,
                    "t_link_occupied_cycle": link,
                    "t_ssd_cold_cycle": final - link,
                }
    return out


def latest_measure(size):
    run_dir = RUN_ROOT / f"cold_pcie_{size}_qd1"
    logs = sorted(run_dir.glob("proc_r*_p1_t1/simplessd.log"))
    if not logs:
        raise FileNotFoundError(f"missing simplessd.log for {size}")

    for log in reversed(logs):
        matches = [MEASURE_RE.search(line) for line in log.read_text(errors="replace").splitlines()]
        matches = [match for match in matches if match]
        if matches:
            values = matches[-1].groupdict()
            return {key: int(value) for key, value in values.items()}, log

    raise RuntimeError(f"missing MEASURE_READ for {size}")


def main():
    timing = load_timing(BASELINE_CSV)
    timing.update(load_timing(CURRENT_CSV))

    rows = []
    for size in SIZES:
        measure, log = latest_measure(size)
        t_ssd = timing[size]["t_ssd_cold_cycle"]
        rows.append({
            "size_bytes": size,
            "t_hil_start_cycle": measure["hil_submit"],
            "t_hil_end_cycle": measure["hil_begin"],
            "t_hil_cycle": measure["hil_cpu"],
            "t_hil_exclusive_cycle": measure["hil_exclusive"],
            "hil_body_exclusive_cycle": measure["hil_body_exclusive"],
            "icl_elapsed_cycle": measure["icl_elapsed"],
            "hil_inclusive_body_cycle": measure["hil_end"] - measure["hil_begin"],
            "t_ssd_cold_cycle": t_ssd,
            "t_hil_over_t_ssd_cold": measure["hil_cpu"] / t_ssd,
            "final_cycle": timing[size]["final_cycle"],
            "t_link_occupied_cycle": timing[size]["t_link_occupied_cycle"],
            "source_log": str(log),
        })

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    for row in rows:
        print(
            f"{row['size_bytes']},{row['t_hil_cycle']},"
            f"{row['t_ssd_cold_cycle']:.0f},{row['t_hil_over_t_ssd_cold']:.12g}"
        )


if __name__ == "__main__":
    main()
