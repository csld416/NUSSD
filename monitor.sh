#!/usr/bin/env bash

if [ -z "${CSV_FILE:-}" ]; then
    if [ -f "results/ufs4_vs_ucie_qd_sweep_128kb.csv" ] || [ -f "results/ufs4_vs_ucie_qd_sweep_128kb.out" ]; then
        CSV_FILE="results/ufs4_vs_ucie_qd_sweep_128kb.csv"
    elif [ -f "results/ufs4_vs_ucie_e2e_qd1.csv" ] || [ -f "results/ufs4_vs_ucie_e2e_qd1.out" ]; then
        CSV_FILE="results/ufs4_vs_ucie_e2e_qd1.csv"
    elif [ -f "results/ucie_qd1_prediction_verification.csv" ]; then
        CSV_FILE="results/ucie_qd1_prediction_verification.csv"
    elif [ -f "results/ucie_targeted_verification.csv" ]; then
        CSV_FILE="results/ucie_targeted_verification.csv"
    else
        CSV_FILE="results/pcie_p_characterization_8ch_onfi52.csv"
    fi
fi
if [ -z "${LOG_FILE:-}" ]; then
    case "$CSV_FILE" in
        *ufs4_vs_ucie_qd_sweep_128kb.csv)
            LOG_FILE="results/ufs4_vs_ucie_qd_sweep_128kb.out"
            ;;
        *ufs4_vs_ucie_e2e_qd1.csv)
            LOG_FILE="results/ufs4_vs_ucie_e2e_qd1.out"
            ;;
        *ucie_qd1_prediction_verification.csv)
            LOG_FILE="results/ucie_qd1_prediction_verification.out"
            ;;
        *ucie_targeted_verification.csv)
            LOG_FILE="results/ucie_targeted_verification.out"
            ;;
        *)
            LOG_FILE="results/pcie_p_characterization_8ch_onfi52.out"
            ;;
    esac
fi
INTERVAL="${INTERVAL:-60}"
MONITOR_TZ="${MONITOR_TZ:-Asia/Taipei}"
if [ -z "${HARNESS_PATTERN:-}" ]; then
    case "$CSV_FILE" in
        *ufs4_vs_ucie_qd_sweep_128kb.csv)
            HARNESS_PATTERN="run_pcie_p_characterization.py.*--variants.*ufs4,ucie.*--sizes.*128KB"
            ;;
        *ufs4_vs_ucie_e2e_qd1.csv)
            HARNESS_PATTERN="run_pcie_p_characterization.py.*--variants.*ufs4,ucie"
            ;;
        *ucie_qd1_prediction_verification.csv)
            HARNESS_PATTERN="run_ucie_targeted_verification.py"
            ;;
        *ucie_targeted_verification.csv)
            HARNESS_PATTERN="run_ucie_targeted_verification.py"
            ;;
        *)
            HARNESS_PATTERN="run_pcie_p_characterization.py"
            ;;
    esac
fi

format_mtime() {
    local path="$1"
    if [ -e "$path" ]; then
        stat -c '%Y' "$path" | xargs -r -I{} env TZ="$MONITOR_TZ" date -d "@{}" '+%Y-%m-%d %H:%M:%S'
    fi
}

