/**
 * Analysis Executor Module
 * Handles analysis execution, progress tracking, and result display
 */

class AnalysisExecutor {
    constructor() {
        this.currentAnalysisId = null;
        this.isExecuting = false;
        this.progressCallback = null;
        this.resultCallback = null;
        this.errorCallback = null;
    }

    /**
     * Execute analysis with the given configuration
     * @param {Object} config - Analysis configuration
     * @param {string} config.file_id - The uploaded file ID
     * @param {string} config.mode - Analysis mode ('scheme' or 'custom')
     * @param {string} config.scheme_id - Scheme ID (for scheme mode)
     * @param {Array<string>} config.selected_fields - Selected fields (for custom mode)
     * @param {Object} config.field_mapping - Field mapping (for scheme mode)
     * @param {Object} config.parameters - Analysis parameters
     * @returns {Promise<Object>} Analysis result
     */
    async execute(config) {
        if (this.isExecuting) {
            throw new Error('分析正在执行中，请等待完成');
        }

        // Validate configuration
        const validation = this.validateConfig(config);
        if (!validation.isValid) {
            throw new Error(`配置无效: ${validation.errors.join(', ')}`);
        }

        this.isExecuting = true;
        this.currentAnalysisId = null;

        try {
            // Show progress
            this.updateProgress(0, '准备分析...');

            // Send analysis request
            const response = await fetch('/api/analysis/execute', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `分析请求失败: ${response.statusText}`);
            }

            this.updateProgress(50, '正在执行分析...');

            const result = await response.json();
            this.currentAnalysisId = result.analysis_id;

            this.updateProgress(100, '分析完成');

            // Trigger result callback
            if (this.resultCallback) {
                this.resultCallback(result);
            }

            return result;

        } catch (error) {
            console.error('Analysis execution error:', error);

            // Trigger error callback
            if (this.errorCallback) {
                this.errorCallback(error);
            }

            throw error;

        } finally {
            this.isExecuting = false;
        }
    }

    /**
     * Validate analysis configuration
     * @param {Object} config - Configuration to validate
     * @returns {Object} Validation result
     */
    validateConfig(config) {
        const errors = [];

        if (!config.file_id) {
            errors.push('缺少文件ID');
        }

        if (!config.mode || !['scheme', 'custom'].includes(config.mode)) {
            errors.push('无效的分析模式');
        }

        if (config.mode === 'scheme') {
            if (!config.scheme_id) {
                errors.push('方案模式需要提供scheme_id');
            }
        } else if (config.mode === 'custom') {
            if (!config.selected_fields || config.selected_fields.length === 0) {
                errors.push('自定义模式需要选择至少一个字段');
            }
        }

        return {
            isValid: errors.length === 0,
            errors: errors
        };
    }

    /**
     * Update progress
     * @param {number} percent - Progress percentage (0-100)
     * @param {string} message - Progress message
     */
    updateProgress(percent, message) {
        console.log(`Progress: ${percent}% - ${message}`);

        if (this.progressCallback) {
            this.progressCallback(percent, message);
        }
    }

    /**
     * Set progress callback
     * @param {Function} callback - Callback function(percent, message)
     */
    onProgress(callback) {
        this.progressCallback = callback;
    }

    /**
     * Set result callback
     * @param {Function} callback - Callback function(result)
     */
    onResult(callback) {
        this.resultCallback = callback;
    }

    /**
     * Set error callback
     * @param {Function} callback - Callback function(error)
     */
    onError(callback) {
        this.errorCallback = callback;
    }

    /**
     * Check if analysis is currently executing
     * @returns {boolean} True if executing
     */
    isRunning() {
        return this.isExecuting;
    }

    /**
     * Get current analysis ID
     * @returns {string|null} Analysis ID or null
     */
    getCurrentAnalysisId() {
        return this.currentAnalysisId;
    }

    /**
     * Display analysis results
     * @param {Object} result - Analysis result object
     * @param {HTMLElement} container - Container element for results
     */
    displayResults(result, container) {
        if (!container) {
            console.error('Container element not provided');
            return;
        }

        // Use the AnalysisResultsComponent if available
        if (typeof analysisResultsComponent !== 'undefined') {
            analysisResultsComponent.displayResults(result);
        } else {
            // Fallback to basic display
            this.displayResultsBasic(result, container);
        }
    }

    /**
     * Basic results display (fallback)
     * @param {Object} result - Analysis result object
     * @param {HTMLElement} container - Container element for results
     */
    displayResultsBasic(result, container) {
        container.innerHTML = '';

        // Create result header
        const header = this.createResultHeader(result);
        container.appendChild(header);

        // Display charts
        if (result.results && result.results.charts) {
            const chartsSection = this.createChartsSection(result.results.charts);
            container.appendChild(chartsSection);
        }

        // Display tables
        if (result.results && result.results.tables) {
            const tablesSection = this.createTablesSection(result.results.tables);
            container.appendChild(tablesSection);
        }

        // Display statistics
        if (result.results && result.results.statistics) {
            const statsSection = this.createStatisticsSection(result.results.statistics);
            container.appendChild(statsSection);
        }

        // Add download button
        const downloadBtn = this.createDownloadButton(result);
        container.appendChild(downloadBtn);
    }

    /**
     * Create result header
     * @param {Object} result - Analysis result
     * @returns {HTMLElement} Header element
     */
    createResultHeader(result) {
        const header = document.createElement('div');
        header.className = 'alert alert-success mb-4';
        header.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <h5 class="alert-heading mb-1">
                        <i class="bi bi-check-circle me-2"></i>
                        分析完成
                    </h5>
                    <p class="mb-0 small">
                        分析ID: <code>${result.analysis_id || 'N/A'}</code>
                    </p>
                </div>
                <div class="text-end">
                    <span class="badge bg-success">成功</span>
                </div>
            </div>
        `;
        return header;
    }

    /**
     * Create charts section
     * @param {Array} charts - Array of chart data
     * @returns {HTMLElement} Charts section element
     */
    createChartsSection(charts) {
        const section = document.createElement('div');
        section.className = 'mb-4';

        const title = document.createElement('h5');
        title.className = 'mb-3';
        title.innerHTML = '<i class="bi bi-bar-chart me-2"></i>图表';
        section.appendChild(title);

        const row = document.createElement('div');
        row.className = 'row';

        charts.forEach((chart, index) => {
            const col = document.createElement('div');
            col.className = 'col-md-6 mb-3';

            const card = document.createElement('div');
            card.className = 'card';
            card.innerHTML = `
                <div class="card-body">
                    <h6 class="card-title">${this.escapeHtml(chart.title || `图表 ${index + 1}`)}</h6>
                    <div class="chart-placeholder" style="height: 300px; background: #f8f9fa; display: flex; align-items: center; justify-content: center;">
                        <span class="text-muted">图表将在此处显示</span>
                    </div>
                </div>
            `;

            col.appendChild(card);
            row.appendChild(col);
        });

        section.appendChild(row);
        return section;
    }

    /**
     * Create tables section
     * @param {Array} tables - Array of table data
     * @returns {HTMLElement} Tables section element
     */
    createTablesSection(tables) {
        const section = document.createElement('div');
        section.className = 'mb-4';

        const title = document.createElement('h5');
        title.className = 'mb-3';
        title.innerHTML = '<i class="bi bi-table me-2"></i>数据表';
        section.appendChild(title);

        tables.forEach((table, index) => {
            const card = document.createElement('div');
            card.className = 'card mb-3';
            card.innerHTML = `
                <div class="card-body">
                    <h6 class="card-title">${this.escapeHtml(table.title || `表格 ${index + 1}`)}</h6>
                    <div class="table-responsive">
                        <table class="table table-sm table-striped">
                            <thead>
                                <tr>
                                    ${table.columns ? table.columns.map(col => `<th>${this.escapeHtml(col)}</th>`).join('') : ''}
                                </tr>
                            </thead>
                            <tbody>
                                ${table.data ? table.data.slice(0, 10).map(row => `
                                    <tr>
                                        ${row.map(cell => `<td>${this.escapeHtml(String(cell))}</td>`).join('')}
                                    </tr>
                                `).join('') : ''}
                            </tbody>
                        </table>
                        ${table.data && table.data.length > 10 ? `<p class="text-muted small mb-0">显示前10行，共${table.data.length}行</p>` : ''}
                    </div>
                </div>
            `;
            section.appendChild(card);
        });

        return section;
    }

    /**
     * Create statistics section
     * @param {Object} statistics - Statistics data
     * @returns {HTMLElement} Statistics section element
     */
    createStatisticsSection(statistics) {
        const section = document.createElement('div');
        section.className = 'mb-4';

        const title = document.createElement('h5');
        title.className = 'mb-3';
        title.innerHTML = '<i class="bi bi-graph-up me-2"></i>统计信息';
        section.appendChild(title);

        const card = document.createElement('div');
        card.className = 'card';

        const cardBody = document.createElement('div');
        cardBody.className = 'card-body';

        const row = document.createElement('div');
        row.className = 'row';

        Object.entries(statistics).forEach(([key, value]) => {
            const col = document.createElement('div');
            col.className = 'col-md-3 mb-2';
            col.innerHTML = `
                <div class="text-center p-3 bg-light rounded">
                    <div class="h4 mb-1">${this.escapeHtml(String(value))}</div>
                    <div class="small text-muted">${this.escapeHtml(key)}</div>
                </div>
            `;
            row.appendChild(col);
        });

        cardBody.appendChild(row);
        card.appendChild(cardBody);
        section.appendChild(card);

        return section;
    }

    /**
     * Create download button
     * @param {Object} result - Analysis result
     * @returns {HTMLElement} Download button element
     */
    createDownloadButton(result) {
        const div = document.createElement('div');
        div.className = 'text-center mt-4';

        const button = document.createElement('button');
        button.className = 'btn btn-primary';
        button.innerHTML = '<i class="bi bi-download me-2"></i>下载结果';
        button.addEventListener('click', () => {
            this.downloadResults(result);
        });

        div.appendChild(button);
        return div;
    }

    /**
     * Download analysis results
     * @param {Object} result - Analysis result
     */
    downloadResults(result) {
        const dataStr = JSON.stringify(result, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);

        const link = document.createElement('a');
        link.href = url;
        link.download = `analysis_${result.analysis_id || 'result'}.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        URL.revokeObjectURL(url);
    }

    /**
     * Show progress UI
     * @param {HTMLElement} container - Container element
     */
    showProgress(container) {
        if (!container) return;

        container.innerHTML = `
            <div class="text-center py-5">
                <div class="spinner-border text-primary mb-3" role="status">
                    <span class="visually-hidden">加载中...</span>
                </div>
                <h5 class="progress-message">正在执行分析...</h5>
                <div class="progress mt-3" style="max-width: 400px; margin: 0 auto;">
                    <div class="progress-bar progress-bar-striped progress-bar-animated" 
                         role="progressbar" 
                         style="width: 0%" 
                         id="analysisProgressBar">
                    </div>
                </div>
            </div>
        `;

        // Set up progress callback to update the UI
        this.onProgress((percent, message) => {
            const progressBar = document.getElementById('analysisProgressBar');
            const progressMessage = container.querySelector('.progress-message');

            if (progressBar) {
                progressBar.style.width = `${percent}%`;
                progressBar.setAttribute('aria-valuenow', percent);
            }

            if (progressMessage) {
                progressMessage.textContent = message;
            }
        });
    }

    /**
     * Show error UI
     * @param {HTMLElement} container - Container element
     * @param {Error} error - Error object
     */
    showError(container, error) {
        if (!container) return;

        container.innerHTML = `
            <div class="alert alert-danger">
                <h5 class="alert-heading">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    分析失败
                </h5>
                <p class="mb-0">${this.escapeHtml(error.message || '未知错误')}</p>
                <hr>
                <button class="btn btn-sm btn-outline-danger retry-btn">
                    <i class="bi bi-arrow-clockwise me-1"></i>
                    重试
                </button>
            </div>
        `;
    }

    /**
     * Escape HTML to prevent XSS
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = AnalysisExecutor;
}
