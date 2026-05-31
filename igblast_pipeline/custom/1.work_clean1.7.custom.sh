#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

INPUT_DIR="${SCRIPT_DIR}/../0.classified_fastq/paired_end"
OUTPUT_DIR="${SCRIPT_DIR}/1.clean_data"
FORWARD_INPUT_SUFFIX="_1"
REVERSE_INPUT_SUFFIX="_2"
INPUT_EXT="fq fastq fq.gz fastq.gz"
FORWARD_OUTPUT_SUFFIX="_forward_cleaned.fq"
REVERSE_OUTPUT_SUFFIX="_reverse_cleaned.fq"
MEMORY_LIMIT_MB=2048
MONITOR_INTERVAL_SEC=5
VERIFY_READ_NUMBERS=1

timestamp() {
    date '+%F %T'
}

log() {
    local level="$1"
    shift
    printf '[%s] [%s] %s\n' "$(timestamp)" "$level" "$*"
}

info() {
    log INFO "$@"
}

warn() {
    log WARN "$@"
}

die() {
    log ERROR "$@"
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

kb_to_mb() {
    awk -v kb="${1:-0}" 'BEGIN { printf "%.1f", kb / 1024 }'
}

apply_memory_limit() {
    if [[ "$MEMORY_LIMIT_MB" =~ ^[0-9]+$ ]] && (( MEMORY_LIMIT_MB > 0 )); then
        ulimit -v $((MEMORY_LIMIT_MB * 1024)) || die "failed to set memory limit ${MEMORY_LIMIT_MB}MB"
    fi
}

process_tree_rss_kb() {
    local root_pid="$1"
    ps -e -o pid=,ppid=,rss= | awk -v root="$root_pid" '
        {
            pid = $1
            ppid = $2
            rss[pid] = $3
            children[ppid] = children[ppid] " " pid
        }
        END {
            print sum(root)
        }
        function sum(pid, total, count, i, ids) {
            if (pid == "" || seen[pid]++) {
                return 0
            }
            total = rss[pid] + 0
            count = split(children[pid], ids, " ")
            for (i = 1; i <= count; i++) {
                if (ids[i] != "") {
                    total += sum(ids[i])
                }
            }
            return total
        }
    '
}

run_with_monitor() {
    local label="$1"
    shift

    local start_ts
    local current_rss=0
    local peak_rss=0
    local exit_code
    local cmd_pid
    local elapsed

    (
        apply_memory_limit
        "$@"
    ) &
    cmd_pid=$!
    start_ts=$(date +%s)

    while kill -0 "$cmd_pid" 2>/dev/null; do
        current_rss=$(process_tree_rss_kb "$cmd_pid")
        if (( current_rss > peak_rss )); then
            peak_rss=$current_rss
        fi
        elapsed=$(( $(date +%s) - start_ts ))
        info "[monitor] ${label} elapsed=${elapsed}s rss=$(kb_to_mb "$current_rss")MB peak=$(kb_to_mb "$peak_rss")MB"
        sleep "$MONITOR_INTERVAL_SEC"
    done

    wait "$cmd_pid"
    exit_code=$?
    elapsed=$(( $(date +%s) - start_ts ))
    info "[monitor] ${label} done exit=${exit_code} elapsed=${elapsed}s peak=$(kb_to_mb "$peak_rss")MB"
    return "$exit_code"
}

stream_fastq() {
    local input_file="$1"
    if [[ "$input_file" == *.gz ]]; then
        gzip -dc "$input_file"
    else
        cat "$input_file"
    fi
}

read_first_line() {
    local input_file="$1"
    local line=""

    set +o pipefail
    if [[ "$input_file" == *.gz ]]; then
        line=$(gzip -dc "$input_file" 2>/dev/null | { IFS= read -r first || true; printf '%s\n' "$first"; })
    else
        IFS= read -r line < "$input_file" || true
    fi
    set -o pipefail

    printf '%s\n' "$line"
}

extract_read_number() {
    local header
    header=$(read_first_line "$1")
    awk '{
        split($2, parts, ":")
        if (parts[1] ~ /^[12]$/) {
            print parts[1]
        }
    }' <<<"$header"
}

