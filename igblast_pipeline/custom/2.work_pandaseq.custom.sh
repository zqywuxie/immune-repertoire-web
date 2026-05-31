#!/bin/bash
set -e

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

DATA_DIRS=("${SCRIPT_DIR}/../1.clean_data")
OUTPUT_DIR="${SCRIPT_DIR}/2.pandaseq"
STATS_FILE="${OUTPUT_DIR}/pandaseq_summary.csv"

FORWARD_CLEAN_SUFFIX="_1"
REVERSE_CLEAN_SUFFIX="_2"
INPUT_EXT="fq fastq"
NUM_THREADS='64'
MEMORY_LIMIT_MB=0
MONITOR_INTERVAL_SEC=5

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

run_with_monitor_logged() {
    local label="$1"
    local log_file="$2"
    shift 2

    local start_ts
    local current_rss=0
    local peak_rss=0
    local exit_code
    local cmd_pid
    local elapsed

    (
        apply_memory_limit
        "$@"
    ) >"$log_file" 2>&1 &
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

extract_stat_from_log() {
    local key="$1"
    local log_file="$2"
    grep -P "\tSTAT\t${key}" "$log_file" | awk 'END{print $4}'
}

resolve_input_file() {
    local dir="$1"
    local base="$2"
    local suffix="$3"

    local base_suffix="$suffix"
    local known_ext

    for known_ext in fq fastq fq.gz fastq.gz; do
        if [[ "$suffix" == *".${known_ext}" ]]; then
            base_suffix="${suffix%.${known_ext}}"
            break
        fi
    done

    local exact="${dir}/${base}${suffix}"
    if [[ -f "$exact" ]]; then
        printf '%s\n' "$exact"
        return 0
    fi

    local ext
    local candidate
    for ext in $INPUT_EXT; do
        candidate="${dir}/${base}${base_suffix}.${ext}"
        if [[ -f "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    return 1
}





usage() {
    cat <<'EOF'
用法:
  bash 2.work_pandaseq.custom.sh [选项]

选项:
  --data-dir DIR[,DIR...]        输入目录（可多次指定，也支持空格/逗号分隔多个路径）
  --output-dir DIR               pandaseq 输出目录
  --forward-clean-suffix SUFFIX  forward 文件后缀（不含扩展名），默认 _1
  --reverse-clean-suffix SUFFIX  reverse 文件后缀（不含扩展名），默认 _2
  --rc-ext EXT_LIST              输入文件扩展名列表（空格分隔），默认 "fq fastq"
  --threads N                    pandaseq 线程数，默认 64
  --memory-limit-mb N            每个 pandaseq 任务的虚拟内存上限，默认 0（不限制）
  --monitor-interval-sec N       内存监控输出间隔秒数，默认 5
  --help                         显示帮助

说明:
  --data-dir 支持三种形式：
    1. 单路径:     --data-dir /path/to/fastq
    2. 多次指定:   --data-dir /path/A --data-dir /path/B
    3. 逗号分隔:   --data-dir /path/A,/path/B
    跨目录的同名样本只保留首次出现的。
  SUFFIX 可以带扩展名（如 _1.fastq）也可以不带（如 _1）。
  不带扩展名时通过 --rc-ext 指定的扩展名列表尝试匹配。
  --rc-ext 默认 "fq fastq" 兼容 .fq 和 .fastq 两种格式。
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --data-dir)
            IFS=',' read -ra _paths <<< "$2"
            DATA_DIRS+=("${_paths[@]}")
            shift 2
            ;;
        --output-dir) OUTPUT_DIR="$2"; STATS_FILE="${OUTPUT_DIR}/pandaseq_summary.csv"; shift 2 ;;
        --forward-clean-suffix) FORWARD_CLEAN_SUFFIX="$2"; shift 2 ;;
        --reverse-clean-suffix) REVERSE_CLEAN_SUFFIX="$2"; shift 2 ;;
        --rc-ext) INPUT_EXT="$2"; shift 2 ;;
        --threads) NUM_THREADS="$2"; shift 2 ;;
        --memory-limit-mb) MEMORY_LIMIT_MB="$2"; shift 2 ;;
        --monitor-interval-sec) MONITOR_INTERVAL_SEC="$2"; shift 2 ;;
        --help) usage; exit 0 ;;
        *) die "未知参数: $1" ;;
    esac
