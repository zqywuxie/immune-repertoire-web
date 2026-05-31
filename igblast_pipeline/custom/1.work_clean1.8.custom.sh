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
    command -v "$1" >/dev/null 2>&1 || die "缺少命令: $1"
}

kb_to_mb() {
    awk -v kb="${1:-0}" 'BEGIN { printf "%.1f", kb / 1024 }'
}

apply_memory_limit() {
    if [[ "$MEMORY_LIMIT_MB" =~ ^[0-9]+$ ]] && (( MEMORY_LIMIT_MB > 0 )); then
        ulimit -v $((MEMORY_LIMIT_MB * 1024)) || die "无法设置内存限制 ${MEMORY_LIMIT_MB}MB"
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
        warn "forward 文件 $(basename "$forward_file") 的 header 显示 read${forward_num}，预期 read1"
    fi

    if [[ -n "$reverse_num" && "$reverse_num" != "2" ]]; then
        warn "reverse 文件 $(basename "$reverse_file") 的 header 显示 read${reverse_num}，预期 read2"
    fi
}

register_sample() {
    local sample_name="$1"
    local forward_file="$2"
    local reverse_file="$3"
    local source_type="$4"

    if [[ -n "${SAMPLE_SOURCE[$sample_name]:-}" ]]; then
        warn "重复样本 ${sample_name}，保留 ${SAMPLE_SOURCE[$sample_name]} 来源，跳过 ${source_type}"
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
    local forward_path forward_base sample_name reverse_path

    SAMPLE_NAMES=()
    declare -gA SAMPLE_FORWARD=()
    declare -gA SAMPLE_REVERSE=()
    declare -gA SAMPLE_SOURCE=()

    shopt -s nullglob

    for ext in $INPUT_EXT; do
        for forward_path in "$input_dir"/*"${FORWARD_INPUT_SUFFIX}.${ext}"; do
            [[ -f "$forward_path" ]] || continue
            forward_base=$(basename "$forward_path")
            sample_name="${forward_base%${FORWARD_INPUT_SUFFIX}.${ext}}"
            reverse_path=$(resolve_input_file "$input_dir" "$sample_name" "$REVERSE_INPUT_SUFFIX") || {
                warn "缺少配对文件，跳过样本 ${sample_name}"
                continue
            }
            register_sample "$sample_name" "$forward_path" "$reverse_path" "flat-file"
        done
    done

    for sample_dir in "$input_dir"/*/; do
        [[ -d "$sample_dir" ]] || continue
        sample_name=$(basename "$sample_dir")
        forward_path=$(resolve_input_file "$sample_dir" "$sample_name" "$FORWARD_INPUT_SUFFIX") || true
        reverse_path=$(resolve_input_file "$sample_dir" "$sample_name" "$REVERSE_INPUT_SUFFIX") || true

        if [[ -n "$forward_path" && -n "$reverse_path" ]]; then
            register_sample "$sample_name" "$forward_path" "$reverse_path" "sample-dir"
        elif [[ -f "$forward_path" || -f "$reverse_path" ]]; then
            warn "样本目录 ${sample_name} 中缺少配对文件"
        fi
    done

    shopt -u nullglob
}

usage() {
    cat <<'EOF'
用法:
  bash 1.work_clean1.8.custom.sh [选项]

选项:
  --input-dir DIR                输入目录，默认 ../0.classified_fastq/paired_end
  --output-dir DIR               输出目录
  --forward-input-suffix SUFFIX  forward 端输入后缀（不含扩展名），默认 _1
  --reverse-input-suffix SUFFIX  reverse 端输入后缀（不含扩展名），默认 _2
  --input-ext EXT_LIST           输入扩展名列表（空格分隔），默认 "fq fastq fq.gz fastq.gz"
  --forward-output-suffix SUFFIX forward 端输出后缀，默认 _forward_cleaned.fq
  --reverse-output-suffix SUFFIX reverse 端输出后缀，默认 _reverse_cleaned.fq
  --memory-limit-mb N            每个处理任务的虚拟内存上限，默认 2048
  --monitor-interval-sec N       内存监控输出间隔秒数，默认 5
  --disable-read-check           不检查 header 中的 read1/read2 编号
  --help                         显示帮助

说明:
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
        *) die "未知参数: $1" ;;
    esac
done

clean_fastq_v18() {
    local input_file="$1"
    local output_file="$2"
    local temp_file="$3"

    trap 'rm -f "$temp_file"' RETURN

    if [[ "$input_file" == *.gz ]]; then
        gzip -dc "$input_file" > "$temp_file"
    else
        cp "$input_file" "$temp_file"
    fi

    awk '{
        if (NR%4==1) {
            sub(/#[^ ]*/, "", $0)
        }
        print
    }' "$temp_file" > "$output_file"
}

require_command awk
require_command gzip
mkdir -p "$OUTPUT_DIR"

collect_samples "$INPUT_DIR"
TOTAL_SAMPLES=${#SAMPLE_NAMES[@]}
(( TOTAL_SAMPLES > 0 )) || die "在 ${INPUT_DIR} 中未找到可配对的样本"

info "开始处理，样本数=${TOTAL_SAMPLES} input=${INPUT_DIR} output=${OUTPUT_DIR}"
info "后缀映射 forward=${FORWARD_INPUT_SUFFIX} reverse=${REVERSE_INPUT_SUFFIX}"
info "内存限制=${MEMORY_LIMIT_MB}MB 监控间隔=${MONITOR_INTERVAL_SEC}s"

SUCCESS_COUNT=0
FAIL_COUNT=0

for ((i = 0; i < TOTAL_SAMPLES; i++)); do
    step=$((i + 1))
    sample="${SAMPLE_NAMES[i]}"
    forward_file="${SAMPLE_FORWARD[$sample]}"
    reverse_file="${SAMPLE_REVERSE[$sample]}"
    sample_output_dir="${OUTPUT_DIR}/${sample}"
    forward_out="${sample_output_dir}/${sample}${FORWARD_OUTPUT_SUFFIX}"
    reverse_out="${sample_output_dir}/${sample}${REVERSE_OUTPUT_SUFFIX}"
    forward_tmp="${sample_output_dir}/${sample}.forward.tmp.fq"
    reverse_tmp="${sample_output_dir}/${sample}.reverse.tmp.fq"

    mkdir -p "$sample_output_dir"
    info "[${step}/${TOTAL_SAMPLES}] 准备处理样本=${sample} source=${SAMPLE_SOURCE[$sample]}"
    validate_pair_orientation "$forward_file" "$reverse_file"

    if ! run_with_monitor "clean-forward ${sample}" clean_fastq_v18 "$forward_file" "$forward_out" "$forward_tmp"; then
        warn "样本 ${sample} 的 forward 清洗失败"
        ((FAIL_COUNT += 1))
        continue
    fi

    if ! run_with_monitor "clean-reverse ${sample}" clean_fastq_v18 "$reverse_file" "$reverse_out" "$reverse_tmp"; then
        warn "样本 ${sample} 的 reverse 清洗失败"
        ((FAIL_COUNT += 1))
        continue
    fi

    ((SUCCESS_COUNT += 1))
    info "[${step}/${TOTAL_SAMPLES}] 样本 ${sample} 完成"
done

info "处理结束 success=${SUCCESS_COUNT} fail=${FAIL_COUNT} total=${TOTAL_SAMPLES}"