validate_pair_orientation() {
    local forward_file="$1"
    local reverse_file="$2"
    local forward_num
    local reverse_num

    if [[ "$VERIFY_READ_NUMBERS" != "1" ]]; then
        return 0
    fi

    forward_num=$(extract_read_number "$forward_file")
    reverse_num=$(extract_read_number "$reverse_file")

    if [[ -n "$forward_num" && "$forward_num" != "1" ]]; then
        warn "forward file $(basename "$forward_file") header shows read${forward_num}, expected read1"
    fi

    if [[ -n "$reverse_num" && "$reverse_num" != "2" ]]; then
        warn "reverse file $(basename "$reverse_file") header shows read${reverse_num}, expected read2"
    fi
}

register_sample() {
    local sample_name="$1"
    local forward_file="$2"
    local reverse_file="$3"
    local source_type="$4"

    if [[ -n "${SAMPLE_SOURCE[$sample_name]:-}" ]]; then
        warn "duplicate sample=${sample_name}, keep ${SAMPLE_SOURCE[$sample_name]} and skip ${source_type}"
        return 0
    fi

    SAMPLE_NAMES+=("$sample_name")
    SAMPLE_FORWARD["$sample_name"]="$forward_file"
    SAMPLE_REVERSE["$sample_name"]="$reverse_file"
    SAMPLE_SOURCE["$sample_name"]="$source_type"
}

resolve_input_file() {
    local dir="$1"
    local base="$2"
    local suffix="$3"
    local ext candidate

    local exact="${dir}/${base}${suffix}"
    [[ -f "$exact" ]] && { printf '%s\n' "$exact"; return 0; }

    for ext in $INPUT_EXT; do
        candidate="${dir}/${base}${suffix}.${ext}"
        [[ -f "$candidate" ]] && { printf '%s\n' "$candidate"; return 0; }
    done
    return 1
}

collect_samples() {
    local input_dir="$1"
    local sample_dir sample_name forward_file reverse_file

    SAMPLE_NAMES=()
    declare -gA SAMPLE_FORWARD=()
    declare -gA SAMPLE_REVERSE=()
    declare -gA SAMPLE_SOURCE=()

    shopt -s nullglob

    for ext in $INPUT_EXT; do
        for forward_file in "$input_dir"/*"${FORWARD_INPUT_SUFFIX}.${ext}"; do
            [[ -f "$forward_file" ]] || continue
            local base
            base=$(basename "$forward_file")
            sample_name="${base%${FORWARD_INPUT_SUFFIX}.${ext}}"
            reverse_file=$(resolve_input_file "$input_dir" "$sample_name" "$REVERSE_INPUT_SUFFIX") || {
                warn "缺少配对文件，跳过样本 ${sample_name}"
                continue
            }
            register_sample "$sample_name" "$forward_file" "$reverse_file" "flat-file"
        done
    done

    for sample_dir in "$input_dir"/*/; do
        [[ -d "$sample_dir" ]] || continue
        sample_name=$(basename "$sample_dir")
        forward_file=$(resolve_input_file "$sample_dir" "$sample_name" "$FORWARD_INPUT_SUFFIX") || true
        reverse_file=$(resolve_input_file "$sample_dir" "$sample_name" "$REVERSE_INPUT_SUFFIX") || true

        if [[ -n "$forward_file" && -n "$reverse_file" ]]; then
            register_sample "$sample_name" "$forward_file" "$reverse_file" "sample-dir"
        elif [[ -f "$forward_file" || -f "$reverse_file" ]]; then
            warn "样本目录 ${sample_name} 中缺少配对文件"
        fi
    done

    shopt -u nullglob
}

