#!/bin/bash

# variables
MERGED_DIR="/workspace/igblast/results_251029/2.pandaseq_merged/20211109/SRM_SY_0324"         # pandaseq output directory
OUTPUT_DIR="/workspace/igblast/results_251029/3.igblastn/20211109/SRM_SY_0324"   
DB_DIR="/workspace/igblast/igblast"             # igblast database directory
SPECIES="human"                                 # "human" "mouse" "rhesus_monkey" "rat"
db_cell_type="TCR"                              # "BCR" "TCR"
index=""                      
ig_cell_type=""                
E_threshold='0.0001'                            # Default = `20'
NUM_THREADS='256'               
if [ "$db_cell_type" == "BCR" ]; then
    index="IG"                       
    ig_cell_type="Ig" 
else
    index="TR"
    ig_cell_type="TCR"
fi

# igblastn command
mkdir -p "$OUTPUT_DIR"
cd $DB_DIR

# REST_FILES=("W_YZM0108_merged.fasta" "W_ZYC_merged.fasta" "WCH_merged.fasta" "WGH_merged.fasta" "WHY_merged.fasta" "WXZ_merged.fasta" "XCM_merged.fasta" "XHY_merged.fasta" "YGM_merged.fasta" "YGQ_merged.fasta" "YXX_merged.fasta" "ZTY_merged.fasta" "ZXZ_merged.fasta")

for MERGED_FILE in "$MERGED_DIR"/*_merged.fasta; do
# for REST_FILE in "${REST_FILES[@]}"; do
    # MERGED_FILE="$MERGED_DIR/$REST_FILE"
    BASENAME=$(basename "$MERGED_FILE")
    SAMPLE=${BASENAME%_merged.fasta}
    OUT_FILE="${OUTPUT_DIR}/${SAMPLE}_igblastn_${db_cell_type}.tsv"

    igblastn \
        -query "$MERGED_FILE" \
        -germline_db_V "${DB_DIR}/database/${SPECIES}/${db_cell_type}/${SPECIES}_gl_${index}_V" \
        -germline_db_D "${DB_DIR}/database/${SPECIES}/${db_cell_type}/${SPECIES}_gl_${index}_D" \
        -germline_db_J "${DB_DIR}/database/${SPECIES}/${db_cell_type}/${SPECIES}_gl_${index}_J" \
        -c_region_db "${DB_DIR}/database/${SPECIES}/${db_cell_type}/${SPECIES}_gl_${index}_C" \
        -auxiliary_data "${DB_DIR}/optional_file/${SPECIES}_gl.aux" \
        -organism $SPECIES \
        -ig_seqtype $ig_cell_type \
        -num_alignments_V 1 -num_alignments_D 1 -num_alignments_J 1 -num_alignments_C 1 \
        -show_translation \
        -evalue $E_threshold \
        -num_threads $NUM_THREADS \
        -outfmt 19 \
        -out $OUT_FILE

done
