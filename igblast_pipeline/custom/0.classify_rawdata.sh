#!/bin/bash
set -e

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

DATA_DIRS=("${SCRIPT_DIR}/fastq")
OUTPUT_DIR="${SCRIPT_DIR}/0.classified_fastq"
INPUT_EXT="fq fastq fq.gz fastq.gz"
LINK_MODE="symlink"   # symlink | copy
PE_PATTERNS=("_1/_2" "_R1/_R2" "_forward/_reverse" "_F/_R")

timestamp() { date '+%F %T'; }
log() { local level="$1"; shift; printf '[%s] [%s] %s\n' "$(timestamp)" "$level" "$*"; }
info() { log INFO "$@"; }
warn() { log WARN "$@"; }
die()  { log ERROR "$@"; exit 1; }

usage() {
    cat <<'EOF'
用法:
  bash 0.classify_rawdata.sh [选项]

选项:
  --data-dir DIR[,DIR...]    输入目录（可多次指定，支持逗号分隔）
  --output-dir DIR           输出目录，默认 ${SCRIPT_DIR}/0.classified_fastq
  --ext EXT_LIST             文件扩展名（空格分隔），默认 "fq fastq fq.gz fastq.gz"
  --pe-patterns PATS         双端配对模式，逗号分隔，默认 "_1/_2,_R1/_R2,_forward/_reverse,_F/_R"
  --mode MODE                链接方式: symlink (默认) | copy
  --help                     显示帮助

输出结构:
  0.classified_fastq/
  ├── paired_end/        # 双端配对样本
  │   └── <sample>/
  │       ├── <sample>_1.fastq -> /原路径
  │       └── <sample>_2.fastq -> /原路径
  ├── single_end/        # 单端样本
  │   └── <sample>.fastq -> /原路径
  └── classify_summary.csv
EOF
}

# ---------- 参数解析 ----------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --data-dir)
            IFS=',' read -ra _paths <<< "$2"
            DATA_DIRS+=("${_paths[@]}")
            shift 2
            ;;
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        --ext) INPUT_EXT="$2"; shift 2 ;;
        --pe-patterns)
            IFS=',' read -ra PE_PATTERNS <<< "$2"
            shift 2
            ;;
        --mode) LINK_MODE="$2"; shift 2 ;;
        --help) usage; exit 0 ;;
        *) die "未知参数: $1" ;;
    esac
done

# ---------- 收集所有 FASTQ 文件 ----------
info "扫描数据目录: ${DATA_DIRS[*]}"
info "双端配对模式: ${PE_PATTERNS[*]}"

ALL_FILES=()
for data_dir in "${DATA_DIRS[@]}"; do
    [[ -d "$data_dir" ]] || { warn "目录不存在，跳过: ${data_dir}"; continue; }
    while IFS= read -r -d '' f; do
        ALL_FILES+=("$f")
    done < <(find "$data_dir" -type f \( -name '*.fq' -o -name '*.fastq' -o -name '*.fq.gz' -o -name '*.fastq.gz' \) -print0 2>/dev/null || true)
done

