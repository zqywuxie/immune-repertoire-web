#!/bin/bash
# 运行 pandaseq 并生成统计汇总

DATA_DIR="/workspace/igblast/results_251029/1.clean_data/20250724_01_YPL6_umi/fastq"
OUTPUT_DIR="./2.pandaseq_merged/20250724_01_YPL6_umi/fastq"
STATS_FILE="${OUTPUT_DIR}/pandaseq_summary.csv"
NUM_THREADS='64'

mkdir -p "$OUTPUT_DIR"

echo "Sample,Total_Reads,OK_Reads,NOALGN,LOWQ,BADR,SLOW,Elapsed_sec,Merged_Percent" > "$STATS_FILE"

for SAMPLE_DIR in "$DATA_DIR"/*/; do
    SAMPLE=$(basename "$SAMPLE_DIR")

    R1="${SAMPLE_DIR}${SAMPLE}_j_cleaned.fq"
    R2="${SAMPLE_DIR}${SAMPLE}_v_cleaned.fq"
    OUT="${OUTPUT_DIR}/${SAMPLE}_merged.fasta"
    LOG="${OUTPUT_DIR}/${SAMPLE}_pandaseq.log"

    pandaseq -f "$R1" -r "$R2" -B -w "$OUT" -T $NUM_THREADS > "$LOG" 2>&1

    TOTAL=$(grep -P "\tSTAT\tREADS" "$LOG" | awk 'END{print $4}')
    OK=$(grep -P "\tSTAT\tOK" "$LOG" | awk 'END{print $4}')
    NOALGN=$(grep -P "\tSTAT\tNOALGN" "$LOG" | awk 'END{print $4}')
    LOWQ=$(grep -P "\tSTAT\tLOWQ" "$LOG" | awk 'END{print $4}')
    BADR=$(grep -P "\tSTAT\tBADR" "$LOG" | awk 'END{print $4}')
    SLOW=$(grep -P "\tSTAT\tSLOW" "$LOG" | awk 'END{print $4}')
    ELAPSED=$(grep -P "\tSTAT\tELAPSED" "$LOG" | awk 'END{print $4}')

    # 若字段缺失则用 NA
    TOTAL=${TOTAL:-NA}
    OK=${OK:-NA}
    NOALGN=${NOALGN:-NA}
    LOWQ=${LOWQ:-NA}
    BADR=${BADR:-NA}
    SLOW=${SLOW:-NA}
    ELAPSED=${ELAPSED:-NA}

    if [[ "$TOTAL" != "NA" && "$OK" != "NA" && "$TOTAL" -gt 0 ]]; then
        PERCENT=$(awk -v ok="$OK" -v total="$TOTAL" 'BEGIN { printf "%.2f", (ok/total)*100 }')
    else
        PERCENT="NA"
    fi

    echo "${SAMPLE},${TOTAL},${OK},${NOALGN},${LOWQ},${BADR},${SLOW},${ELAPSED},${PERCENT}" >> "$STATS_FILE"
done