done

mkdir -p "$OUTPUT_DIR"

echo "Sample,Total_Reads,OK_Reads,NOALGN,LOWQ,BADR,SLOW,Elapsed_sec,Merged_Percent" > "$STATS_FILE"

# 采集样本：扁文件配对 + 子目录遍历（支持多数据目录）
SAMPLE_NAMES=()
declare -A SAMPLE_FORWARD=()
declare -A SAMPLE_REVERSE=()
declare -A SAMPLE_SOURCE=()
declare -A SAMPLE_DATA_BASENAME=()

for data_dir in "${DATA_DIRS[@]}"; do
    [[ -d "$data_dir" ]] || { warn "数据目录不存在，跳过: ${data_dir}"; continue; }

    for forward_file in $(shopt -s nullglob; for ext in $INPUT_EXT; do printf '%s\n' "$data_dir"/*"${FORWARD_CLEAN_SUFFIX}.${ext}"; done); do
        forward_base=$(basename "$forward_file")
        for known_ext in $INPUT_EXT; do
            forward_base="${forward_base%.${known_ext}}"
        done
        sample="${forward_base%${FORWARD_CLEAN_SUFFIX}}"
        reverse_file=$(resolve_input_file "$data_dir" "$sample" "$REVERSE_CLEAN_SUFFIX") || {
            warn "缺少配对文件，跳过样本 ${sample} (${data_dir})"
            continue
        }

        if [[ -n "${SAMPLE_SOURCE[$sample]:-}" ]]; then
            warn "重复样本 ${sample}，保留 ${SAMPLE_SOURCE[$sample]} 来源，跳过 (${data_dir})"
            continue
        fi
        SAMPLE_NAMES+=("$sample")
        SAMPLE_FORWARD["$sample"]="$forward_file"
        SAMPLE_REVERSE["$sample"]="$reverse_file"
        SAMPLE_SOURCE["$sample"]="flat-file:${data_dir}"
        SAMPLE_DATA_BASENAME["$sample"]="$(basename "$data_dir")"
    done

    for sample_dir in "$data_dir"/*/; do
        [[ -d "$sample_dir" ]] || continue
        sample=$(basename "$sample_dir")
        forward_file=$(resolve_input_file "$sample_dir" "$sample" "$FORWARD_CLEAN_SUFFIX") || true
        reverse_file=$(resolve_input_file "$sample_dir" "$sample" "$REVERSE_CLEAN_SUFFIX") || true

        if [[ -n "$forward_file" && -n "$reverse_file" ]]; then
            if [[ -n "${SAMPLE_SOURCE[$sample]:-}" ]]; then
                warn "重复样本 ${sample}，保留 ${SAMPLE_SOURCE[$sample]} 来源，跳过 (${data_dir})"
                continue
            fi
            SAMPLE_NAMES+=("$sample")
            SAMPLE_FORWARD["$sample"]="$forward_file"
            SAMPLE_REVERSE["$sample"]="$reverse_file"
            SAMPLE_SOURCE["$sample"]="sample-dir:${data_dir}"
            SAMPLE_DATA_BASENAME["$sample"]="$(basename "$data_dir")"
        elif [[ -f "$forward_file" || -f "$reverse_file" ]]; then
            warn "样本目录 ${sample} 中缺少配对文件 (${data_dir})"
        fi
    done
done

TOTAL_SAMPLES=${#SAMPLE_NAMES[@]}

(( TOTAL_SAMPLES > 0 )) || die "在 ${DATA_DIRS[*]} 中未找到有效的样本数据"
info "开始 pandaseq，样本数=${TOTAL_SAMPLES} data_dirs=${DATA_DIRS[*]} output=${OUTPUT_DIR}"
info "输入后缀 forward=${FORWARD_CLEAN_SUFFIX} reverse=${REVERSE_CLEAN_SUFFIX}"
info "线程=${NUM_THREADS} 内存限制=${MEMORY_LIMIT_MB}MB 监控间隔=${MONITOR_INTERVAL_SEC}s"

SUCCESS_COUNT=0
FAIL_COUNT=0

for ((i = 0; i < TOTAL_SAMPLES; i++)); do
    step=$((i + 1))
    sample="${SAMPLE_NAMES[i]}"
    forward_file="${SAMPLE_FORWARD[$sample]}"
    reverse_file="${SAMPLE_REVERSE[$sample]}"
    source_type="${SAMPLE_SOURCE[$sample]}"

    data_basename="${SAMPLE_DATA_BASENAME[$sample]}"
    if [[ "$source_type" == sample-dir:* ]]; then
        sample_output_dir="${OUTPUT_DIR}/${data_basename}/${sample}"
        mkdir -p "$sample_output_dir"
        out_fasta="${sample_output_dir}/${sample}_merged.fasta"
        log_file="${sample_output_dir}/${sample}_pandaseq.log"
    else
        mkdir -p "${OUTPUT_DIR}/${data_basename}"
        out_fasta="${OUTPUT_DIR}/${data_basename}/${sample}_merged.fasta"
        log_file="${OUTPUT_DIR}/${data_basename}/${sample}_pandaseq.log"
    fi

    if [[ ! -f "$forward_file" || ! -f "$reverse_file" ]]; then
        warn "[${step}/${TOTAL_SAMPLES}] 样本 ${sample} 缺少输入文件，跳过"
        ((FAIL_COUNT += 1))
        continue
    fi

    info "[${step}/${TOTAL_SAMPLES}] 开始拼接样本=${sample} source=${source_type}"
    run_with_monitor_logged "pandaseq ${sample}" "$log_file" pandaseq -f "$forward_file" -r "$reverse_file" -B -w "$out_fasta" -T "$NUM_THREADS"

    TOTAL=$(extract_stat_from_log "READS" "$log_file")
    OK=$(extract_stat_from_log "OK" "$log_file")
    NOALGN=$(extract_stat_from_log "NOALGN" "$log_file")
    LOWQ=$(extract_stat_from_log "LOWQ" "$log_file")
    BADR=$(extract_stat_from_log "BADR" "$log_file")
    SLOW=$(extract_stat_from_log "SLOW" "$log_file")
    ELAPSED=$(extract_stat_from_log "ELAPSED" "$log_file")

    TOTAL=${TOTAL:-NA}
    OK=${OK:-NA}
    NOALGN=${NOALGN:-NA}
    LOWQ=${LOWQ:-NA}
    BADR=${BADR:-NA}
    SLOW=${SLOW:-NA}
    ELAPSED=${ELAPSED:-NA}

    if [[ "$TOTAL" != "NA" && "$OK" != "NA" && "$TOTAL" -gt 0 ]]; then
        PERCENT=$(awk -v ok="$OK" -v total="$TOTAL" 'BEGIN { printf "%.2f", (ok / total) * 100 }')
    else
        PERCENT="NA"
    fi

    echo "${sample},${TOTAL},${OK},${NOALGN},${LOWQ},${BADR},${SLOW},${ELAPSED},${PERCENT}" >> "$STATS_FILE"
    ((SUCCESS_COUNT += 1))
    info "[${step}/${TOTAL_SAMPLES}] 样本 ${sample} 完成 merged=${PERCENT}%"
done

info "pandaseq 结束 success=${SUCCESS_COUNT} fail=${FAIL_COUNT} total=${TOTAL_SAMPLES}"
info "统计文件: ${STATS_FILE}"
