/**
 * History Management Module
 * Handles analysis history viewing, filtering, and management
 */
const HistoryManager = {
    historyTable: null,
    deleteAnalysisId: null,
    selectedIds: new Set(),

    init() {
        this.bindEvents();
        this.loadHistory();
        this.loadStats();
    },

    bindEvents() {
        // Bind filter events
        const statusFilter = document.getElementById('statusFilter');
        const typeFilter = document.getElementById('typeFilter');
        const refreshBtn = document.querySelector('[onclick="loadHistory()"]');

        if (statusFilter) {
            statusFilter.removeAttribute('onclick');
            statusFilter.addEventListener('change', () => this.loadHistory());
        }

        if (typeFilter) {
            typeFilter.removeAttribute('onclick');
            typeFilter.addEventListener('change', () => this.loadHistory());
        }

        if (refreshBtn) {
            refreshBtn.removeAttribute('onclick');
            refreshBtn.addEventListener('click', () => {
                this.loadHistory();
                this.loadStats();
            });
        }

        // Bind delete confirmation
        const confirmDeleteBtn = document.querySelector('[onclick="confirmDelete()"]');
        if (confirmDeleteBtn) {
            confirmDeleteBtn.removeAttribute('onclick');
            confirmDeleteBtn.addEventListener('click', () => this.confirmDelete());
        }

        // Bind select all checkbox
        const selectAllCheckbox = document.getElementById('selectAll');
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', (e) => this.toggleSelectAll(e.target.checked));
        }

        // Bind batch delete button
        const batchDeleteBtn = document.getElementById('batchDeleteBtn');
        if (batchDeleteBtn) {
            batchDeleteBtn.addEventListener('click', () => this.showBatchDeleteModal());
        }

        // Bind confirm delete button
        const confirmDeleteBtnEl = document.getElementById('confirmDeleteBtn');
        if (confirmDeleteBtnEl) {
            confirmDeleteBtnEl.addEventListener('click', () => this.confirmDelete());
        }
    },

    toggleSelectAll(checked) {
        const checkboxes = document.querySelectorAll('.row-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = checked;
            const id = cb.dataset.id;
            if (checked) {
                this.selectedIds.add(id);
            } else {
                this.selectedIds.delete(id);
            }
        });
        this.updateBatchDeleteButton();
    },

    toggleRowSelection(id, checked) {
        if (checked) {
            this.selectedIds.add(id);
        } else {
            this.selectedIds.delete(id);
        }
        this.updateBatchDeleteButton();

        // Update select all checkbox state
        const allCheckboxes = document.querySelectorAll('.row-checkbox');
        const selectAllCheckbox = document.getElementById('selectAll');
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = allCheckboxes.length > 0 &&
                Array.from(allCheckboxes).every(cb => cb.checked);
        }
    },

    updateBatchDeleteButton() {
        const btn = document.getElementById('batchDeleteBtn');
        const countSpan = document.getElementById('selectedCount');
        if (btn && countSpan) {
            const count = this.selectedIds.size;
            countSpan.textContent = count;
            btn.style.display = count > 0 ? 'inline-block' : 'none';
        }
    },

    showBatchDeleteModal() {
        if (this.selectedIds.size === 0) return;

        const modalBody = document.querySelector('#deleteModal .modal-body p');
        if (modalBody) {
            modalBody.textContent = `确定要删除选中的 ${this.selectedIds.size} 条分析记录吗？此操作将同时删除所有相关的结果文件，且无法恢复。`;
        }

        this.deleteAnalysisId = 'batch';
        const modal = new bootstrap.Modal(document.getElementById('deleteModal'));
        modal.show();
    },

    async loadHistory() {
        this.showLoading();

        try {
            const statusFilter = document.getElementById('statusFilter')?.value || '';
            const typeFilter = document.getElementById('typeFilter')?.value || '';

            const params = new URLSearchParams();
            if (statusFilter) params.append('status', statusFilter);
            if (typeFilter) params.append('type', typeFilter);

            const response = await fetch(`/api/history?${params}`);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || 'Failed to load history');
            }

            this.renderHistoryTable(data.items);
            this.updateStats(data.stats);

        } catch (error) {
            console.error('Error loading history:', error);
            this.showError(error.message);
        }
    },

    async loadStats() {
        try {
            const response = await fetch('/api/history/stats');
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || 'Failed to load stats');
            }

            // API返回 {status_counts: {completed: N, ...}, type_counts: {...}}
            // 转换为前端期望的格式
            const stats = data.status_counts || {};
            this.updateStats(stats);

        } catch (error) {
            console.error('Error loading stats:', error);
        }
    },

    renderHistoryTable(items) {
        const container = document.getElementById('historyTableContainer');
        const noHistoryMessage = document.getElementById('noHistoryMessage');
        const loadingEl = document.getElementById('loadingIndicator');

        // Hide loading indicator
        if (loadingEl) loadingEl.style.display = 'none';

        if (!items || items.length === 0) {
            if (container) container.style.display = 'none';
            if (noHistoryMessage) noHistoryMessage.style.display = 'block';
            return;
        }

        if (container) container.style.display = 'block';
        if (noHistoryMessage) noHistoryMessage.style.display = 'none';

        // Render table rows directly
        const tbody = document.getElementById('historyTableBody');
        if (!tbody) return;

        tbody.innerHTML = '';
        const formattedData = this.formatHistoryData(items);

        formattedData.forEach(row => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><input type="checkbox" class="form-check-input row-checkbox" data-id="${row.id}" onchange="HistoryManager.toggleRowSelection('${row.id}', this.checked)"></td>
                <td>${row.type_text}</td>
                <td>${row.mode_badge}</td>
                <td>${row.analysis_description}</td>
                <td>${row.status_badge}</td>
                <td>${row.created_at}</td>
                <td>${row.completed_at}</td>
                <td>${row.actions}</td>
            `;
            tbody.appendChild(tr);
        });

        // Reset selection state
        this.selectedIds.clear();
        this.updateBatchDeleteButton();
        const selectAllCheckbox = document.getElementById('selectAll');
        if (selectAllCheckbox) selectAllCheckbox.checked = false;
    },

    formatHistoryData(items) {
        return items.map(item => {
            // Add error handling for missing fields
            const type = item.type || item.analysis_type || 'unknown';
            const status = item.status || 'unknown';

            // Handle completed field safely - check for both 'completed' and 'completed_at'
            const completedTime = item.completed_at || item.completed;

            // Format analysis description based on mode - Requirements: 10.2
            let analysisDescription = '';
            if (item.mode === 'scheme' && item.scheme_name) {
                analysisDescription = `方案: ${item.scheme_name}`;
            } else if (item.mode === 'custom' && item.selected_fields && item.selected_fields.length > 0) {
                const fieldCount = item.selected_fields.length;
                const fieldPreview = item.selected_fields.slice(0, 3).join(', ');
                analysisDescription = `自定义字段 (${fieldCount}个): ${fieldPreview}${fieldCount > 3 ? '...' : ''}`;
            } else {
                // Fallback for old records without mode
                analysisDescription = this.getTypeText(type);
            }

            return {
                id: item.id || '',
                type_text: this.getTypeText(type),
                mode_badge: this.getModeBadge(item.mode),
                analysis_description: analysisDescription,
                status_badge: this.getStatusBadge(status),
                created_at: this.formatDateTime(item.created_at),
                completed_at: completedTime ? this.formatDateTime(completedTime) : (status === 'completed' ? '-' : '进行中'),
                sample_count: item.sample_count || '-',
                description: this.truncateText(item.description, 50),
                actions: this.getActionButtons(item)
            };
        });
    },

    getTypeText(type) {
        const types = {
            'similarity_heatmap': '相似度热图',
            'sequencing_depth': '测序深度分析',
            'diversity_metrics': '多样性指标',
            'chain_specific': '链特异性分析',
            'bcell_isotype': 'B细胞同型分析',
            'shm_analysis': 'SHM分析',
            'ig_metrics': 'IG指标分析',
            'custom_field_analysis': '自定义字段分析',
            'unknown': '未知类型'
        };
        return types[type] || type;
    },

    getModeBadge(mode) {
        // Requirements: 10.2 - Distinguish between scheme and custom modes
        if (!mode) {
            return '<span class="badge bg-secondary">旧版</span>';
        }
        const badges = {
            'scheme': '<span class="badge bg-info">预设方案</span>',
            'custom': '<span class="badge bg-warning text-dark">自定义</span>'
        };
        return badges[mode] || '<span class="badge bg-secondary">未知</span>';
    },

    getStatusBadge(status) {
        const badges = {
            'completed': '<span class="badge bg-success">已完成</span>',
            'running': '<span class="badge bg-primary">运行中</span>',
            'pending': '<span class="badge bg-warning text-dark">等待中</span>',
            'failed': '<span class="badge bg-danger">失败</span>',
            'cancelled': '<span class="badge bg-secondary">已取消</span>'
        };
        return badges[status] || status;
    },

    getActionButtons(item) {
        let buttons = '';

        // Re-execute button - Requirements: 10.3
        if (item.status === 'completed' || item.status === 'failed') {
            buttons += `<button class="btn btn-sm btn-outline-primary me-1" onclick="HistoryManager.reExecuteAnalysis('${item.id}')" title="重新执行">
                <i class="bi bi-arrow-repeat"></i>
            </button>`;
        }

        if (item.status === 'completed' && item.result_file) {
            buttons += `<a href="/api/history/${item.id}/download" class="btn btn-sm btn-outline-success me-1" title="下载结果">
                <i class="bi bi-download"></i>
            </a>`;
        }

        if (item.status === 'completed' && item.result_file) {
            buttons += `<a href="/analysis/results/${item.id}" class="btn btn-sm btn-outline-info me-1" title="查看结果">
                <i class="bi bi-eye"></i>
            </a>`;
        }

        if (['completed', 'failed', 'cancelled'].includes(item.status)) {
            buttons += `<button class="btn btn-sm btn-outline-danger" onclick="HistoryManager.showDeleteModal('${item.id}')" title="删除">
                <i class="bi bi-trash"></i>
            </button>`;
        }

        return buttons || '-';
    },

    updateStats(stats) {
        // Handle undefined or null stats
        if (!stats) {
            stats = {};
        }
        const elements = {
            completedCount: stats.completed || 0,
            runningCount: stats.running || 0,
            pendingCount: stats.pending || 0,
            failedCount: stats.failed || 0
        };

        Object.entries(elements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) element.textContent = value;
        });
    },

    showLoading() {
        const loadingEl = document.getElementById('loadingIndicator');
        const tableEl = document.getElementById('historyTableContainer');
        const noHistoryEl = document.getElementById('noHistoryMessage');
        const errorEl = document.getElementById('errorMessage');

        if (loadingEl) loadingEl.style.display = 'block';
        if (tableEl) tableEl.style.display = 'none';
        if (noHistoryEl) noHistoryEl.style.display = 'none';
        if (errorEl) errorEl.style.display = 'none';
    },

    showError(message) {
        const loadingEl = document.getElementById('loadingIndicator');
        const tableEl = document.getElementById('historyTableContainer');
        const noHistoryEl = document.getElementById('noHistoryMessage');
        const errorEl = document.getElementById('errorMessage');
        const errorTextEl = document.getElementById('errorText');

        if (loadingEl) loadingEl.style.display = 'none';
        if (tableEl) tableEl.style.display = 'none';
        if (noHistoryEl) noHistoryEl.style.display = 'none';
        if (errorEl) errorEl.style.display = 'block';
        if (errorTextEl) errorTextEl.textContent = message;
    },

    showDeleteModal(analysisId) {
        this.deleteAnalysisId = analysisId;
        const modal = new bootstrap.Modal(document.getElementById('deleteModal'));
        modal.show();
    },

    async confirmDelete() {
        if (!this.deleteAnalysisId) return;

        const modal = bootstrap.Modal.getInstance(document.getElementById('deleteModal'));

        try {
            if (this.deleteAnalysisId === 'batch') {
                // Batch delete
                const ids = Array.from(this.selectedIds);
                for (const id of ids) {
                    const response = await fetch(`/api/history/${id}`, { method: 'DELETE' });
                    if (!response.ok) {
                        const data = await response.json();
                        console.error(`Failed to delete ${id}:`, data.message);
                    }
                }
                this.selectedIds.clear();
                this.updateBatchDeleteButton();
            } else {
                // Single delete
                const response = await fetch(`/api/history/${this.deleteAnalysisId}`, {
                    method: 'DELETE'
                });
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.message || 'Failed to delete history item');
                }
            }

            modal.hide();
            this.loadHistory();
            this.loadStats();

        } catch (error) {
            alert('删除失败: ' + error.message);
        }

        this.deleteAnalysisId = null;
    },

    async reExecuteAnalysis(analysisId) {
        // Requirements: 10.3 - Re-execute analysis with saved configuration
        try {
            // Fetch the analysis details
            const response = await fetch(`/api/history/${analysisId}`);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || 'Failed to load analysis details');
            }

            const analysis = data;

            // Build the URL with query parameters to pre-fill the analysis page
            const params = new URLSearchParams();
            params.append('file_id', analysis.file_id);

            if (analysis.mode) {
                params.append('mode', analysis.mode);
            }

            if (analysis.scheme_id) {
                params.append('scheme_id', analysis.scheme_id);
            }

            if (analysis.selected_fields && analysis.selected_fields.length > 0) {
                params.append('selected_fields', JSON.stringify(analysis.selected_fields));
            }

            if (analysis.field_mapping) {
                params.append('field_mapping', JSON.stringify(analysis.field_mapping));
            }

            if (analysis.parameters) {
                params.append('parameters', JSON.stringify(analysis.parameters));
            }

            // Redirect to unified analysis page with pre-filled configuration
            window.location.href = `/analysis?${params.toString()}`;

        } catch (error) {
            console.error('Error re-executing analysis:', error);
            alert('重新执行失败: ' + error.message);
        }
    },

    // Utility functions
    formatDateTime(isoString) {
        // Handle undefined, null, or empty string
        if (!isoString || isoString === '' || isoString === 'null' || isoString === 'undefined') {
            return '-';
        }

        try {
            const date = new Date(isoString);
            // Check if date is valid
            if (isNaN(date.getTime())) {
                return '-';
            }
            return date.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        } catch (error) {
            console.warn('Invalid date format:', isoString, error);
            return '-';
        }
    },

    truncateText(text, maxLength) {
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    },

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML.replace(/'/g, "\\'").replace(/"/g, '\\"');
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('historyTable') || document.querySelector('.history-page')) {
        HistoryManager.init();
    }
});

// Global functions for backward compatibility
window.loadHistory = () => HistoryManager.loadHistory();
window.loadStats = () => HistoryManager.loadStats();
window.confirmDelete = () => HistoryManager.confirmDelete();
