#!/bin/bash
set -e

INPUT_DIR="/workspace/igblast/data_251029/SRM_SY/20211109/SRM_SY_0324"
OUTPUT_DIR="/workspace/igblast/results_251029/1.clean_data/20211109/SRM_SY_0324"

mkdir -p "$OUTPUT_DIR"

for sample_dir in "$INPUT_DIR"/*/; do
    sample_name=$(basename "$sample_dir")
    output_dir="${OUTPUT_DIR}/${sample_name}"

    fq_gz_j="${sample_dir}${sample_name}_j.fq.gz"
    fq_j="${sample_dir}${sample_name}_j.fq"
    cleaned_fq_j="${output_dir}/${sample_name}_j_cleaned.fq"

    fq_gz_v="${sample_dir}${sample_name}_v.fq.gz"
    fq_v="${sample_dir}${sample_name}_v.fq"
    cleaned_fq_v="${output_dir}/${sample_name}_v_cleaned.fq"

    if [ ! -f "$fq_gz_j" ] || [ ! -f "$fq_gz_v" ]; then
        echo "未找到文件: $fq_gz_j 或 $fq_gz_v，跳过样本 $sample_name"
        continue
    fi

    mkdir -p "$output_dir"

    if ! gunzip -k "$fq_gz_j" 2>/dev/null; then
        echo "❌ 解压失败: $fq_gz_j，跳过样本 $sample_name"
        continue
    fi

    if ! gunzip -k "$fq_gz_v" 2>/dev/null; then
        echo "❌ 解压失败: $fq_gz_v，跳过样本 $sample_name"
        rm -f "$fq_j"
        continue
    fi

    # 删除 @ 行中 #... 到空格前的部分
    awk '{if(NR%4==1){sub(/#[^ ]*/, "", $0)}; print}' "$fq_j" > "$cleaned_fq_j"
    awk '{if(NR%4==1){sub(/#[^ ]*/, "", $0)}; print}' "$fq_v" > "$cleaned_fq_v"

    rm "$fq_j" "$fq_v"

done
