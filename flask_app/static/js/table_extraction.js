/**
 * Table Extraction Module
 * Handles PDF table extraction functionality
 */

class TableExtraction {
    constructor() {
        this.currentFileId = null;
        this.currentMethod = 'pdfplumber';
        this.selectedTable = null;
        this.tables = [];

        this.init();
    }

    init() {
        this.bindEvents();
        this.loadExistingPDFs();
    }

    bindEvents() {
        // PDF file input
        document.getElementById('pdfFileInput').addEventListener('change', (e) => {
            this.handleFileSelect(e.target.files[0]);
        });

        // Upload button
        document.getElementById('uploadPdfBtn').addEventListener('click', () => {
            this.uploadPDF();
        });

        // Existing PDF selection
        document.getElementById('pdfFileSelect').addEventListener('change', (e) => {
            if (e.target.value) {
                this.loadExistingPDF(e.target.value);
            }
        });

        // Extraction method selection
        document.querySelectorAll('.method-option').forEach(option => {
            option.addEventListener('click', (e) => {
                this.selectMethod(e.currentTarget.dataset.method);
            });
        });

        // Preview button
        document.getElementById('previewTableBtn').addEventListener('click', () => {
            this.previewTable();
        });

        // Export button
        document.getElementById('exportTableBtn').addEventListener('click', () => {
            this.exportTable();
        });

        // Use for analysis button
        document.getElementById('useForAnalysisBtn').addEventListener('click', () => {
            this.useForAnalysis();
        });
    }

    handleFileSelect(file) {
        if (!file) return;

        if (!file.name.toLowerCase().endsWith('.pdf')) {
            this.showError('请选择PDF文件');
            return;
        }

        // Display file info
        document.getElementById('pdfFileName').textContent = file.name;
        document.getElementById('pdfFileSize').textContent = this.formatFileSize(file.size);
        document.getElementById('pdfFileInfo').classList.remove('d-none');
    }

