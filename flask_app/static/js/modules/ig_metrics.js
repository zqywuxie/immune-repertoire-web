/**
 * IG Metrics Analysis Module
 * Handles IG metrics analysis UI interactions
 */

const IGMetricsModule = {
    // State
    currentFileId: null,
    analysisResults: null,
    charts: {},
    fileUploader: null,
    colorSchemePreview: null,

    // Chain and metric lists
    chains: ["IGH", "IGK", "IGL"],
    metrics: ["Reads", "UCDR3", "D50", "Gini_index", "Shannon"],
    metricDisplayNames: {
        "Reads": "Reads",
        "UCDR3": "Unique CDR3",
        "D50": "D50 Index",
        "Gini_index": "Gini Index",
        "Shannon": "Shannon Entropy"
    },

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

        // Metric chart selection
        document.getElementById('metricChartSelect').addEventListener('change', function () {
            self.displayMetricChart(this.value);
        });

        // Copy table button
        document.getElementById('copyTableBtn').addEventListener('click', function () {
            self.copyTableToClipboard();
        });

        // Download chart buttons
        document.getElementById('downloadChartBtn').addEventListener('click', function () {
            self.downloadChart('metric');
        });

        document.getElementById('downloadPctChangeChartBtn').addEventListener('click', function () {
            self.downloadChart('pctChange');
        });

        document.getElementById('downloadOverviewChartBtn').addEventListener('click', function () {
            self.downloadChart('overview');
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
     * Initialize field mapping for IG指标分析
     */
    initFieldMapping: async function (columns) {
        const fieldMappingSection = document.getElementById('fieldMappingSection');

        // Initialize FieldMapper with columns
        FieldMapper.init(columns);

        // Set analysis type to ig_metrics
        FieldMapper.analysisType = 'ig_metrics';

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
     * Get selected chains
     */
    getSelectedChains: function () {
        const chains = [];
        if (document.getElementById('chainIGH').checked) chains.push('IGH');
        if (document.getElementById('chainIGK').checked) chains.push('IGK');
        if (document.getElementById('chainIGL').checked) chains.push('IGL');
        return chains;
    },

    /**
     * Get selected metrics
     */
    getSelectedMetrics: function () {
        const metrics = [];
        if (document.getElementById('metricReads').checked) metrics.push('Reads');
        if (document.getElementById('metricUCDR3').checked) metrics.push('UCDR3');
        if (document.getElementById('metricD50').checked) metrics.push('D50');
        if (document.getElementById('metricGini').checked) metrics.push('Gini_index');
        if (document.getElementById('metricShannon').checked) metrics.push('Shannon');
        return metrics;
    },

    /**
     * Run the analysis
     */
    runAnalysis: async function () {
        const fileId = this.currentFileId;
        const sampleColumn = document.getElementById('sampleColumnSelect').value;
        const baselineSample = document.getElementById('baselineSelect').value || null;
        const chains = this.getSelectedChains();
        const metrics = this.getSelectedMetrics();

        if (!fileId || !sampleColumn) {
            this.showError('请选择文件和样本列');
            return;
        }

        if (chains.length === 0) {
            this.showError('请至少选择一个链');
            return;
        }

        if (metrics.length === 0) {
            this.showError('请至少选择一个指标');
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
            bar_width: 0.25
        };

        // Show loading state
        const analyzeBtn = document.getElementById('analyzeBtn');
        const loadingSpinner = document.getElementById('loadingSpinner');
        analyzeBtn.disabled = true;
        loadingSpinner.classList.remove('d-none');

        try {
            const response = await fetch('/api/analysis/ig-metrics', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_id: fileId,
                    sample_column: sampleColumn,
                    selected_samples: selectedSamples,
                    chains: chains,
                    metrics: metrics,
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

        // Populate metric chart selector
        const metricChartSelect = document.getElementById('metricChartSelect');
        metricChartSelect.innerHTML = '<option value="">-- Select a metric --</option>';

        if (results.metrics) {
            results.metrics.forEach(metric => {
                const option = document.createElement('option');
                option.value = metric;
                option.textContent = this.metricDisplayNames[metric] || metric;
                metricChartSelect.appendChild(option);
            });

            // Auto-select first metric
            if (results.metrics.length > 0) {
                metricChartSelect.value = results.metrics[0];
                this.displayMetricChart(results.metrics[0]);
            }
        }

        // Display percentage change chart if available
        const pctChangeChartSection = document.getElementById('pctChangeChartSection');
        if (results.charts && results.charts.percentage_change) {
            pctChangeChartSection.classList.remove('d-none');
            const pctChangeChartContainer = document.getElementById('pctChangeChartContainer');
            pctChangeChartContainer.innerHTML = `<img src="data:image/png;base64,${results.charts.percentage_change}" alt="Percentage Change Chart">`;
        } else {
            pctChangeChartSection.classList.add('d-none');
        }

        // Display overview chart
        const overviewChartContainer = document.getElementById('overviewChartContainer');
        if (results.charts && results.charts.overview) {
            overviewChartContainer.innerHTML = `<img src="data:image/png;base64,${results.charts.overview}" alt="Overview Chart">`;
        } else {
            overviewChartContainer.innerHTML = '<p class="text-muted">No overview chart available</p>';
        }

        // Display data table
        this.displayDataTable(results.table_data);
    },

    /**
     * Display chart for a specific metric
     */
    displayMetricChart: function (metricName) {
        const chartContainer = document.getElementById('chartContainer');
        const downloadBtn = document.getElementById('downloadChartBtn');

        if (!metricName) {
            chartContainer.innerHTML = '<p class="text-muted">Select a metric to view the chart</p>';
            downloadBtn.disabled = true;
            return;
        }

        const chartKey = `metric_${metricName}`;
        if (this.charts && this.charts[chartKey]) {
            chartContainer.innerHTML = `<img src="data:image/png;base64,${this.charts[chartKey]}" alt="${metricName} Comparison">`;
            downloadBtn.disabled = false;
        } else {
            chartContainer.innerHTML = '<p class="text-muted">No chart available for this metric</p>';
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

        if (type === 'metric') {
            const metricName = document.getElementById('metricChartSelect').value;
            const chartKey = `metric_${metricName}`;
            if (this.charts && this.charts[chartKey]) {
                imageData = this.charts[chartKey];
                filename = `ig_metrics_${metricName}.png`;
            }
        } else if (type === 'pctChange') {
            if (this.charts && this.charts.percentage_change) {
                imageData = this.charts.percentage_change;
                filename = 'ig_metrics_percentage_change.png';
            }
        } else if (type === 'overview') {
            if (this.charts && this.charts.overview) {
                imageData = this.charts.overview;
                filename = 'ig_metrics_overview.png';
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
    IGMetricsModule.init();
});
