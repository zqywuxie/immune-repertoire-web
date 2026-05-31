#!/bin/bash

set -u
set -o pipefail
shopt -s nullglob

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# variables

MERGED_DIRS=(
    "${SCRIPT_DIR}/../2.pandaseq"
)        # pandaseq output directory
OUTPUT_DIR="${SCRIPT_DIR}/3.igblastn_out"             # igblastn output directory
DB_DIR="/workspace/igblast/igblast"                                     # igblast database directory
SPECIES="human"                                                         # "human" "mouse" "rhesus_monkey" "rat"
db_cell_type="TCR"                                                      # "BCR" "TCR" "BOTH" "BCR,TCR"
index=""
ig_cell_type=""
E_threshold='0.0001'                                                    # Default = `20'
NUM_THREADS='256'
MEMORY_LIMIT_GB='50'                                                     # 0 means disabled
MONITOR_INTERVAL_SEC='5'                                                # 0 means disabled
MONITOR_DIR=""
SUMMARY_FILE=""

echo "MERGED_DIRS paths: ${MERGED_DIRS[@]}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --data-dir)
            IFS=',' read -ra _paths <<< "$2"
            MERGED_DIRS+=("${_paths[@]}")
            shift 2
            ;;
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        --db-dir) DB_DIR="$2"; shift 2 ;;
        --species) SPECIES="$2"; shift 2 ;;
        --evalue) E_threshold="$2"; shift 2 ;;
        --threads) NUM_THREADS="$2"; shift 2 ;;
        --memory-limit-gb) MEMORY_LIMIT_GB="$2"; shift 2 ;;
        --monitor-interval-sec) MONITOR_INTERVAL_SEC="$2"; shift 2 ;;
        --help) usage; exit 0 ;;
        BCR|TCR|BOTH|BCR,TCR|TCR,BCR) db_cell_type="$1"; shift ;;
        *) fail "未知参数: $1" ;;
    esac
done

if [ -z "$MONITOR_DIR" ]; then
    MONITOR_DIR="${OUTPUT_DIR}/monitor_logs"
fi

if [ -z "$SUMMARY_FILE" ]; then
    SUMMARY_FILE="${OUTPUT_DIR}/igblastn_run_summary.tsv"
fi

usage() {
    cat <<'EOF'
Usage:
  bash 3.work_igblastn_unified.sh [options] [BCR|TCR|BOTH|BCR,TCR]

Options:
  --data-dir DIR[,DIR...]     pandaseq 输出目录（可多次指定，支持逗号分隔）
  --output-dir DIR            igblastn 输出目录，默认 ${SCRIPT_DIR}/3.igblastn_out
  --db-dir DIR                igblast 数据库目录
  --species NAME              物种: human / mouse / rhesus_monkey / rat，默认 human
  --evalue N                  e-value 阈值，默认 0.0001
  --threads N                 igblastn 线程数，默认 256
  --memory-limit-gb N         虚拟内存限制（GB），0=不限制，默认 50
  --monitor-interval-sec N    内存监控间隔秒数，0=禁用，默认 5
  --help                      显示帮助

也可通过位置参数指定细胞类型:
  bash 3.work_igblastn_unified.sh BOTH
  bash 3.work_igblastn_unified.sh --species mouse TCR

Examples:
  bash 3.work_igblastn_unified.sh BOTH
  bash 3.work_igblastn_unified.sh --threads 64 --memory-limit-gb 128 BCR
EOF
}

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

fail() {
    log "ERROR: $*"
    exit 1
}

normalize_cell_types() {
    local raw
    raw="$(printf '%s' "$db_cell_type" | tr '[:lower:]' '[:upper:]' | tr -d ' ')"

    case "$raw" in
        BCR)
            CELL_TYPES=("BCR")
            ;;
        TCR)
            CELL_TYPES=("TCR")
            ;;
        BOTH|BCR,TCR|TCR,BCR)
            CELL_TYPES=("BCR" "TCR")
            ;;
        -H|--HELP|HELP)
            usage
            exit 0
            ;;
        *)
            usage
            fail "Unsupported cell type input: $db_cell_type"
            ;;
    esac
}