while true; do
    LAST_UPDATED="尚無輸出"
    if [ -f "$CSV_FILE" ] || [ -f "$LOG_FILE" ]; then
        LAST_UPDATED=$(
            ls -t "$CSV_FILE" "$LOG_FILE" 2>/dev/null \
                | head -n 1 \
                | while IFS= read -r newest; do format_mtime "$newest"; done
        )
    fi

    clear
    echo "============================================================"
    echo " Simulation monitor - $(TZ="$MONITOR_TZ" date '+%Y-%m-%d %H:%M:%S') UTC+8"
    echo " 最後輸出更新時間 - ${LAST_UPDATED} UTC+8"
    echo " CSV - ${CSV_FILE}"
    echo " LOG - ${LOG_FILE}"
    echo "============================================================"

    LIVE_PID="$(pgrep -f "python3.*${HARNESS_PATTERN}" | head -n 1)"
    RUNNING_ROWS=0
    if [ -f "$CSV_FILE" ]; then
        RUNNING_ROWS="$(awk -F ',' 'NR > 1 && $6 == "RUNNING" { count += 1 } END { print count + 0 }' "$CSV_FILE")"
    fi
    if [ -n "$LIVE_PID" ] && ps -p "$LIVE_PID" >/dev/null 2>&1; then
        echo "行程狀態: [執行中 (RUNNING)] Python PID: ${LIVE_PID}"
        pgrep -af "interchiplet|popnet" | grep -E "ufs4_vs_ucie_e2e_qd1|pcie_p_characterization|ucie_targeted_verification|ucie_qd1_prediction_verification|popnet" | tail -n 4
    elif [ "$RUNNING_ROWS" -gt 0 ]; then
        echo "行程狀態: [執行中 (RUNNING, CSV inferred)]"
    else
        echo "行程狀態: [未執行 / 已結束 (NOT RUNNING / FINISHED)]"
    fi
    echo "------------------------------------------------------------"

    echo "[整體進度]"
    if [ -f "$CSV_FILE" ]; then
        awk -F ',' '
            NR > 1 {
                total += 1
                count[$6] += 1
            }
            END {
                printf "total=%d OK=%d RUNNING=%d PENDING=%d FAIL=%d STOPPED=%d\n",
                    total, count["OK"], count["RUNNING"], count["PENDING"], count["FAIL"], count["STOPPED"]
            }
        ' "$CSV_FILE"
    else
        echo "CSV 尚未產生..."
    fi
    echo "------------------------------------------------------------"

    echo "[目前執行中]"
    if [ -f "$CSV_FILE" ]; then
        awk -F ',' '
            NR > 1 && $6 == "RUNNING" {
                printf "%s %s size=%sB qd=%s started=%s run_dir=%s\n", $1, $2, $3, $4, $7, $22
            }
        ' "$CSV_FILE"
    else
        echo "CSV 尚未產生..."
    fi
    echo "------------------------------------------------------------"

    echo "[已完成案例與 UTC+8 完成時間]"
    if [ -f "$CSV_FILE" ]; then
        awk -F ',' '
            NR > 1 && $6 == "OK" {
                if (NF >= 28 && $26 != "") {
                    printf "%s %s size=%sB qd=%s | cycles=%s | p_wall=%s | pred_speedup=%s | meas_speedup=%s | err=%s | done_time=%s UTC+8\n",
                        $1, $2, $3, $4, $9, $14, $26, $27, $28, $8
                }
                else {
                    printf "%s %s size=%sB qd=%s | cycles=%s | throughput=%.3f GB/s | link_occupied=%s | p_wall=%s | link_sum/request=%s | done_time=%s UTC+8\n",
                        $1, $2, $3, $4, $9, $16 * 1000, $11, $14, $15, $8
                }
            }
        ' "$CSV_FILE" | tail -n 20
    else
        echo "CSV 尚未產生..."
    fi
    echo "------------------------------------------------------------"

    echo "[尚未完成案例]"
    if [ -f "$CSV_FILE" ]; then
        awk -F ',' '
            NR > 1 && $6 != "OK" {
                printf "%s %s size=%sB qd=%s status=%s started=%s done=%s error=%s\n",
                    $1, $2, $3, $4, $6, $7, $8, $21
            }
        ' "$CSV_FILE" | head -n 40
    else
        echo "CSV 尚未產生..."
    fi
    echo "------------------------------------------------------------"

    echo "[Log 最新內容]"
    if [ -f "$LOG_FILE" ]; then
        tail -n 12 "$LOG_FILE"
    else
        echo "Log 尚未產生..."
    fi
    echo "============================================================"
    echo "每 ${INTERVAL} 秒更新一次 (按 Ctrl+C 退出)..."

    sleep "$INTERVAL"
done