(( ${#ALL_FILES[@]} > 0 )) || die "未找到任何 FASTQ 文件"
info "共找到 ${#ALL_FILES[@]} 个 FASTQ 文件"

# ---------- 双端配对检测 ----------
declare -A FILE_PAIRS=()       # basename -> "forward_file|reverse_file|pattern"
declare -A PAIRED_SAMPLES=()   # basename -> 1
declare -a SINGLE_FILES=()

strip_pe_suffix() {
    local filename="$1"
    local base="${filename%.gz}"
    local ext=""
    for e in fq fastq fq.gz fastq.gz; do
        if [[ "$filename" == *".${e}" ]]; then
            ext=".${e}"
            base="${filename%.${e}}"
            break
        fi
    done

    for pair in "${PE_PATTERNS[@]}"; do
        local fwd_suf="${pair%%/*}"
        local rev_suf="${pair#*/}"
        if [[ "$base" == *"${fwd_suf}" ]]; then
            printf '%s|%s|%s\n' "${base%${fwd_suf}}" "$fwd_suf" "$pair"
            return 0
        elif [[ "$base" == *"${rev_suf}" ]]; then
            printf '%s|%s|%s\n' "${base%${rev_suf}}" "$rev_suf" "$pair"
            return 0
        fi
    done
    return 1
}

for f in "${ALL_FILES[@]}"; do
    fname=$(basename "$f")
    result=$(strip_pe_suffix "$fname") || {
        SINGLE_FILES+=("$f")
        continue
    }

    IFS='|' read -r base suffix pair_pattern <<< "$result"
    fwd_suf="${pair_pattern%%/*}"
    rev_suf="${pair_pattern#*/}"

    if [[ -n "${FILE_PAIRS[$base]:-}" ]]; then
        # 已有另一半，检查是否匹配
        IFS='|' read -r existing_f existing_suf existing_pair <<< "${FILE_PAIRS[$base]}"
        if [[ "$existing_pair" == "$pair_pattern" && "$existing_suf" != "$suffix" ]]; then
            PAIRED_SAMPLES["$base"]=1
            if [[ "$suffix" == "$fwd_suf" ]]; then
                FILE_PAIRS["${base}"]="${f}|${existing_f}|${pair_pattern}"
            else
                FILE_PAIRS["${base}"]="${existing_f}|${f}|${pair_pattern}"
            fi
        else
            warn "样本 ${base} 配对模式冲突，当作单端处理"
            SINGLE_FILES+=("$existing_f")
            SINGLE_FILES+=("$f")
            unset "FILE_PAIRS[$base]"
        fi
    else
        FILE_PAIRS["$base"]="${f}|${suffix}|${pair_pattern}"
    fi
done

# 处理未配对的残留
for base in "${!FILE_PAIRS[@]}"; do
    [[ -n "${PAIRED_SAMPLES[$base]:-}" ]] && continue
    IFS='|' read -r leftover_f leftover_suf leftover_pair <<< "${FILE_PAIRS[$base]}"
    warn "样本 ${base} 缺少配对 (仅有 ${leftover_suf})，归为单端"
    SINGLE_FILES+=("$leftover_f")
done

# ---------- 输出目录 & 链接 ----------
[[ "$OUTPUT_DIR" == "/" || "$OUTPUT_DIR" == "" ]] && die "输出目录不能为 / 或空"
[[ -d "$OUTPUT_DIR" ]] && rm -rf "$OUTPUT_DIR"
mkdir -p "${OUTPUT_DIR}/paired_end" "${OUTPUT_DIR}/single_end"

SUMMARY_FILE="${OUTPUT_DIR}/classify_summary.csv"
echo "Type,Sample,File1,File2,Pattern,Source_Dir" > "$SUMMARY_FILE"

do_link() {
    local src="$1"
    local dst="$2"
    case "$LINK_MODE" in
        copy) cp "$src" "$dst" ;;
        symlink|*) ln -s "$src" "$dst" ;;
    esac
}

info "输出模式: ${LINK_MODE}"

# 双端 — 统一规范化为 _1 / _2 后缀
for base in "${!PAIRED_SAMPLES[@]}"; do
    IFS='|' read -r fwd rev pattern <<< "${FILE_PAIRS[$base]}"
    sample_dir="${OUTPUT_DIR}/paired_end/${base}"
    mkdir -p "$sample_dir"

    ext=$(echo "$fwd" | grep -o '\.\(fq\|fastq\)\(\.gz\)\?$')
    fwd_dst="${sample_dir}/${base}_1${ext}"
    rev_dst="${sample_dir}/${base}_2${ext}"

    do_link "$fwd" "$fwd_dst"
    do_link "$rev" "$rev_dst"

    fwd_dir=$(dirname "$fwd")
    echo "paired,${base},${fwd},${rev},${pattern},${fwd_dir}" >> "$SUMMARY_FILE"
    info "[paired] ${base}  orig_pattern=${pattern} -> _1/_2"
done

# 单端
for f in "${SINGLE_FILES[@]}"; do
    fname=$(basename "$f")
    dst="${OUTPUT_DIR}/single_end/${fname}"
    do_link "$f" "$dst"
    f_dir=$(dirname "$f")
    echo "single,${fname},${f},,,${f_dir}" >> "$SUMMARY_FILE"
    info "[single] ${fname}"
done

# ---------- 统计 ----------
PE_COUNT=${#PAIRED_SAMPLES[@]}
SE_COUNT=${#SINGLE_FILES[@]}
TOTAL_FILES=${#ALL_FILES[@]}

info "============================================"
info "分类完成"
info "  总文件数:   ${TOTAL_FILES}"
info "  双端样本:   ${PE_COUNT}  (文件数: $((PE_COUNT * 2)))"
info "  单端文件:   ${SE_COUNT}"
info "  输出目录:   ${OUTPUT_DIR}"
info "  汇总文件:   ${SUMMARY_FILE}"
info "============================================"