set_memory_limit() {
    if ! [[ "$MEMORY_LIMIT_GB" =~ ^[0-9]+$ ]]; then
        fail "MEMORY_LIMIT_GB must be a non-negative integer."
    fi

    if [ "$MEMORY_LIMIT_GB" -gt 0 ]; then
        local limit_kb
        limit_kb=$((MEMORY_LIMIT_GB * 1024 * 1024))
        if ulimit -v "$limit_kb" 2>/dev/null; then
            log "Virtual memory limit enabled: ${MEMORY_LIMIT_GB} GB"
        else
            log "WARNING: Failed to apply ulimit -v ${limit_kb}; memory limit not enforced."
        fi
    else
        log "Virtual memory limit disabled."
    fi
}

get_db_config() {
    local db_cell_type="$1"

    case "$db_cell_type" in
        BCR)
            INDEX="IG"
            IG_CELL_TYPE="Ig"
            index="$INDEX"
            ig_cell_type="$IG_CELL_TYPE"
            ;;
        TCR)
            INDEX="TR"
            IG_CELL_TYPE="TCR"
            index="$INDEX"
            ig_cell_type="$IG_CELL_TYPE"
            ;;
        *)
            fail "Unsupported db cell type: $db_cell_type"
            ;;
    esac
}

monitor_process_memory() {
    local pid="$1"
    local label="$2"
    local monitor_file="$3"
    local interval="$4"
    local peak_rss_kb=0

    while kill -0 "$pid" 2>/dev/null; do
        local timestamp
        local rss_kb
        local rss_mb
        local peak_rss_mb

        timestamp="$(date '+%F %T')"
        rss_kb="$(ps -o rss= -p "$pid" 2>/dev/null | awk 'NF {print $1; exit}')"
        rss_kb="${rss_kb:-0}"

        if [[ "$rss_kb" =~ ^[0-9]+$ ]] && [ "$rss_kb" -gt "$peak_rss_kb" ]; then
            peak_rss_kb="$rss_kb"
        fi

        rss_mb=$(((rss_kb + 1023) / 1024))
        peak_rss_mb=$(((peak_rss_kb + 1023) / 1024))

        printf '%s\tpid=%s\trss_mb=%s\tpeak_rss_mb=%s\n' \
            "$timestamp" "$pid" "$rss_mb" "$peak_rss_mb" >> "$monitor_file"
        log "${label} memory rss=${rss_mb}MB peak=${peak_rss_mb}MB"

        sleep "$interval"
    done

    printf '%s\n' "$peak_rss_kb" > "${monitor_file}.peak"
}

read_peak_rss_mb() {
    local peak_file="$1"
    local peak_kb=0

    if [ -f "$peak_file" ]; then
        peak_kb="$(tr -d '[:space:]' < "$peak_file")"
    fi

    if [[ ! "$peak_kb" =~ ^[0-9]+$ ]]; then
        peak_kb=0
    fi

    printf '%s' $(((peak_kb + 1023) / 1024))
}

normalize_cell_types

command -v igblastn >/dev/null 2>&1 || fail "igblastn command not found in PATH."

[ -d "$DB_DIR" ] || fail "DB_DIR does not exist: $DB_DIR"


declare -a MERGED_FILES=()
declare -A FILE_OUTPUT_SUBDIR=()