    async uploadPDF() {
        const fileInput = document.getElementById('pdfFileInput');
        const file = fileInput.files[0];

        if (!file) {
            this.showError('请先选择PDF文件');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);
        formData.append('method', this.currentMethod);

        try {
            this.showLoading('正在上传并检测表格...');

            const response = await fetch('/api/table-extraction/upload-pdf', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || '上传失败');
            }

            this.currentFileId = data.id;

            // Update UI
            document.getElementById('pdfTableCount').textContent = data.table_count;

            // Show method selection
            document.getElementById('methodCard').style.display = 'block';

            // Extract tables
            await this.extractTables();

            this.hideLoading();
            this.showSuccess('PDF上传成功，已检测到 ' + data.table_count + ' 个表格');

        } catch (error) {
            this.hideLoading();
            this.showError('上传失败: ' + error.message);
        }
    }

    async loadExistingPDFs() {
        try {
            // This would load PDFs from the file list
            // For now, we'll skip this as it requires backend support
        } catch (error) {
            console.error('Failed to load existing PDFs:', error);
        }
    }

    async loadExistingPDF(fileId) {
        this.currentFileId = fileId;
        await this.extractTables();
    }

    selectMethod(method) {
        this.currentMethod = method;

        // Update UI
        document.querySelectorAll('.method-option').forEach(option => {
            option.classList.remove('active');
        });
        document.querySelector(`[data-method="${method}"]`).classList.add('active');

        // Re-extract tables with new method
        if (this.currentFileId) {
            this.extractTables();
        }
    }

    async extractTables() {
        if (!this.currentFileId) return;

        try {
            this.showLoading('正在提取表格...');

            const response = await fetch('/api/table-extraction/extract', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_id: this.currentFileId,
                    method: this.currentMethod
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || '提取失败');
            }

            this.tables = data.tables;
            this.displayTables();

            this.hideLoading();

        } catch (error) {
            this.hideLoading();
            this.showError('提取表格失败: ' + error.message);
        }
    }

    displayTables() {
        const tableList = document.getElementById('tableList');
        tableList.innerHTML = '';

        if (this.tables.length === 0) {
            tableList.innerHTML = '<div class="alert alert-warning">未检测到表格</div>';
            return;
        }

        this.tables.forEach((table, index) => {
            const card = document.createElement('div');
            card.className = 'table-card card mb-2';
            card.dataset.index = index;

            card.innerHTML = `
                <div class="card-body py-2">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <strong>表格 ${index + 1}</strong>
                            <small class="text-muted ms-2">第 ${table.page} 页</small>
                        </div>
                        <div class="text-end">
                            <small class="text-muted">
                                ${table.row_count} 行 × ${table.col_count} 列
                            </small>
                        </div>
                    </div>
                </div>
            `;

            card.addEventListener('click', () => {
                this.selectTable(index);
            });

            tableList.appendChild(card);
        });

        // Show table selection card
        document.getElementById('tableSelectionCard').style.display = 'block';
        document.getElementById('actionCard').style.display = 'block';
    }

    selectTable(index) {
        this.selectedTable = this.tables[index];

        // Update UI
        document.querySelectorAll('.table-card').forEach(card => {
            card.classList.remove('selected');
        });
        document.querySelector(`[data-index="${index}"]`).classList.add('selected');
    }

    async previewTable() {
        if (!this.selectedTable) {
            this.showError('请先选择要预览的表格');
            return;
        }

        try {
            this.showLoading('正在加载预览...');

            const response = await fetch('/api/table-extraction/preview', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_id: this.currentFileId,
                    page: this.selectedTable.page,
                    table_index: this.selectedTable.table_index,
                    method: this.currentMethod,
                    max_rows: 10
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || '预览失败');
            }

            this.displayPreview(data);

            this.hideLoading();

        } catch (error) {
            this.hideLoading();
            this.showError('预览失败: ' + error.message);
        }
    }

    displayPreview(data) {
        const previewCard = document.getElementById('previewCard');
        const previewInfo = document.getElementById('previewInfo');
        const previewTableHead = document.getElementById('previewTableHead');
        const previewTableBody = document.getElementById('previewTableBody');

        // Update info
        previewInfo.textContent = `${data.showing_rows} / ${data.total_rows} 行`;

        // Build table header
        let headerHtml = '<tr>';
        data.columns.forEach(col => {
            headerHtml += `<th>${col}</th>`;
        });
        headerHtml += '</tr>';
        previewTableHead.innerHTML = headerHtml;

        // Build table body
        let bodyHtml = '';
        data.preview_data.forEach(row => {
            bodyHtml += '<tr>';
            data.columns.forEach(col => {
                bodyHtml += `<td>${row[col] || ''}</td>`;
            });
            bodyHtml += '</tr>';
        });
        previewTableBody.innerHTML = bodyHtml;

        // Show preview card
        previewCard.style.display = 'block';

        // Scroll to preview
        previewCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    async exportTable() {
        if (!this.selectedTable) {
            this.showError('请先选择要导出的表格');
            return;
        }

        try {
            this.showLoading('正在导出表格...');

            const response = await fetch('/api/table-extraction/export-csv', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_id: this.currentFileId,
                    page: this.selectedTable.page,
                    table_index: this.selectedTable.table_index,
                    method: this.currentMethod
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || '导出失败');
            }

            this.displayExportResult(data);

            this.hideLoading();
            this.showSuccess('表格导出成功');

        } catch (error) {
            this.hideLoading();
            this.showError('导出失败: ' + error.message);
        }
    }

    displayExportResult(data) {
        const resultCard = document.getElementById('resultCard');

        document.getElementById('resultFileName').textContent = data.filename;
        document.getElementById('resultRowCount').textContent = data.row_count;
        document.getElementById('resultColCount').textContent = data.col_count;

        const downloadLink = document.getElementById('downloadLink');
        downloadLink.href = data.download_url;

        // Store file ID for analysis
        downloadLink.dataset.fileId = data.file_id;

        resultCard.style.display = 'block';
        resultCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    useForAnalysis() {
        const downloadLink = document.getElementById('downloadLink');
        const fileId = downloadLink.dataset.fileId;

        if (!fileId) {
            this.showError('文件ID不可用');
            return;
        }

        // Redirect to field analysis page with the file
        window.location.href = `/analysis/field?file_id=${fileId}`;
    }

    formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    }

    showLoading(message) {
        // Simple loading indicator
        const loadingDiv = document.createElement('div');
        loadingDiv.id = 'loadingIndicator';
        loadingDiv.className = 'alert alert-info';
        loadingDiv.innerHTML = `
            <div class="d-flex align-items-center">
                <div class="spinner-border spinner-border-sm me-2" role="status">
                    <span class="visually-hidden">加载中...</span>
                </div>
                <span>${message}</span>
            </div>
        `;

        // Remove existing loading indicator
        const existing = document.getElementById('loadingIndicator');
        if (existing) existing.remove();

        // Add to top of content
        document.querySelector('.container-fluid').prepend(loadingDiv);
    }

    hideLoading() {
        const loadingDiv = document.getElementById('loadingIndicator');
        if (loadingDiv) loadingDiv.remove();
    }

    showError(message) {
        this.showAlert(message, 'danger');
    }

    showSuccess(message) {
        this.showAlert(message, 'success');
    }

    showAlert(message, type) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        document.querySelector('.container-fluid').prepend(alertDiv);

        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new TableExtraction();
});
