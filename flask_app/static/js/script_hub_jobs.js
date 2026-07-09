const ScriptHubJobsPage = {
    jobs: [],
    modules: {},
    selectedJobId: '',
    refreshTimer: null,

    init() {
        this.bindEvents();
        this.loadModules();
        this.loadJobs().catch((error) => {
            console.warn('Failed to load jobs:', error);
            this.showListError(error.message || '加载后台任务失败');
        });
        this.startAutoRefresh();
    },

    bindEvents() {
        document.getElementById('scriptJobRefreshBtn')?.addEventListener('click', () => this.loadJobs().catch((error) => {
            console.warn('Failed to refresh jobs:', error);
            this.showListError(error.message || '加载后台任务失败');
        }));
        document.getElementById('scriptJobStatusFilter')?.addEventListener('change', () => this.renderJobs());
        document.getElementById('scriptJobModuleFilter')?.addEventListener('change', () => this.renderJobs());
        document.getElementById('scriptJobSearchInput')?.addEventListener('input', () => this.renderJobs());
        document.getElementById('scriptJobAutoRefresh')?.addEventListener('change', () => this.startAutoRefresh());
        document.getElementById('scriptJobIncludeChildren')?.addEventListener('change', () => this.loadJobs());
        document.getElementById('scriptJobCancelBtn')?.addEventListener('click', () => this.cancelSelectedJob().catch((error) => {
            console.warn('Failed to cancel job:', error);
            this.showListError(error.message || '取消任务失败');
        }));
        document.getElementById('scriptJobDeleteBtn')?.addEventListener('click', () => this.deleteSelectedJob().catch((error) => {
            console.warn('Failed to delete job:', error);
            this.showListError(error.message || '删除任务失败');
        }));
        document.getElementById('scriptJobList')?.addEventListener('click', (event) => {
            const card = event.target.closest('[data-job-id]');
            if (card) this.selectJob(card.dataset.jobId || '');
        });
    },

    async fetchJson(url, options = {}) {
        const response = await fetch(url, options);
        const contentType = response.headers.get('content-type') || '';
        let data = null;
        if (contentType.includes('application/json')) {
            data = await response.json();
        } else {
            const text = await response.text();
            data = {
                success: false,
                message: text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 500)
                    || `HTTP ${response.status}`,
            };
        }
        if (!response.ok || data.success === false) {
            throw new Error(data.message || data.error || `HTTP ${response.status}`);
        }
        return data;
    },

    async loadModules() {
        try {
            const data = await this.fetchJson('/api/jobs/modules');
            const modules = Array.isArray(data.modules) ? data.modules : [];
            this.modules = modules.reduce((acc, item) => {
                acc[item.key] = item;
                return acc;
            }, {});
            const select = document.getElementById('scriptJobModuleFilter');
            if (select) {
                select.innerHTML = '<option value="">全部模块</option>' + modules.map((module) =>
                    `<option value="${this.escapeHtml(module.key)}">${this.escapeHtml(module.label || module.key)}</option>`
                ).join('');
            }
        } catch (error) {
            console.warn('Failed to load Script Hub modules:', error);
        }
    },

    async loadJobs() {
        const includeChildren = document.getElementById('scriptJobIncludeChildren')?.checked;
        const data = await this.fetchJson(`/api/jobs?limit=200${includeChildren ? '&include_children=1' : ''}`);
        this.jobs = Array.isArray(data.jobs) ? data.jobs : [];
        if (this.selectedJobId && !this.jobs.some((job) => String(job.job_id || job.task_id || '') === this.selectedJobId)) {
            this.selectedJobId = '';
        }
        if (!this.selectedJobId && this.jobs.length) this.selectedJobId = this.jobs[0].job_id;
        this.renderStats();
        this.renderJobs();
        this.renderSelectedJob();
    },

    startAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
        const enabled = document.getElementById('scriptJobAutoRefresh')?.checked;
        if (enabled) {
            this.refreshTimer = setInterval(() => this.loadJobs().catch((error) => {
                console.warn('Failed to refresh jobs:', error);
                this.showListError(error.message || '加载后台任务失败');
            }), 2500);
        }
    },

    showListError(message) {
        const list = document.getElementById('scriptJobList');
        if (!list) return;
        list.innerHTML = `<div class="alert alert-danger m-2">${this.escapeHtml(message || '加载后台任务失败')}</div>`;
    },

    getFilteredJobs() {
        const status = document.getElementById('scriptJobStatusFilter')?.value || '';
        const module = document.getElementById('scriptJobModuleFilter')?.value || '';
        const query = (document.getElementById('scriptJobSearchInput')?.value || '').trim().toLowerCase();
        return this.jobs.filter((job) => {
            if (status && job.status !== status) return false;
            const moduleName = job.module || job?.meta?.module || '';
            if (module && moduleName !== module) return false;
            if (!query) return true;
            const haystack = [
                job.job_id,
                job.task_id,
                moduleName,
                job.stage,
                job.detail,
                job.error,
                job.analysis_signature,
            ].join(' ').toLowerCase();
            return haystack.includes(query);
        });
    },

    renderJobs() {
        const list = document.getElementById('scriptJobList');
        const meta = document.getElementById('scriptJobListMeta');
        if (!list) return;
        const filtered = this.getFilteredJobs();
        if (meta) meta.textContent = `${filtered.length} / ${this.jobs.length} 个任务`;
        if (!filtered.length) {
            list.innerHTML = '<div class="sj-empty">暂无匹配任务。</div>';
            return;
        }
        list.innerHTML = filtered.map((job) => this.renderJobCard(job)).join('');
    },

    renderJobCard(job) {
        const jobId = String(job.job_id || job.task_id || '');
        const moduleName = job.module || job?.meta?.module || '';
        const label = this.getModuleLabel(moduleName);
        const status = job.status || 'queued';
        const progress = this.normalizeProgress(job.progress);
        const selected = this.selectedJobId === jobId;
        const isChild = Boolean(job.parent_job_id);
        const updated = this.formatDateTime(job.updated_at || job.created_at);
        const icon = this.getModuleIcon(moduleName);
        return `
            <button type="button" class="sj-job-card sj-job-card-${this.escapeHtml(status)} ${isChild ? 'is-child' : ''} ${selected ? 'is-selected' : ''}" data-job-id="${this.escapeHtml(jobId)}">
                <div class="sj-job-main">
                    <div class="sj-job-title">
                        <i class="bi ${icon}"></i>
                        <span>${this.escapeHtml(isChild ? (job.child_label || label) : label)}</span>
                        ${isChild ? '<em>子任务</em>' : ''}
                    </div>
                    <div class="sj-job-id">${this.escapeHtml(jobId || '-')}</div>
                    <div class="sj-job-detail">${this.escapeHtml(job.detail || job.stage || '-')}</div>
                    <div class="sj-job-time">${this.escapeHtml(updated || '')}</div>
                </div>
                <div class="sj-job-side">
                    <span class="sj-status sj-status-${this.escapeHtml(status)}">${this.escapeHtml(status)}</span>
                    <span class="sj-card-progress">${progress.toFixed(0)}%</span>
                </div>
                <div class="sj-card-bar"><span style="width:${progress}%"></span></div>
            </button>
        `;
    },

    selectJob(jobId) {
        this.selectedJobId = jobId;
        this.renderJobs();
        this.renderSelectedJob();
    },

    renderSelectedJob() {
        const job = this.jobs.find((item) => String(item.job_id || item.task_id || '') === this.selectedJobId);
        const empty = document.getElementById('scriptJobDetailEmpty');
        const body = document.getElementById('scriptJobDetailBody');
        const cancelBtn = document.getElementById('scriptJobCancelBtn');
        const deleteBtn = document.getElementById('scriptJobDeleteBtn');
        if (!job) {
            empty?.classList.remove('d-none');
            body?.classList.add('d-none');
            if (cancelBtn) cancelBtn.disabled = true;
            if (deleteBtn) deleteBtn.disabled = true;
            return;
        }

        empty?.classList.add('d-none');
        body?.classList.remove('d-none');
        const moduleName = job.module || job?.meta?.module || '';
        const progress = this.normalizeProgress(job.progress);
        this.setText('scriptJobDetailTitle', this.getModuleLabel(moduleName));
        const parentText = job.parent_job_id ? ` · 子任务 of ${job.parent_job_id}` : '';
        this.setText('scriptJobDetailMeta', `${job.job_id || job.task_id || '-'} · ${job.status || '-'}${parentText}`);
        this.setText('scriptJobStage', job.stage || job.status || '-');
        this.setText('scriptJobDetail', job.detail || job.error || '-');
        this.setText('scriptJobProgressValue', `${progress.toFixed(0)}%`);
        const bar = document.getElementById('scriptJobProgressBar');
        if (bar) {
            bar.style.width = `${progress}%`;
            bar.setAttribute('aria-valuenow', String(progress));
            bar.className = `progress-bar sj-progress-bar sj-progress-bar-${job.status || 'queued'}`;
        }
        if (cancelBtn) cancelBtn.disabled = this.isTerminal(job.status);
        if (deleteBtn) {
            deleteBtn.disabled = !this.isTerminal(job.status);
            deleteBtn.title = this.isTerminal(job.status) ? '删除这条任务记录' : '运行中或排队中的任务需要先取消';
        }
        this.renderActions(job);
        this.renderChildResults(job);
        this.renderHistory(job.history || []);
        this.setText('scriptJobJson', JSON.stringify(job, null, 2));
    },

    renderActions(job) {
        const container = document.getElementById('scriptJobResultActions');
        if (!container) return;
        const result = job.result || {};
        const links = [
            ['viewer_url', '打开 Viewer', 'bi-box-arrow-up-right'],
            ['zip_url', '下载 ZIP', 'bi-download'],
            ['metadata_url', 'Metadata', 'bi-filetype-json'],
            ['report_url', '报告', 'bi-file-earmark-richtext'],
        ].filter(([key]) => result[key]);

        if (!links.length) {
            container.innerHTML = '<span class="text-muted small">当前任务暂无可打开的结果文件。</span>';
            return;
        }
        container.innerHTML = links.map(([key, label, icon]) =>
            `<button type="button" class="btn btn-outline-primary btn-sm" data-result-url="${this.escapeHtml(result[key])}">
                <i class="bi ${icon} me-1"></i>${this.escapeHtml(label)}
            </button>`
        ).join('');
        container.querySelectorAll('[data-result-url]').forEach((button) => {
            button.addEventListener('click', () => {
                const url = button.getAttribute('data-result-url');
                if (url) window.open(url, '_blank');
            });
        });
    },

    renderChildResults(job) {
        const container = document.getElementById('scriptJobChildResults');
        if (!container) return;
        const result = job.result || {};
        const chartResults = Array.isArray(result.chart_results) ? result.chart_results : [];
        const childJobs = this.jobs.filter((item) => item.parent_job_id && item.parent_job_id === (job.job_id || job.task_id));
        const rows = chartResults.length ? chartResults : childJobs;
        if (!rows.length) {
            container.innerHTML = '';
            return;
        }
        container.innerHTML = `
            <div class="sj-section-title">子步骤</div>
            <div class="sj-child-grid">
                ${rows.map((item) => {
                    const status = item.status || 'completed';
                    const key = item.key || item.module || '';
                    const label = item.label || item.child_label || this.getModuleLabel(key);
                    const progress = this.normalizeProgress(item.progress ?? 100);
                    const viewerUrl = item.viewer_url || item.result?.viewer_url;
                    const zipUrl = item.zip_url || item.result?.zip_url;
                    return `<div class="sj-child-card">
                        <div class="sj-child-head">
                            <strong>${this.escapeHtml(label || key || '子步骤')}</strong>
                            <span class="sj-status sj-status-${this.escapeHtml(status)}">${this.escapeHtml(status)}</span>
                        </div>
                        <div class="sj-child-progress"><span style="width:${progress}%"></span></div>
                        <div class="sj-child-actions">
                            ${viewerUrl ? `<a class="btn btn-sm btn-outline-primary" href="${this.escapeHtml(viewerUrl)}" target="_blank" rel="noopener">Viewer</a>` : ''}
                            ${zipUrl ? `<a class="btn btn-sm btn-outline-primary" href="${this.escapeHtml(zipUrl)}">ZIP</a>` : ''}
                        </div>
                    </div>`;
                }).join('')}
            </div>
        `;
    },

    renderHistory(history) {
        const container = document.getElementById('scriptJobHistory');
        if (!container) return;
        if (!history.length) {
            container.innerHTML = '<div class="text-muted small">暂无历史记录。</div>';
            return;
        }
        container.innerHTML = history.slice().reverse().map((item) => `
            <div class="sj-history-item">
                <div class="sj-history-time">${this.escapeHtml(item.timestamp || '-')}</div>
                <div class="sj-history-main">
                    <strong>${this.escapeHtml(item.stage || '-')}</strong>
                    <span>${this.escapeHtml(item.detail || '')}</span>
                </div>
                <div class="sj-history-progress">${this.normalizeProgress(item.progress).toFixed(0)}%</div>
            </div>
        `).join('');
    },

    async cancelSelectedJob() {
        if (!this.selectedJobId) return;
        await this.fetchJson(`/api/jobs/${encodeURIComponent(this.selectedJobId)}/cancel`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        await this.loadJobs();
    },

    async deleteSelectedJob() {
        if (!this.selectedJobId) return;
        const job = this.jobs.find((item) => String(item.job_id || item.task_id || '') === this.selectedJobId);
        if (!job || !this.isTerminal(job.status)) return;
        if (!window.confirm('删除这条后台任务记录？已生成的结果文件不会被删除。')) return;
        await this.fetchJson(`/api/jobs/${encodeURIComponent(this.selectedJobId)}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
        });
        this.selectedJobId = '';
        await this.loadJobs();
    },

    renderStats() {
        const counts = this.jobs.reduce((acc, job) => {
            const status = job.status || 'queued';
            acc[status] = (acc[status] || 0) + 1;
            return acc;
        }, {});
        this.setText('scriptJobStatRunning', String((counts.running || 0) + (counts.queued || 0)));
        this.setText('scriptJobStatCompleted', String(counts.completed || 0));
        this.setText('scriptJobStatFailed', String(counts.failed || 0));
        this.setText('scriptJobStatCancelled', String((counts.cancelled || 0) + (counts.interrupted || 0)));
    },

    getModuleLabel(moduleName) {
        const labels = {
            'charts.combined': '综合图表',
            'treemap.generate': 'Treemap',
            'chord.generate': 'Chord',
            'treemap': 'Treemap',
            'chord': 'Chord',
            'profile': 'Profile 分析',
            'boxplot': '箱线图分析',
            'db-alignment': '数据库比对',
            'pep-analysis': 'PEP 共享分析',
            'topclone': 'TopClone 分析',
            'umap': 'UMAP 降维分析',
            'volcano': '火山图分析',
            'umapin': 'UMAPin 降维',
            'ml-analysis': '机器学习分析',
            'pgen-analysis': 'Pgen 分析',
            'mait-nkt': 'MAIT/NKT 分析',
        };
        if (labels[moduleName]) return labels[moduleName];
        const catalogLabel = this.modules[moduleName]?.label;
        if (catalogLabel) return catalogLabel;
        return labels[moduleName] || moduleName || '分析任务';
    },

    getModuleIcon(moduleName) {
        if (String(moduleName || '').includes('chart')) return 'bi-grid-1x2';
        if (String(moduleName || '').includes('treemap')) return 'bi-columns-gap';
        if (String(moduleName || '').includes('chord')) return 'bi-bezier2';
        if (String(moduleName || '').includes('heatmap')) return 'bi-grid-3x3-gap';
        if (String(moduleName || '').includes('statistical')) return 'bi-bar-chart-line';
        if (String(moduleName || '').includes('ppt')) return 'bi-file-earmark-slides';
        return 'bi-cpu';
    },

    isTerminal(status) {
        return ['completed', 'failed', 'cancelled', 'interrupted'].includes(status);
    },

    formatDateTime(value) {
        if (!value) return '';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value);
        return date.toLocaleString();
    },

    normalizeProgress(value) {
        const number = Number(value || 0);
        if (!Number.isFinite(number)) return 0;
        return Math.max(0, Math.min(100, number));
    },

    setText(id, value) {
        const element = document.getElementById(id);
        if (element) element.textContent = value ?? '';
    },

    escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    },
};

document.addEventListener('DOMContentLoaded', () => ScriptHubJobsPage.init());