for MERGED_DIR in "${MERGED_DIRS[@]}"; do
    # 去掉 Windows 回车符和首尾空白
    MERGED_DIR="$(printf '%s' "$MERGED_DIR" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

    log "检查输入目录: [$MERGED_DIR]"

    if [ ! -d "$MERGED_DIR" ]; then
        log "ERROR: MERGED_DIR does not exist: [$MERGED_DIR]"
        ls -lh "$(dirname "$MERGED_DIR")" || true
        exit 1
    fi

    input_base="$(basename "$MERGED_DIR")"

    # 判断该输入目录下是否存在一级子目录
    SUBDIRS=()
    while IFS= read -r -d '' subdir; do
        SUBDIRS+=("$subdir")
    done < <(find "$MERGED_DIR" -mindepth 1 -maxdepth 1 -type d -print0)

    if [ "${#SUBDIRS[@]}" -eq 0 ]; then
        # 情况 1：输入路径下没有子目录
        # 输出到 OUTPUT_DIR/输入目录名/
        echo "No subdirectories found. Searching in $MERGED_DIR"
        while IFS= read -r -d '' file; do
            MERGED_FILES+=("$file")
            FILE_OUTPUT_SUBDIR["$file"]="$input_base"
        done < <(
            find "$MERGED_DIR" -maxdepth 1 -type f \( \
                -name "*.fasta" -o \
                -name "*.fa" \
            \) -print0
        )
    else
        # 情况 2：输入路径下有子目录
        # 每个子目录输出到 OUTPUT_DIR/子目录名/
        for subdir in "${SUBDIRS[@]}"; do
            subdir_base="$(basename "$subdir")"
            echo "Searching in subdirectory: $subdir_base"
            while IFS= read -r -d '' file; do
                MERGED_FILES+=("$file")
                FILE_OUTPUT_SUBDIR["$file"]="$subdir_base"
            done < <(
                find "$subdir" -type f \( \
                    -name "*.fasta" -o \
                    -name "*.fa" \
                \) -print0
            )
        done
    fi
done

[ "${#MERGED_FILES[@]}" -gt 0 ] || fail "No fastq/fasta files found in input directories"


if ! [[ "$MONITOR_INTERVAL_SEC" =~ ^[0-9]+$ ]]; then
    fail "MONITOR_INTERVAL_SEC must be a non-negative integer."
fi

if [ "$MONITOR_INTERVAL_SEC" -gt 0 ]; then
    command -v ps >/dev/null 2>&1 || fail "ps command not found; required for memory monitoring."
fi

mkdir -p "$OUTPUT_DIR" "$MONITOR_DIR"
set_memory_limit

printf 'cell_type\tsample\toutput_file\texit_code\telapsed_sec\tpeak_rss_mb\n' > "$SUMMARY_FILE"

