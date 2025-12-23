/**
 * Field Analyzer Module
 * 通用字段数据分析模块
 * Requirements: 6.2, 6.5
 */

const FieldAnalyzer = {
    // State
    currentFileId: null,
    numericFields: [],
    selectedFields: [],
    samples: [],
    sampleColumn: null,
    analysisResults: null,
    fileUploader: null,

    /**
     * Initialize the module
     */
    init: function () {
        // Initialize FileUploader
        this.fileUploader = new FileUploader({
            containerId: 'fileUploaderContainer',
            onFileSelected: (data) => this.onFileSelected(data),
            onUploadComplete: (data) => this.onFileSelected(data)
        });

        this.bindEvents();
    },

    /**
     * Bind event handlers
     */
    bindEvents: function () {
        // Sample column selection change
        document.getElementById('sampleColumnSelect').addEventListener('change', (e) => {
            this.onSampleColumnSelect(e.target.value);
        });

        // Field selection events
        document.getElementById('selectAllBtn').addEventListener('click', () => {
            this.selectAllFields();
        });

        document.getElementById('deselectAllBtn').addEventListener('click', () => {
            this.deselectAllFields();
        });

        // Analysis button
        document.getElementById('runAnalysisBtn').addEventListener('click', () => {
            this.runAnalysis();
        });
    },

    /**
     * Handle file selection from FileUploader
     */
    onFileSelected: function (data) {
        this.currentFileId = data.fileId;

        // Show file info
        const fileInfo = document.getElementById('fileInfo');
        const fileInfoText = document.getElementById('fileInfoText');
        fileInfo.classList.remove('d-none');
        fileInfoText.textContent = `已选择文件: ${data.fileName}`;

        // Load file columns
        this.loadFileColumns(data.fileId);
    },

    /**
     * Load file columns from server
     */
    loadFileColumns: async function (fileId) {
        try {
            const response = await fetch(`/api/files/${fileId}`);
            const data = await response.json();

            if (data.columns) {
                // Populate sample column select
                const sampleSelect = document.getElementById('sampleColumnSelect');
                sampleSelect.innerHTML = '<option value="">-- 选择样本列 --</option>';

                data.columns.forEach(col => {
                    const option = document.createElement('option');
                    option.value = col;
                    option.textContent = col;
                    sampleSelect.appendChild(option);
                });

                // Show sample column card
                document.getElementById('sampleColumnCard').style.display = 'block';
            }
        } catch (error) {
            console.error('Error loading file columns:', error);
            this.showNotification('加载文件列失败', 'error');
        }
    },

    /**
     * Handle sample column selection
     */
    onSampleColumnSelect: async function (columnName) {
        if (!columnName) {
            this.resetSampleSelection();
            return;
        }

        this.sampleColumn = columnName;

        try {
            // Get samples for the selected column
            const response = await fetch(`/api/analysis/samples/${this.currentFileId}?column=${columnName}`);
            const data = await response.json();

            if (data.samples) {
                this.samples = data.samples;
                this.showSampleSelector();
                this.loadNumericFields();
            }
        } catch (error) {
            console.error('Error loading samples:', error);
            this.showNotification('加载样本失败', 'error');
        }
    },

    /**
     * Load numeric fields for selection
     */
    loadNumericFields: async function () {
        try {
            const response = await fetch(`/api/analysis/fields/${this.currentFileId}`);
            const data = await response.json();

            this.numericFields = data.numeric_fields || [];
            this.renderFieldSelection();

            // Show field selection card
            document.getElementById('fieldSelectionCard').style.display = 'block';
        } catch (error) {
            console.error('Error loading numeric fields:', error);
            this.showNotification('加载字段失败', 'error');
        }
    },

    /**
     * Render field selection checkboxes
     */
    renderFieldSelection: function () {
        const container = document.getElementById('fieldListContainer');

        if (!container) return;

        if (this.numericFields.length === 0) {
            container.innerHTML = '<div class="text-muted small text-center py-3">没有可用的数值字段</div>';
            return;
        }

        container.innerHTML = '';
        this.numericFields.forEach(field => {
            const div = document.createElement('div');
            div.className = 'form-check';
            div.innerHTML = `
                <input class="form-check-input" type="checkbox" value="${field}" id="field_${field}">
                <label class="form-check-label" for="field_${field}">${field}</label>
            `;

            div.querySelector('input').addEventListener('change', () => {
                this.updateSelectedFields();
            });

            container.appendChild(div);
        });
    },

    /**
     * Update selected fields list
     */
    updateSelectedFields: function () {
        const checkboxes = document.querySelectorAll('#fieldListContainer input[type="checkbox"]:checked');
        this.selectedFields = Array.from(checkboxes).map(cb => cb.value);

        // Update count
        const countElement = document.getElementById('selectedFieldCount');
        if (countElement) {
            countElement.textContent = this.selectedFields.length;
        }

        const infoElement = document.getElementById('selectedFieldsInfo');
        if (infoElement) {
            infoElement.classList.toggle('d-none', this.selectedFields.length === 0);
        }

        // Show/hide analysis sections
        const hasFields = this.selectedFields.length > 0;
        const cards = ['baselineCard', 'chartConfigCard', 'runAnalysisSection'];
        cards.forEach(cardId => {
            const card = document.getElementById(cardId);
            if (card) {
                card.style.display = hasFields ? 'block' : 'none';
            }
        });

        // Populate baseline select
        if (hasFields) {
            this.populateBaselineSelect();
        }
    },

    /**
     * Populate baseline select
     */
    populateBaselineSelect: function () {
        const select = document.getElementById('baselineSelect');
        if (!select) return;

        select.innerHTML = '<option value="">-- 不使用基准样本 --</option>';

        // Use selected samples if available, otherwise all samples
        const samplesToShow = this.samples.length > 0 ? this.samples : [];

        samplesToShow.forEach(sample => {
            const option = document.createElement('option');
            option.value = sample;
            option.textContent = sample;
            select.appendChild(option);
        });
    },

    /**
     * Show sample selector
     */
    showSampleSelector: function () {
        // Initialize SampleSelector if available
        if (window.SampleSelector) {
            SampleSelector.init(this.currentFileId, this.sampleColumn);
            SampleSelector.loadSamples().then(() => {
                SampleSelector.displaySamples();
            });
        }

        // Show field mapping status
        this.showFieldMappingStatus();
    },

    /**
     * Show field mapping status (display all mapped fields)
     */
    showFieldMappingStatus: function () {
        const fieldMappingSection = document.getElementById('fieldMappingSection');
        const mappingStatusText = document.getElementById('mappingStatusText');

        if (fieldMappingSection && mappingStatusText) {
            // Get all field mappings from FieldMapper module
            const mappings = window.FieldMapper ? window.FieldMapper.currentMapping : {};

            if (Object.keys(mappings).length > 0) {
                // Create a list of all mapped fields
                const mappingList = Object.entries(mappings)
                    .filter(([field, column]) => column) // Only show mapped fields
                    .map(([field, column]) => `${field} → ${column}`)
                    .join(', ');

                mappingStatusText.innerHTML = `
                    <strong>字段映射:</strong> ${mappingList}
                `;
            } else {
                mappingStatusText.textContent = '暂无字段映射';
            }

            fieldMappingSection.classList.remove('d-none');
        }
    },

    /**
     * Select all fields
     */
    selectAllFields: function () {
        document.querySelectorAll('#fieldListContainer input[type="checkbox"]').forEach(cb => {
            cb.checked = true;
        });
        this.updateSelectedFields();
    },

    /**
     * Deselect all fields
     */
    deselectAllFields: function () {
        document.querySelectorAll('#fieldListContainer input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
        });
        this.updateSelectedFields();
    },

    /**
     * Get chart configuration
     */
    getChartConfig: function () {
        return {
            plot_type: document.getElementById('plotType')?.value || 'bar',
            title: document.getElementById('chartTitle')?.value || '',
            figsize: [
                parseInt(document.getElementById('figureWidth')?.value) || 12,
                parseInt(document.getElementById('figureHeight')?.value) || 8
            ],
            color_scheme: document.getElementById('colorScheme')?.value || 'viridis',
            show_values: document.getElementById('showValues')?.checked !== false
        };
    },

    /**
     * Run analysis
     */
    runAnalysis: async function () {
        if (this.selectedFields.length === 0) {
            this.showNotification('请至少选择一个字段', 'warning');
            return;
        }

        if (!SampleSelector.validate()) {
            this.showNotification('请至少选择一个样本进行分析', 'warning');
            return;
        }

        const selectedSamples = SampleSelector.getSelectedSamples();

        // Show loading
        document.getElementById('loadingIndicator').classList.remove('d-none');
        document.getElementById('resultsSection').style.display = 'none';
        document.getElementById('emptyState').style.display = 'none';
        document.getElementById('runAnalysisBtn').disabled = true;

        try {
            const requestBody = {
                file_id: this.currentFileId,
                fields: this.selectedFields,
                sample_column: this.sampleColumn,
                selected_samples: selectedSamples,  // Include selected samples
                baseline_sample: document.getElementById('baselineSelect').value || null,
                plot_type: document.getElementById('plotType').value,
                chart_config: this.getChartConfig()
            };

            const response = await fetch('/api/analysis/field-data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || 'Analysis failed');
            }

            this.analysisResults = data;
            this.displayResults(data);

        } catch (error) {
            console.error('Error running analysis:', error);
            this.showNotification('分析失败: ' + error.message, 'error');
            document.getElementById('emptyState').style.display = 'flex';
        } finally {
            document.getElementById('loadingIndicator').classList.add('d-none');
            document.getElementById('runAnalysisBtn').disabled = false;
        }
    },

    /**
     * Display analysis results
     */
    displayResults: function (data) {
        // Display charts
        this.displayCharts(data.charts);

        // Display data table
        this.displayDataTable(data.table_data);

        // Show results section
        document.getElementById('resultsSection').style.display = 'block';

        this.showNotification('分析完成', 'success');
    },

    /**
     * Display charts
     */
    displayCharts: function (charts) {
        const container = document.getElementById('chartsContainer');
        container.innerHTML = '';

        if (!charts || Object.keys(charts).length === 0) {
            container.innerHTML = '<div class="text-muted">没有生成图表</div>';
            return;
        }

        Object.entries(charts).forEach(([name, base64Data]) => {
            if (name === 'error') {
                container.innerHTML += `<div class="alert alert-danger">${base64Data}</div>`;
                return;
            }

            const chartItem = document.createElement('div');
            chartItem.className = 'chart-item';
            chartItem.innerHTML = `
                <div class="chart-header">
                    <span>${this.formatChartName(name)}</span>
                    <button class="btn btn-outline-secondary btn-sm" onclick="FieldAnalyzer.downloadChart('${name}', '${base64Data}')">
                        <i class="bi bi-download"></i>
                    </button>
                </div>
                <div class="chart-body">
                    <img src="data:image/png;base64,${base64Data}" alt="${name}">
                </div>
            `;
            container.appendChild(chartItem);
        });
    },

    /**
     * Format chart name for display
     */
    formatChartName: function (name) {
        const nameMap = {
            'bar': '柱状图',
            'line_chart': '折线图',
            'grouped_bar': '分组柱状图',
            'percentage_diff': '百分比差异图'
        };

        // Check if name starts with known prefix
        for (const [key, value] of Object.entries(nameMap)) {
            if (name.startsWith(key)) {
                const suffix = name.replace(key + '_', '');
                return suffix ? `${value} - ${suffix}` : value;
            }
        }

        return name.replace(/_/g, ' ');
    },

    /**
     * Display data table
     */
    displayDataTable: function (tableData) {
        if (!tableData || !tableData.headers || !tableData.rows) {
            return;
        }

        // Build table header
        const thead = document.getElementById('dataTableHead');
        thead.innerHTML = '<tr>' + tableData.headers.map(h => `<th>${h}</th>`).join('') + '</tr>';

        // Build table body
        const tbody = document.getElementById('dataTableBody');
        tbody.innerHTML = '';

        tableData.rows.forEach(row => {
            const tr = document.createElement('tr');
            row.forEach((cell, index) => {
                const td = document.createElement('td');

                // Format percentage diff columns
                if (tableData.headers[index] && tableData.headers[index].endsWith('_Diff%')) {
                    if (cell !== '' && cell !== null) {
                        const value = parseFloat(cell);
                        if (value > 0) {
                            td.className = 'diff-positive';
                            td.textContent = '+' + value.toFixed(2) + '%';
                        } else if (value < 0) {
                            td.className = 'diff-negative';
                            td.textContent = value.toFixed(2) + '%';
                        } else {
                            td.className = 'diff-zero';
                            td.textContent = '0.00%';
                        }
                    } else {
                        td.textContent = '-';
                    }
                } else if (typeof cell === 'number') {
                    td.textContent = cell.toFixed(4);
                } else {
                    td.textContent = cell !== null && cell !== '' ? cell : '-';
                }

                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
    },

    /**
     * Copy table to clipboard
     * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
     */
    copyTableToClipboard: function () {
        if (!this.analysisResults || !this.analysisResults.table_data) {
            this.showNotification('没有可复制的数据', 'warning');
            return;
        }

        const tabSeparated = this.analysisResults.table_data.tab_separated;

        navigator.clipboard.writeText(tabSeparated).then(() => {
            this.showNotification('表格已复制到剪贴板', 'success');
        }).catch(err => {
            console.error('Failed to copy:', err);
            this.showNotification('复制失败', 'error');
        });
    },

    /**
     * Download a single chart
     */
    downloadChart: function (name, base64Data) {
        const link = document.createElement('a');
        link.href = 'data:image/png;base64,' + base64Data;
        link.download = `field_analysis_${name}.png`;
        link.click();
    },

    /**
     * Download all charts
     */
    downloadAllCharts: function () {
        if (!this.analysisResults || !this.analysisResults.charts) {
            this.showNotification('没有可下载的图表', 'warning');
            return;
        }

        Object.entries(this.analysisResults.charts).forEach(([name, base64Data]) => {
            if (name !== 'error') {
                this.downloadChart(name, base64Data);
            }
        });
    },

    /**
     * Reset state
     */
    resetState: function () {
        this.currentFileId = null;
        this.numericFields = [];
        this.selectedFields = [];
        this.samples = [];
        this.sampleColumn = null;
        this.analysisResults = null;

        // Hide cards
        document.getElementById('fileInfo').classList.add('d-none');
        document.getElementById('sampleColumnCard').style.display = 'none';
        document.getElementById('fieldSelectionCard').style.display = 'none';
        document.getElementById('baselineCard').style.display = 'none';
        document.getElementById('chartConfigCard').style.display = 'none';
        document.getElementById('runAnalysisSection').style.display = 'none';
        document.getElementById('resultsSection').style.display = 'none';
        document.getElementById('emptyState').style.display = 'flex';
    },

    /**
     * Show notification toast
     */
    showNotification: function (message, type = 'info') {
        const toast = document.getElementById('notificationToast');
        const toastBody = document.getElementById('toastBody');
        const toastIcon = document.getElementById('toastIcon');
        const toastTitle = document.getElementById('toastTitle');

        toastBody.textContent = message;

        // Set icon and title based on type
        const typeConfig = {
            success: { icon: 'bi-check-circle-fill text-success', title: '成功' },
            error: { icon: 'bi-x-circle-fill text-danger', title: '错误' },
            warning: { icon: 'bi-exclamation-triangle-fill text-warning', title: '警告' },
            info: { icon: 'bi-info-circle-fill text-info', title: '提示' }
        };

        const config = typeConfig[type] || typeConfig.info;
        toastIcon.className = 'bi me-2 ' + config.icon;
        toastTitle.textContent = config.title;

        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();
    },

    /**
     * Show field mapping status (display all mapped fields)
     */
    showFieldMappingStatus: function () {
        const fieldMappingSection = document.getElementById('fieldMappingSection');
        const mappingStatusText = document.getElementById('mappingStatusText');

        if (fieldMappingSection && mappingStatusText) {
            // Get all field mappings from FieldMapper module
            const mappings = window.FieldMapper ? window.FieldMapper.currentMapping : {};

            if (Object.keys(mappings).length > 0) {
                // Create a list of all mapped fields
                const mappingList = Object.entries(mappings)
                    .filter(([field, column]) => column) // Only show mapped fields
                    .map(([field, column]) => `${field} → ${column}`)
                    .join(', ');

                mappingStatusText.innerHTML = `
                    <strong>字段映射:</strong> ${mappingList}
                `;
            } else {
                mappingStatusText.textContent = '暂无字段映射';
            }

            fieldMappingSection.classList.remove('d-none');
        }
    }
};
