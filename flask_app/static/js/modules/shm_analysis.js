/**
 * SHM Analysis Module
 * Handles SHM (Somatic Hypermutation) analysis UI interactions
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
 */

const SHMAnalysisModule = {
    // State
    currentFileId: null,
    currentFileName: null,
    analysisResults: null,
    charts: {},
    fileUploader: null,
    colorSchemePreview: null,

    // Isotype labels
    isotopeLabels: ["IgA", "IgG1/2", "IgG3/4", "IgM/IgD", "IGH"],

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

        // Isotype chart selection
        document.getElementById('isotypeChartSelect').addEventListener('change', function () {
            self.displayIsotopeChart(this.value);
        });

        // Copy table button
        document.getElementById('copyTableBtn').addEventListener('click', function () {
            self.copyTableToClipboard();
        });

        // Download chart buttons
        document.getElementById('downloadChartBtn').addEventListener('click', function () {
            self.downloadChart('isotype');
        });

        document.getElementById('downloadOverviewBtn').addEventListener('click', function () {
            self.downloadChart('overview');
        });

        document.getElementById('downloadPctChangeBtn').addEventListener('click', function () {
            self.downloadChart('pctChange');
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
            sampleColumnSelect.innerHTML = '<option value="">-- 选择样本列 --</option>';
            baselineSelect.disabled = true;
            baselineSelect.innerHTML = '<option value="">-- 选择基准样本 --</option>';
            analyzeBtn.disabled = true;
            fieldMappingSection.classList.add('d-none');
            this.currentFileName = null;
            return;
        }

        // Show loading state
        sampleColumnSelect.disabled = true;
        sampleColumnSelect.innerHTML = '<option value="">加载中...</option>';

        try {
            const response = await fetch(`/api/files/${fileId}`);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            // Validate response data
            if (!data || !data.columns || !Array.isArray(data.columns)) {
                throw new Error('Invalid file data structure');
            }

            // Store file name for display (handle both 'name' and 'original_name' fields)
            this.currentFileName = data.name || data.original_name || '未知文件';

            // Populate sample column select
            sampleColumnSelect.innerHTML = '<option value="">-- 选择样本列 --</option>';
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
            sampleColumnSelect.disabled = false;

            // Initialize field mapping
            await this.initFieldMapping(data.columns);

            // Trigger sample column selection if auto-selected
            if (sampleColumnSelect.value) {
                this.onSampleColumnSelected(sampleColumnSelect.value);
            }

        } catch (error) {
            console.error('Error loading file details:', error);
            const errorMessage = error.message || '加载文件详情失败';
            this.showError(`无法加载文件详情: ${errorMessage}`);

            // Reset UI state on error
            sampleColumnSelect.disabled = true;
            sampleColumnSelect.innerHTML = '<option value="">-- 选择样本列 --</option>';
            baselineSelect.disabled = true;
            baselineSelect.innerHTML = '<option value="">-- 选择基准样本 --</option>';
            analyzeBtn.disabled = true;
            fieldMappingSection.classList.add('d-none');
            this.currentFileName = null;
        }
    },

    /**
     * Initialize field mapping for SHM分析
     */
    initFieldMapping: async function (columns) {
        const fieldMappingSection = document.getElementById('fieldMappingSection');

        // Initialize FieldMapper with columns
        FieldMapper.init(columns);

        // Set analysis type to shm_analysis
        FieldMapper.analysisType = 'shm_analysis';

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
            baselineSelect.innerHTML = '<option value="">-- 选择基准样本 --</option>';
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
        baselineSelect.innerHTML = '<option value="">-- 选择基准样本 --</option>';

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
                parseInt(document.getElementById('chartHeight').value) || 10
            ],
            dpi: 300,
            font_size: 12,
            show_values: document.getElementById('showValues').checked,
            shm0_color: document.getElementById('shm0Color').value || '#2E86AB',
            shm1_color: document.getElementById('shm1Color').value || '#A23B72',
            bar_width: 0.35
        };

        // Show loading state
        const analyzeBtn = document.getElementById('analyzeBtn');
        const loadingSpinner = document.getElementById('loadingSpinner');
        analyzeBtn.disabled = true;
        loadingSpinner.classList.remove('d-none');

        try {
            const response = await fetch('/api/analysis/shm', {
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

        // Populate isotype chart selector
        const isotypeChartSelect = document.getElementById('isotypeChartSelect');
        isotypeChartSelect.innerHTML = '<option value="">-- Select an isotype --</option>';

        if (results.isotype_labels) {
            results.isotype_labels.forEach(label => {
                const option = document.createElement('option');
                option.value = label;
                option.textContent = label;
                isotypeChartSelect.appendChild(option);
            });

            // Auto-select first isotype
            if (results.isotype_labels.length > 0) {
                isotypeChartSelect.value = results.isotype_labels[0];
                this.displayIsotopeChart(results.isotype_labels[0]);
            }
        }

        // Display overview chart
        const overviewChartContainer = document.getElementById('overviewChartContainer');
        if (results.charts && results.charts.overview) {
            overviewChartContainer.innerHTML = `<img src="data:image/png;base64,${results.charts.overview}" alt="SHM Overview">`;
        } else {
            overviewChartContainer.innerHTML = '<p class="text-muted">No overview chart available</p>';
        }

        // Display percentage change chart if available
        const pctChangeSection = document.getElementById('pctChangeSection');
        const pctChangeChartContainer = document.getElementById('pctChangeChartContainer');
        if (results.charts && results.charts.percentage_change) {
            pctChangeSection.classList.remove('d-none');
            pctChangeChartContainer.innerHTML = `<img src="data:image/png;base64,${results.charts.percentage_change}" alt="Percentage Change Chart">`;
        } else {
            pctChangeSection.classList.add('d-none');
        }

        // Display data table
        this.displayDataTable(results.table_data);
    },

    /**
     * Display chart for a specific isotype
     */
    displayIsotopeChart: function (isotopeLabel) {
        const chartContainer = document.getElementById('chartContainer');
        const downloadBtn = document.getElementById('downloadChartBtn');

        if (!isotopeLabel) {
            chartContainer.innerHTML = '<p class="text-muted">Select an isotype to view the chart</p>';
            downloadBtn.disabled = true;
            return;
        }

        // Convert label to chart key format (replace / with _)
        const chartKey = `shm_${isotopeLabel.replace('/', '_')}`;
        if (this.charts && this.charts[chartKey]) {
            chartContainer.innerHTML = `<img src="data:image/png;base64,${this.charts[chartKey]}" alt="SHM - ${isotopeLabel}">`;
            downloadBtn.disabled = false;
        } else {
            chartContainer.innerHTML = '<p class="text-muted">No chart available for this isotype</p>';
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

                    // Style percentage change cells
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

        if (type === 'isotype') {
            const isotopeLabel = document.getElementById('isotypeChartSelect').value;
            const chartKey = `shm_${isotopeLabel.replace('/', '_')}`;
            if (this.charts && this.charts[chartKey]) {
                imageData = this.charts[chartKey];
                filename = `shm_${isotopeLabel.replace('/', '_')}.png`;
            }
        } else if (type === 'overview') {
            if (this.charts && this.charts.overview) {
                imageData = this.charts.overview;
                filename = 'shm_overview.png';
            }
        } else if (type === 'pctChange') {
            if (this.charts && this.charts.percentage_change) {
                imageData = this.charts.percentage_change;
                filename = 'shm_percentage_change.png';
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
    SHMAnalysisModule.init();
});