usage() {
    cat <<'EOF'
Usage:
  bash 1.work_clean1.7.custom.sh [options]

Options:
  --input-dir DIR                input directory, default: ../0.classified_fastq/paired_end
  --output-dir DIR               output directory
  --forward-input-suffix SUFFIX  forward input suffix (without ext), default: _1
  --reverse-input-suffix SUFFIX  reverse input suffix (without ext), default: _2
  --input-ext EXT_LIST           input extensions (space-separated), default: "fq fastq fq.gz fastq.gz"
  --forward-output-suffix SUFFIX forward output suffix, default: _forward_cleaned.fq
  --reverse-output-suffix SUFFIX reverse output suffix, default: _reverse_cleaned.fq
  --memory-limit-mb N            per-task virtual memory limit in MB, default: 2048
  --monitor-interval-sec N       monitor interval in seconds, default: 5
  --disable-read-check           disable read1/read2 header check
  --help                         show this help message

Notes:
  INPUT_SUFFIX 不带扩展名，脚本会依次尝试 INPUT_EXT 中的扩展名匹配文件。
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --input-dir) INPUT_DIR="$2"; shift 2 ;;
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        --forward-input-suffix) FORWARD_INPUT_SUFFIX="$2"; shift 2 ;;
        --reverse-input-suffix) REVERSE_INPUT_SUFFIX="$2"; shift 2 ;;
        --input-ext) INPUT_EXT="$2"; shift 2 ;;
        --forward-output-suffix) FORWARD_OUTPUT_SUFFIX="$2"; shift 2 ;;
        --reverse-output-suffix) REVERSE_OUTPUT_SUFFIX="$2"; shift 2 ;;
        --memory-limit-mb) MEMORY_LIMIT_MB="$2"; shift 2 ;;
        --monitor-interval-sec) MONITOR_INTERVAL_SEC="$2"; shift 2 ;;
        --disable-read-check) VERIFY_READ_NUMBERS=0; shift ;;
        --help) usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

clean_fastq_v17() {
    local input_file="$1"
    local output_file="$2"

    stream_fastq "$input_file" | awk '
        NR % 4 == 1 {
            sub(/#[^ ]*/, "", $1)
            split($1, a, ":")
            flag = 0
            for (i = 1; i <= length(a); i++) {
                if (a[i] ~ /run/) flag = 1
                if (flag == 1 && a[i] !~ /^run/) gsub(/[A-Za-z]/, "", a[i])
            }
            out = a[1]
            for (i = 2; i <= length(a); i++) out = out ":" a[i]
            print out " " $2
            flag = 0
            next
        }
        { print }
    ' > "$output_file"
}



require_command awk
require_command gzip
require_command ps
mkdir -p "$OUTPUT_DIR"

collect_samples "$INPUT_DIR"
TOTAL_SAMPLES=${#SAMPLE_NAMES[@]}
(( TOTAL_SAMPLES > 0 )) || die "no paired samples found in ${INPUT_DIR}"

info "start processing total=${TOTAL_SAMPLES} input=${INPUT_DIR} output=${OUTPUT_DIR}"
info "suffix mapping forward=${FORWARD_INPUT_SUFFIX} reverse=${REVERSE_INPUT_SUFFIX}"
info "memory_limit=${MEMORY_LIMIT_MB}MB monitor_interval=${MONITOR_INTERVAL_SEC}s"

SUCCESS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0

for ((i = 0; i < TOTAL_SAMPLES; i++)); do
    step=$((i + 1))
    sample_name="${SAMPLE_NAMES[i]}"
    forward_file="${SAMPLE_FORWARD[$sample_name]}"
    reverse_file="${SAMPLE_REVERSE[$sample_name]}"
    sample_output_dir="${OUTPUT_DIR}/${sample_name}"
    forward_out="${sample_output_dir}/${sample_name}${FORWARD_OUTPUT_SUFFIX}"
    reverse_out="${sample_output_dir}/${sample_name}${REVERSE_OUTPUT_SUFFIX}"

    info "[${step}/${TOTAL_SAMPLES}] prepare sample=${sample_name} source=${SAMPLE_SOURCE[$sample_name]}"

    mkdir -p "$sample_output_dir"
    validate_pair_orientation "$forward_file" "$reverse_file"

    if ! run_with_monitor "clean-forward ${sample_name}" clean_fastq_v17 "$forward_file" "$forward_out"; then
        warn "sample ${sample_name} forward clean failed"
        ((FAIL_COUNT += 1))
        continue
    fi

    if ! run_with_monitor "clean-reverse ${sample_name}" clean_fastq_v17 "$reverse_file" "$reverse_out"; then
        warn "sample ${sample_name} reverse clean failed"
        ((FAIL_COUNT += 1))
        continue
    fi

    ((SUCCESS_COUNT += 1))
    info "[${step}/${TOTAL_SAMPLES}] sample=${sample_name} done"
done

info "finished success=${SUCCESS_COUNT} fail=${FAIL_COUNT} skipped=${SKIP_COUNT} total=${TOTAL_SAMPLES}"
