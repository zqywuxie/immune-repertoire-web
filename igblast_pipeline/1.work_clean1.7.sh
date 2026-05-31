#!/bin/bash
# 处理header格式
set -e

INPUT_DIR="/workspace/igblast/data_251029/SRM_SY/20250724_01_YPL6_umi/fastq"
OUTPUT_DIR="/workspace/igblast/results_251029/1.clean_data/20250724_01_YPL6_umi/fastq"

mkdir -p "$OUTPUT_DIR"

for sample_dir in "$INPUT_DIR"/*/; do
    sample_name=$(basename "$sample_dir")
    output_dir="${OUTPUT_DIR}/${sample_name}"

    fq_gz_j="${sample_dir}${sample_name}_j.fq.gz"
    fq_gz_v="${sample_dir}${sample_name}_v.fq.gz"

    if [ ! -f "$fq_gz_j" ] || [ ! -f "$fq_gz_v" ]; then
        echo "未找到文件: $fq_gz_j 或 $fq_gz_v，跳过样本 $sample_name"
        continue
    fi

    mkdir -p "$output_dir"

    for f in "$fq_gz_j" "$fq_gz_v"; do
      basename=$(basename "$f")
      fixed="${basename%.fq.gz}_cleaned.fq"
      # zcat "$f" | awk '{if(NR%4==1){sub(/#[^ ]*/, "", $0)}; print}'| sed -E '/^@/s/(run[^ ]*)/echo "\1" | sed -E "s\/(run)|[A-Za-z]/\1/g"/e' > "${output_dir}/${fixed}"
      # GNU sed version
      # zcat "$f" | sed -E '/^@/{s/#([^ ]*)//g; s/(run[^ ]*)/echo "\1" | sed -E "s\/(run)|[A-Za-z]/\1/g"/e}' > "${output_dir}/${fixed}"
      zcat "$f" | \
      awk 'NR%4==1{
        sub(/#[^ ]*/, "", $1)
        split($1, a, ":")
        flag=0
        for (i=1; i<=length(a); i++) {
            if (a[i] ~ /run/) flag=1
            if (flag==1 && a[i] !~ /^run/) gsub(/[A-Za-z]/, "", a[i])
        }
        out=a[1]
        for (i=2; i<=length(a); i++) out=out":"a[i]
        print out" "$2
        flag=0
        next
    }
    {print}' > "${output_dir}/${fixed}"
    done

done
