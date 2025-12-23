# Final Versions Scripts - Standalone Analysis Scripts

This directory contains standalone analysis scripts that were not integrated into the web application due to their specific requirements and hardcoded paths.

## Integrated Scripts

The following scripts have been successfully integrated as analysis modules in `flask_app/services/analysis/modules/`:

1. **sequencing_reads_bar_chart_final.py** → `sequencing_reads_chart.py`
   - Generates reads and percentage bar charts for TRA/TRB/TRD/TRG/IGH/IGK/IGL chains
   - Now available as "sequencing_reads_chart" analysis type in the web app

2. **ig_other_isotype_metrics_final.py** → `ig_other_isotype_metrics.py`
   - Analyzes IG other isotype metrics (IGHA, IGHG12, IGHG34, IGHM_IGHD)
   - Now available as "ig_other_isotype_metrics" analysis type in the web app

3. **extract_shm_fields_final.py** → `shm_fields_analysis.py`
   - Analyzes somatic hypermutation (SHM) fields for different isotypes
   - Now available as "shm_fields_analysis" analysis type in the web app

## Skipped Scripts

The following scripts were not integrated because they don't fit the web application pattern:

### 1. extract_bcell_isotype_final.py
- **Purpose**: Extracts B cell isotype distribution from PDF reports
- **Reason for skipping**: 
  - Requires PDF files as input
  - Hardcoded file paths to specific directories
  - Uses pdfplumber for PDF parsing
- **Usage**: Standalone script for batch processing of PDF reports

### 2. extract_ct_shm_classification_final.py
- **Purpose**: CT-specific SHM classification analysis
- **Reason for skipping**:
  - CT sample-specific logic
  - Hardcoded sample patterns (NW_11_*CT)
  - Specialized classification workflow
- **Usage**: Standalone script for CT dataset analysis

### 3. extract_shm_ct_samples_final.py
- **Purpose**: Extracts SHM data specifically for CT samples
- **Reason for skipping**:
  - CT sample-specific extraction logic
  - Hardcoded sample names and patterns
  - Designed for specific dataset structure
- **Usage**: Standalone script for CT SHM data extraction

## Running Standalone Scripts

To run the standalone scripts:

```bash
cd Final_Versions_Scripts
python extract_bcell_isotype_final.py
python extract_ct_shm_classification_final.py
python extract_shm_ct_samples_final.py
```

**Note**: These scripts require:
- Specific file paths and directory structures
- Access to the shared data directory
- Python dependencies: pdfplumber, pandas, matplotlib, seaborn

## Integration Considerations

If future integration is desired, the following changes would be needed:

1. **PDF-based scripts**: Modify to accept PDF uploads through the web interface
2. **CT-specific scripts**: Generalize the logic to work with any sample pattern
3. **Hardcoded paths**: Convert to configurable parameters
4. **Output handling**: Adapt to return results in web-compatible format