TOTAL_SAMPLES="${#MERGED_FILES[@]}"
TOTAL_TASKS=$((TOTAL_SAMPLES * ${#CELL_TYPES[@]}))
DONE_TASKS=0
FAILED_TASKS=0

log "Found ${TOTAL_SAMPLES} merged fasta files."
log "Planned tasks: ${TOTAL_TASKS} ($(printf '%s ' "${CELL_TYPES[@]}" | sed 's/ $//'))"
log "Output directory: $OUTPUT_DIR"
log "Summary file: $SUMMARY_FILE"

cd "$DB_DIR" || fail "Cannot cd to DB_DIR: $DB_DIR"

for DB_CELL_TYPE in "${CELL_TYPES[@]}"; do
    get_db_config "$DB_CELL_TYPE"
    log "Starting cell type: ${DB_CELL_TYPE}"

    for MERGED_FILE in "${MERGED_FILES[@]}"; do
        BASENAME="$(basename "$MERGED_FILE")"

        SAMPLE="$BASENAME"
        SAMPLE="${SAMPLE%.fastq.gz}"
        SAMPLE="${SAMPLE%.fq.gz}"
        SAMPLE="${SAMPLE%.fastq}"
        SAMPLE="${SAMPLE%.fq}"
        SAMPLE="${SAMPLE%.fasta}"
        SAMPLE="${SAMPLE%.fa}"
        SAMPLE="${SAMPLE%_merged}"

        OUT_SUBDIR="${FILE_OUTPUT_SUBDIR[$MERGED_FILE]}"
        SAMPLE_OUTPUT_DIR="${OUTPUT_DIR}/${OUT_SUBDIR}"
        SAMPLE_MONITOR_DIR="${MONITOR_DIR}/${OUT_SUBDIR}"

        mkdir -p "$SAMPLE_OUTPUT_DIR" "$SAMPLE_MONITOR_DIR"

        OUT_FILE="${SAMPLE_OUTPUT_DIR}/${SAMPLE}_igblastn_${DB_CELL_TYPE}.tsv"
        MONITOR_FILE="${SAMPLE_MONITOR_DIR}/${SAMPLE}_${DB_CELL_TYPE}.mem.log"
        DONE_TASKS=$((DONE_TASKS + 1))
        TASK_PERCENT=$((DONE_TASKS * 100 / TOTAL_TASKS))
        TASK_LABEL="[${DONE_TASKS}/${TOTAL_TASKS} ${TASK_PERCENT}%] [${DB_CELL_TYPE}] ${SAMPLE}"
        log "${TASK_LABEL} started"

        START_TS="$(date +%s)"

        igblastn \
            -query "$MERGED_FILE" \
            -germline_db_V "${DB_DIR}/database/${SPECIES}/${DB_CELL_TYPE}/${SPECIES}_gl_${INDEX}_V" \
            -germline_db_D "${DB_DIR}/database/${SPECIES}/${DB_CELL_TYPE}/${SPECIES}_gl_${INDEX}_D" \
            -germline_db_J "${DB_DIR}/database/${SPECIES}/${DB_CELL_TYPE}/${SPECIES}_gl_${INDEX}_J" \
            -c_region_db "${DB_DIR}/database/${SPECIES}/${DB_CELL_TYPE}/${SPECIES}_gl_${INDEX}_C" \
            -auxiliary_data "${DB_DIR}/optional_file/${SPECIES}_gl.aux" \
            -organism "$SPECIES" \
            -ig_seqtype "$IG_CELL_TYPE" \
            -num_alignments_V 1 -num_alignments_D 1 -num_alignments_J 1 -num_alignments_C 1 \
            -show_translation \
            -evalue "$E_threshold" \
            -num_threads "$NUM_THREADS" \
            -outfmt 19 \
            -out "$OUT_FILE" &
        IGBLAST_PID=$!

        MONITOR_PID=""
        if [ "$MONITOR_INTERVAL_SEC" -gt 0 ]; then
            : > "$MONITOR_FILE"
            monitor_process_memory "$IGBLAST_PID" "$TASK_LABEL" "$MONITOR_FILE" "$MONITOR_INTERVAL_SEC" &
            MONITOR_PID=$!
        fi

        wait "$IGBLAST_PID"
        EXIT_CODE=$?

        if [ -n "$MONITOR_PID" ]; then
            wait "$MONITOR_PID" 2>/dev/null || true
        fi

        END_TS="$(date +%s)"
        ELAPSED_SEC=$(( END_TS - START_TS ))
        PEAK_RSS_MB=0
        if [ -n "$MONITOR_PID" ]; then
            PEAK_RSS_MB="$(read_peak_rss_mb "${MONITOR_FILE}.peak")"
        fi

        printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
            "$DB_CELL_TYPE" "$SAMPLE" "$OUT_FILE" "$EXIT_CODE" "$ELAPSED_SEC" "$PEAK_RSS_MB" >> "$SUMMARY_FILE"

        if [ "$EXIT_CODE" -eq 0 ]; then
            log "${TASK_LABEL} finished in ${ELAPSED_SEC}s, peak memory ${PEAK_RSS_MB}MB"
        else
            FAILED_TASKS=$((FAILED_TASKS + 1))
            log "${TASK_LABEL} failed with exit code ${EXIT_CODE} after ${ELAPSED_SEC}s, peak memory ${PEAK_RSS_MB}MB"
        fi
    done
done

SUCCESS_TASKS=$((TOTAL_TASKS - FAILED_TASKS))
log "All tasks finished. success=${SUCCESS_TASKS} failed=${FAILED_TASKS}"

if [ "$FAILED_TASKS" -gt 0 ]; then
    exit 1
fi
