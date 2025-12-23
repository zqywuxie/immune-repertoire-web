/**
 * B Cell Isotype Analysis Module
 * Handles B cell isotype distribution analysis UI interactions
 */

const BcellIsotypeModule = {
    // State
    currentFileId: null,
    analysisResults: null,
    charts: {},
    fileUploader: null,
    colorSchemePreview: null,

    // Isotype list
    isotypes: ["IgM", "IgD", "IgA1/2", "IgG1/2", "IgG3/4", "IgE"],

    /**
     * Initialize the module
     */
    init: function () {
        this.initFileUploader();
        this.initColorSchemePreview();
        this.bindEvents();
    },

    /**
     * Initialize Color Scheme Preview
     */
    initColorSchemePreview: function () {
        try {
            this.colorSchemePreview = new ColorSchemePreview('colorSchemePreviewContainer', {
                onChange: (scheme) => {
                    console.log('Color scheme changed to:', scheme);
                },
                showDescription: true,
            });
        } catch (error) {
            console.error('Failed to initialize color scheme preview:', error);
        }
    },

    /**
     * Initialize FileUploader component
     */
    initFileUploader: function () {
        const self = this;
        this.fileUploader = new FileUploader({
            onFileSelected: function (fileData) {
                self.onFileSelected(fileData.fileId);
            },
            acceptedFormats: '.csv,.xlsx,.xls'
        });
    },

    /**
     * Bind event handlers
     */
    bindEvents: function () {
        const self = this;

        // Sample column selection
        document.getElementById('sampleColumnSelect').addEventListener('change', function () {
            self.onSampleColumnSelected(this.value);
        });

        // Analyze button
        document.getElementById('analyzeBtn').addEventListener('click', function () {
            self.runAnalysis();
        });

        // Sample chart selection
        document.getElementById('sampleChartSelect').addEventListener('change', function () {
            self.displaySampleChart(this.value);
        });

        // Copy table button
        document.getElementById('copyTableBtn').addEventListener('click', function () {
            self.copyTableToClipboard();
        });

        // Download chart buttons
        document.getElementById('downloadChartBtn').addEventListener('click', function () {
            self.downloadChart('sample');
        });

        document.getElementById('downloadDiffChartBtn').addEventListener('click', function () {
            self.downloadChart('diff');
        });

        // Listen for sample selection changes to update baseline select
        document.addEventListener('click', function (e) {
            if (e.target.classList.contains('sample-checkbox') || e.target.id === 'selectAllSamples') {
                // Delay to allow SampleSelector to update its state
                setTimeout(() => {
                    self.updateBaselineSelect();
                }, 50);
            }
        });
    },

    /**
     * Handle file selection
     */
    onFileSelected: async function (fileId) {
        this.currentFileId = fileId;

        const sampleColumnSelect = document.getElementById('sampleColumnSelect');
        const baselineSelect = document.getElementById('baselineSelect');
        const analyzeBtn = document.getElementById('analyzeBtn');
        const fieldMappingSection = document.getElementById('fieldMappingSection');

        if (!fileId) {
            sampleColumnSelect.disabled = true;
            sampleColumnSelect.innerHTML = '<option value="">-- Select sample column --</option>';
            baselineSelect.disabled = true;
            baselineSelect.innerHTML = '<option value="">-- No baseline --</option>';
            analyzeBtn.disabled = true;
            fieldMappingSection.classList.add('d-none');
            return;
        }

        try {
            const response = await fetch(`/api/files/${fileId}`);
            const data = await response.json();

            // Populate sample column select
            sampleColumnSelect.innerHTML = '<option value="">-- Select sample column --</option>';
            if (data.columns) {
                data.columns.forEach(col => {
                    const option = document.createElement('option');
                    option.value = col;
                    option.textContent = col;
                    // Auto-select if column name suggests it's a sample column
                    if (col.toLowerCase().includes('sample') || col.toLowerCase() === 'id') {
                        option.selected = true;
                    }
                    sampleColumnSelect.appendChild(option);
                });
            }
            sampleColumnSelect.disabled = false;

            // Initialize field mapping
            await this.initFieldMapping(data.columns);

            // Trigger sample column selection if auto-selected
            if (sampleColumnSelect.value) {
                this.onSampleColumnSelected(sampleColumnSelect.value);
            }

        } catch (error) {
            console.error('Error loading file details:', error);
            this.showError('加载文件详情失败');
        }
    },

    /**
     * Initialize field mapping for B细胞同型分析
     */
    initFieldMapping: async function (columns) {
        const fieldMappingSection = document.getElementById('fieldMappingSection');

        // Initialize FieldMapper with columns
        FieldMapper.init(columns);

        // Set analysis type to bcell_isotype
        FieldMapper.analysisType = 'bcell_isotype';

        try {
            // Load required fields
            await FieldMapper.loadRequiredFields();

            // Get mapping suggestions
            await FieldMapper.getSuggestions();

            // Show field mapping section
            fieldMappingSection.classList.remove('d-none');

        } catch (error) {
            console.error('Error initializing field mapping:', error);
            this.showError('无法初始化字段映射');
        }
    },

    /**
     * Handle sample column selection
     */
    onSampleColumnSelected: async function (columnName) {
        const baselineSelect = document.getElementById('baselineSelect');
        const analyzeBtn = document.getElementById('analyzeBtn');
        const sampleSelectionSection = document.getElementById('sampleSelectionSection');

        if (!columnName || !this.currentFileId) {
            baselineSelect.disabled = true;
            baselineSelect.innerHTML = '<option value="">-- 无基准 --</option>';
            analyzeBtn.disabled = true;
            sampleSelectionSection.classList.add('d-none');
            return;
        }

        try {
            // Initialize SampleSelector
            SampleSelector.init(this.currentFileId, columnName);

            // Load samples
            const success = await SampleSelector.loadSamples();

            if (!success) {
                this.showError('无法加载样本列表');
                return;
            }

            // Display samples using SampleSelector
            SampleSelector.displaySamples();

            // Show sample selection section
            sampleSelectionSection.classList.remove('d-none');

            // Populate baseline select with selected samples
            this.updateBaselineSelect();

            // Enable analyze button
            analyzeBtn.disabled = false;

        } catch (error) {
            console.error('Error loading column values:', error);
            this.showError('加载样本值失败');
        }
    },

    /**
     * Update baseline select with selected samples
     */
    updateBaselineSelect: function () {
        const baselineSelect = document.getElementById('baselineSelect');
        baselineSelect.innerHTML = '<option value="">-- 无基准 --</option>';

        // Get selected samples from SampleSelector
        const selectedSamples = SampleSelector.getSelectedSamples();

        // Only show selected samples in baseline dropdown
        selectedSamples.forEach(sample => {
            const option = document.createElement('option');
            option.value = sample;
            option.textContent = sample;
            baselineSelect.appendChild(option);
        });

        baselineSelect.disabled = false;
    },

    /**
     * Run the analysis
     */
    runAnalysis: async function () {
        const fileId = this.currentFileId;
        const sampleColumn = document.getElementById('sampleColumnSelect').value;
        const baselineSample = document.getElementById('baselineSelect').value || null;

        if (!fileId || !sampleColumn) {
            this.showError('请选择文件和样本列');
            return;
        }

        // Validate sample selection
        if (!SampleSelector.validate()) {
            this.showError('请至少选择一个样本进行分析');
            return;
        }

        const selectedSamples = SampleSelector.getSelectedSamples();

        // Get chart config
        const chartConfig = {
            title: document.getElementById('chartTitle').value || '',
            figsize: [
                parseInt(document.getElementById('chartWidth').value) || 16,
                parseInt(document.getElementById('chartHeight').value) || 8
            ],
            dpi: 300,
            font_size: 12,
            show_values: document.getElementById('showValues').checked
        };

        // Show loading state
        const analyzeBtn = document.getElementById('analyzeBtn');
        const loadingSpinner = document.getElementById('loadingSpinner');
        analyzeBtn.disabled = true;
        loadingSpinner.classList.remove('d-none');

        try {
            const response = await fetch('/api/analysis/bcell-isotype', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_id: fileId,
                    sample_column: sampleColumn,
                    selected_samples: selectedSamples,
                    baseline_sample: baselineSample,
                    chart_config: chartConfig
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || 'Analysis failed');
            }

            const results = await response.json();
            this.analysisResults = results;
            this.charts = results.charts || {};

            // Display results
            this.displayResults(results);

        } catch (error) {
            console.error('Error running analysis:', error);
            this.showError(error.message || '分析失败');
        } finally {
            analyzeBtn.disabled = false;
            loadingSpinner.classList.add('d-none');
        }
    },

    /**
     * Display analysis results
     */
    displayResults: function (results) {
        const resultsSection = document.getElementById('resultsSection');
        resultsSection.classList.remove('d-none');

        // Populate sample chart selector
        const sampleChartSelect = document.getElementById('sampleChartSelect');
        sampleChartSelect.innerHTML = '<option value="">-- Select a sample --</option>';

        if (results.samples) {
            results.samples.forEach(sample => {
                const option = document.createElement('option');
                option.value = sample;
                option.textContent = sample;
                sampleChartSelect.appendChild(option);
            });

            // Auto-select first sample
            if (results.samples.length > 0) {
                sampleChartSelect.value = results.samples[0];
                this.displaySampleChart(results.samples[0]);
            }
        }

        // Display percentage diff chart if available
        const diffChartSection = document.getElementById('diffChartSection');
        if (results.charts && results.charts.percentage_diff) {
            diffChartSection.classList.remove('d-none');
            const diffChartContainer = document.getElementById('diffChartContainer');
            diffChartContainer.innerHTML = `<img src="data:image/png;base64,${results.charts.percentage_diff}" alt="Percentage Difference Chart">`;
        } else {
            diffChartSection.classList.add('d-none');
        }

        // Display data table
        this.displayDataTable(results.table_data);
    },

    /**
     * Display chart for a specific sample
     */
    displaySampleChart: function (sampleName) {
        const chartContainer = document.getElementById('chartContainer');
        const downloadBtn = document.getElementById('downloadChartBtn');

        if (!sampleName) {
            chartContainer.innerHTML = '<p class="text-muted">Select a sample to view the chart</p>';
            downloadBtn.disabled = true;
            return;
        }

        const chartKey = `isotype_${sampleName}`;
        if (this.charts && this.charts[chartKey]) {
            chartContainer.innerHTML = `<img src="data:image/png;base64,${this.charts[chartKey]}" alt="Isotype Distribution - ${sampleName}">`;
            downloadBtn.disabled = false;
        } else {
            chartContainer.innerHTML = '<p class="text-muted">No chart available for this sample</p>';
            downloadBtn.disabled = true;
        }
    },

    /**
     * Display data table
     */
    displayDataTable: function (tableData) {
        if (!tableData) return;

        const table = document.getElementById('dataTable');
        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');

        // Clear existing content
        thead.innerHTML = '';
        tbody.innerHTML = '';

        // Create header row
        if (tableData.headers) {
            const headerRow = document.createElement('tr');
            tableData.headers.forEach(header => {
                const th = document.createElement('th');
                th.textContent = header;
                headerRow.appendChild(th);
            });
            thead.appendChild(headerRow);
        }

        // Create data rows
        if (tableData.rows) {
            tableData.rows.forEach(row => {
                const tr = document.createElement('tr');
                row.forEach((cell, index) => {
                    const td = document.createElement('td');
                    td.textContent = cell;

                    // Style percentage diff cells
                    if (typeof cell === 'string' && cell.includes('%')) {
                        if (cell.startsWith('+')) {
                            td.classList.add('value-positive');
                        } else if (cell.startsWith('-')) {
                            td.classList.add('value-negative');
                        }
                    }

                    tr.appendChild(td);
                });
                tbody.appendChild(tr);
            });
        }
    },

    /**
     * Copy table to clipboard
     */
    copyTableToClipboard: function () {
        if (!this.analysisResults || !this.analysisResults.table_data) {
            this.showError('No data to copy');
            return;
        }

        const tabSeparated = this.analysisResults.table_data.tab_separated;

        navigator.clipboard.writeText(tabSeparated).then(() => {
            this.showToast('表格已复制到剪贴板！');
        }).catch(err => {
            console.error('Failed to copy:', err);
            this.showError('复制到剪贴板失败');
        });
    },

    /**
     * Download chart as PNG
     */
    downloadChart: function (type) {
        let imageData, filename;

        if (type === 'sample') {
            const sampleName = document.getElementById('sampleChartSelect').value;
            const chartKey = `isotype_${sampleName}`;
            if (this.charts && this.charts[chartKey]) {
                imageData = this.charts[chartKey];
                filename = `bcell_isotype_${sampleName}.png`;
            }
        } else if (type === 'diff') {
            if (this.charts && this.charts.percentage_diff) {
                imageData = this.charts.percentage_diff;
                filename = 'bcell_isotype_percentage_diff.png';
            }
        }

        if (!imageData) {
            this.showError('No chart to download');
            return;
        }

        // Create download link
        const link = document.createElement('a');
        link.href = `data:image/png;base64,${imageData}`;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    },

    /**
     * Show error message
     */
    showError: function (message) {
        alert(message);
    },

    /**
     * Show toast notification
     */
    showToast: function (message) {
        const toast = document.createElement('div');
        toast.className = 'copy-toast';
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 2000);
    }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function () {
    BcellIsotypeModule.init();
});
