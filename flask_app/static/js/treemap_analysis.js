const TreemapAnalysis = {
    basePath: '',
    scanResult: null,
    samples: [],
    selectedChains: [],
    selectedSampleKeys: new Set(),
    detectedSampleSelectionInitialized: false,
    selectedFilePath: null,
    fileColumns: [],
    result: null,
    activeTaskId: null,
    pollTimer: null,
    syncPollTimer: null,
    dataSourceMode: 'local',
    remoteSources: [],
    remoteSourceId: '',
    remoteBrowsePath: '',
    remoteSelectedPath: '',
    remoteParentPath: null,
    remoteTreeNodes: {},
    remoteTreeRootPath: '',
    remoteTreeFilter: '',
    remoteBrowserMessage: '',
    isBrowsingRemote: false,
    projectContext: null,
    fieldMapping: {
        cdr3_column: '',
        copy_column: '',
        v_column: '',
        j_column: ''
    },

    COLUMN_HINTS: {
        cdr3_column: ['cdr3(pep)', 'cdr3_pep', 'cdr3aa', 'cdr3_aa', 'cdr3'],
        copy_column: ['copy', 'copies', 'count', 'reads', 'umis', 'umi'],
        v_column: ['v', 'v_gene', 'vgene', 'bestvgene', 'v_call'],
        j_column: ['j', 'j_gene', 'jgene', 'bestjgene', 'j_call']
    },

    init() {
        this.updateStepIndicator(1);
        const modeSelect = document.getElementById('dataSourceMode');
        const remoteSourceSelect = document.getElementById('remoteSourceSelect');
        const remoteTreeSearch = document.getElementById('remoteTreeSearch');
        const topcloneOnly = document.getElementById('topcloneOnly');

        if (modeSelect) {
            this.dataSourceMode = modeSelect.value || 'local';
            modeSelect.addEventListener('change', () => this.toggleDataSourceMode(modeSelect.value));
            this.toggleDataSourceMode(this.dataSourceMode);
        }
        if (remoteSourceSelect) {
            remoteSourceSelect.addEventListener('change', () => this.handleRemoteSourceChange());
        }
        if (remoteTreeSearch) {
            remoteTreeSearch.addEventListener('input', event => this.handleRemoteTreeSearch(event.target.value));
        }
        if (topcloneOnly) {
            topcloneOnly.addEventListener('change', () => this.updateTopcloneOnlyState());
            this.updateTopcloneOnlyState();
        }
        this.loadRemoteSources();
        this.initializeFromProjectContext();
    },

    getProjectContext() {
        if (this.projectContext) return this.projectContext;
        const params = new URLSearchParams(window.location.search);
        this.projectContext = {
            projectId: params.get('project_id') || '',
            projectName: params.get('project_name') || '',
            basePath: params.get('base_path') || '',
            autoScan: params.get('auto_scan') === '1'
        };
        return this.projectContext;
    },

    initializeFromProjectContext() {
        const context = this.getProjectContext();
        if (!context.projectId) return;

        const container = document.querySelector('.container-fluid.py-4');
        if (container) {
            const banner = document.createElement('div');
            banner.className = 'alert alert-primary d-flex justify-content-between align-items-center gap-3';
            banner.innerHTML = `
                <div>
                    <div class="fw-semibold">项目桥接已启用</div>
                    <div class="small">当前项目：${this.escapeHtml(context.projectName || context.projectId)}。Treemap 会直接从项目目录扫描数据。</div>
                </div>
                <a class="btn btn-sm btn-outline-primary" href="/projects/${encodeURIComponent(context.projectId)}">返回项目详情</a>
            `;
            container.insertBefore(banner, container.firstChild);
        }

        const basePathInput = document.getElementById('basePath');
        if (basePathInput && context.basePath) {
            basePathInput.value = context.basePath;
        }
        if (context.autoScan && context.basePath) {
            this.scanFolder();
        }
    },

    escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    },

    async registerProjectResult(payload) {
        const context = this.getProjectContext();
        if (!context.projectId) return;
        try {
            await fetch(`/api/projects/${encodeURIComponent(context.projectId)}/analysis/treemap/register-result`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (error) {
            console.warn('Failed to register treemap result for project:', error);
        }
    },

    updateTopcloneOnlyState() {
        const topcloneOnly = document.getElementById('topcloneOnly');
        const disableVisuals = Boolean(topcloneOnly?.checked);
        const minCopyDefault = document.getElementById('minCopyDefault');
        const layoutModeSelect = document.getElementById('layoutModeSelect');
        const canvasShapeSelect = document.getElementById('canvasShapeSelect');

        if (minCopyDefault) {
            minCopyDefault.disabled = disableVisuals;
        }
        if (layoutModeSelect) {
            layoutModeSelect.disabled = disableVisuals;
        }
        if (canvasShapeSelect) {
            canvasShapeSelect.disabled = disableVisuals;
        }
    },

    updateStepIndicator(step) {
        document.querySelectorAll('.step-item').forEach((item, index) => {
            const stepNum = index + 1;
            item.classList.remove('active', 'completed');
            if (stepNum < step) item.classList.add('completed');
            if (stepNum === step) item.classList.add('active');
        });
    },

    showLoading(text = '正在处理...') {
        document.getElementById('loadingStage').textContent = '正在处理...';
        document.getElementById('loadingText').textContent = text;
        this.updateProgress(0, '正在处理...', text, [], { phase: 'queued' }, 'queued');
        document.getElementById('loadingOverlay').style.display = 'flex';
    },

    hideLoading() {
        document.getElementById('loadingOverlay').style.display = 'none';
    },

    showError(message) {
        alert(message);
    },

    formatPhaseLabel(phase, status) {
        const phaseMap = {
            queued: '排队中',
            init: '初始化',
            sample_prepare: '准备样本',
            read_chain: '读取链数据',
            individual_html: '生成单链 HTML',
            overview_html: '生成七链 HTML',
            individual_png: '导出单链 PNG',
            trim_png: '裁切 PNG',
            overview_png: '导出七链 PNG',
            metadata: '写入结果',
            completed: '已完成',
            failed: '已失败'
        };
        if (phase && phaseMap[phase]) return phaseMap[phase];
        if (status === 'completed') return '已完成';
        if (status === 'failed') return '已失败';
        if (status === 'queued') return '排队中';
        return '处理中';
    },

    formatDuration(totalSeconds) {
        const seconds = Math.max(0, Math.round(Number(totalSeconds || 0)));
        const minutes = Math.floor(seconds / 60);
        const remainSeconds = seconds % 60;
        if (minutes <= 0) return `${remainSeconds} 秒`;
        if (minutes < 60) return `${minutes} 分 ${remainSeconds} 秒`;
        const hours = Math.floor(minutes / 60);
        const remainMinutes = minutes % 60;
        return `${hours} 小时 ${remainMinutes} 分`;
    },

    estimateRemainingSeconds(progress, history = []) {
        const value = Number(progress || 0);
        if (!Array.isArray(history) || history.length < 2 || value <= 0 || value >= 100) {
            return null;
        }

        const parseTimestamp = (timestamp) => {
            if (!timestamp) return null;
            const parts = String(timestamp).split(':').map(item => Number(item));
            if (parts.length !== 3 || parts.some(Number.isNaN)) return null;
            const now = new Date();
            return new Date(now.getFullYear(), now.getMonth(), now.getDate(), parts[0], parts[1], parts[2]).getTime();
        };

        const first = history[0];
        const last = history[history.length - 1];
        const startTime = parseTimestamp(first.timestamp);
        const endTime = parseTimestamp(last.timestamp);
        if (!startTime || !endTime || endTime <= startTime) return null;

        const elapsedSeconds = (endTime - startTime) / 1000;
        const estimatedTotalSeconds = elapsedSeconds / (value / 100);
        const remainingSeconds = estimatedTotalSeconds - elapsedSeconds;
        return Number.isFinite(remainingSeconds) && remainingSeconds > 0 ? remainingSeconds : null;
    },

    updateProgressMeta(meta = {}, status = 'running') {
        const phaseEl = document.getElementById('loadingMetaPhase');
        const sampleEl = document.getElementById('loadingMetaSample');
        const chainEl = document.getElementById('loadingMetaChain');
        const unitsEl = document.getElementById('loadingMetaUnits');
        const etaEl = document.getElementById('loadingMetaEta');
        const fileEl = document.getElementById('loadingMetaFile');

        const sampleText = meta.current_sample
            ? `${meta.current_sample}${meta.current_sample_index ? ` (${meta.current_sample_index}/${meta.total_samples || '-'})` : ''}`
            : (meta.total_samples ? `共 ${meta.total_samples} 个样本` : '-');
        const chainText = meta.current_chain
            ? `${meta.current_chain}${meta.current_chain_index ? ` (${meta.current_chain_index}/${meta.current_chain_total || '-'})` : ''}`
            : (meta.selected_chain_count ? `已选 ${meta.selected_chain_count} 条链` : '-');
        const unitsText = meta.total_units
            ? `${meta.completed_units || 0}/${meta.total_units}`
            : '-';

        if (phaseEl) phaseEl.textContent = this.formatPhaseLabel(meta.phase, status);
        if (sampleEl) sampleEl.textContent = sampleText;
        if (chainEl) chainEl.textContent = chainText;
        if (unitsEl) unitsEl.textContent = unitsText;
        if (etaEl) etaEl.textContent = meta.estimated_remaining_seconds
            ? this.formatDuration(meta.estimated_remaining_seconds)
            : (status === 'completed' ? '0 秒' : '估算中');
        if (fileEl) {
            const fileParts = [];
            if (meta.current_input_file) fileParts.push(`输入: ${meta.current_input_file}`);
            if (meta.current_output_file) fileParts.push(`输出: ${meta.current_output_file}`);
            fileEl.textContent = fileParts.length ? fileParts.join(' | ') : '-';
        }
    },

    updateProgress(progress, stage, detail, history = null, meta = {}, status = 'running') {
        const progressBar = document.getElementById('loadingProgressBar');
        const stageEl = document.getElementById('loadingStage');
        const detailEl = document.getElementById('loadingText');
        const logEl = document.getElementById('loadingProgressLog');

        const value = Math.max(0, Math.min(100, Number(progress || 0)));
        if (progressBar) {
            progressBar.style.width = `${value}%`;
            progressBar.setAttribute('aria-valuenow', String(value));
            progressBar.textContent = `${Math.round(value)}%`;
        }
        if (stageEl) stageEl.textContent = stage || '正在处理...';
        if (detailEl) detailEl.textContent = detail || '';
        const nextMeta = { ...(meta || {}) };
        const estimatedRemaining = this.estimateRemainingSeconds(value, history || []);
        if (estimatedRemaining) nextMeta.estimated_remaining_seconds = estimatedRemaining;
        this.updateProgressMeta(nextMeta, status);

        if (logEl && Array.isArray(history)) {
            logEl.innerHTML = history.length
                ? history.slice().reverse().map(item => `
                    <div class="progress-log-item">
                        <div class="fw-semibold">${item.stage || '处理中'} <span class="text-muted">(${Math.round(item.progress || 0)}%)</span></div>
                        <div class="text-muted small">${item.timestamp || ''}</div>
                        <div class="text-muted">${item.detail || ''}</div>
                    </div>
                `).join('')
                : '<div class="text-muted">等待任务开始...</div>';
        }
    },

    stopTaskPolling() {
        if (this.pollTimer) {
            clearTimeout(this.pollTimer);
            this.pollTimer = null;
        }
    },

    stopSyncPolling() {
        if (this.syncPollTimer) {
            clearTimeout(this.syncPollTimer);
            this.syncPollTimer = null;
        }
    },

    setScanSummary(message, variant = 'info') {
        const summary = document.getElementById('scanSummary');
        if (!summary) return;
        summary.classList.remove('d-none', 'alert-info', 'alert-success', 'alert-warning', 'alert-danger');
        summary.classList.add(`alert-${variant}`);
        summary.textContent = message || '';
    },

    updateRemoteHint(message, variant = 'secondary') {
        const hint = document.getElementById('remoteSourceHint');
        if (!hint) return;
        hint.className = `alert alert-${variant} mb-3`;
        hint.textContent = message || '';
    },

    toggleDataSourceMode(mode = 'local') {
        this.dataSourceMode = mode;
        const localPanel = document.getElementById('localSourcePanel');
        const remotePanel = document.getElementById('remoteSourcePanel');
        if (localPanel) localPanel.classList.toggle('d-none', mode !== 'local');
        if (remotePanel) remotePanel.classList.toggle('d-none', mode !== 'remote');
        if (mode === 'remote' && this.remoteSourceId && !this.remoteBrowsePath) {
            this.browseRemoteRoot();
        }
    },

    async pollTaskStatus(taskId) {
        try {
            const response = await fetch(`/api/treemap/task/${encodeURIComponent(taskId)}`);
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || '读取任务状态失败');
            }

            this.updateProgress(data.progress, data.stage, data.detail, data.history || [], data.meta || {}, data.status);

            if (data.status === 'completed') {
                this.stopTaskPolling();
                this.result = data.result;
                await this.registerProjectResult({
                    job_id: data.result?.job_id,
                    output_base: data.result?.job_id ? `treemap:${data.result.job_id}` : '',
                    report_path: data.result?.viewer_url || '',
                    report_url: data.result?.viewer_url || '',
                    zip_url: data.result?.zip_url || '',
                    viewer_url: data.result?.viewer_url || '',
                    metadata: {
                        sample_count: data.result?.sample_count || 0,
                        topclone_only: Boolean(data.result?.topclone_only)
                    }
                });
                document.getElementById('resultSummary').textContent = data.result?.topclone_only
                    ? `已生成 ${data.result.sample_count} 个样本的 topclone 表格结果。可打开结果页或下载 ZIP。`
                    : `已生成 ${data.result.sample_count} 个样本的 treemap 结果。点击“新窗口打开查看器”进行查看。`;
                this.updateResultActions();
                document.getElementById('resultsCard').style.display = 'block';
                document.getElementById('resultsCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
                this.hideLoading();
                return;
            }

            if (data.status === 'failed') {
                this.stopTaskPolling();
                this.hideLoading();
                this.showError(data.error || data.detail || 'Treemap 任务失败');
                return;
            }

            this.pollTimer = setTimeout(() => this.pollTaskStatus(taskId), 1000);
        } catch (error) {
            this.stopTaskPolling();
            this.hideLoading();
            this.showError(error.message);
        }
    },

    updateResultActions() {
        const openViewerBtn = document.getElementById('openViewerBtn');
        const downloadZipBtn = document.getElementById('downloadZipBtn');
        if (openViewerBtn) {
            openViewerBtn.style.display = this.result?.viewer_url ? '' : 'none';
            openViewerBtn.innerHTML = this.result?.topclone_only
                ? '<i class="bi bi-box-arrow-up-right me-1"></i>打开结果页'
                : '<i class="bi bi-box-arrow-up-right me-1"></i>新窗口打开查看器';
        }
        if (downloadZipBtn) {
            downloadZipBtn.style.display = this.result?.zip_url ? '' : 'none';
        }
    },

    normalizeHeader(value) {
        return String(value || '').trim().toLowerCase().replace(/[\s\-_.\/]+/g, '');
    },

    findSuggestedColumn(columns, key, fallback = '') {
        const aliases = this.COLUMN_HINTS[key] || [];
        const normalized = new Map(columns.map(col => [this.normalizeHeader(col), col]));
        for (const alias of aliases) {
            const match = normalized.get(this.normalizeHeader(alias));
            if (match) return match;
        }
        return fallback;
    },

    async scanFolder() {
        const basePath = document.getElementById('basePath').value.trim();
        if (!basePath) {
            this.showError('请输入分析目录路径');
            return;
        }

        this.showLoading('正在扫描目录...');
        try {
            const response = await fetch('/api/auto-heatmap/scan-folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ base_path: basePath })
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || '扫描目录失败');
            }

            this.basePath = basePath;
            this.scanResult = data;
            this.samples = data.samples || [];
            this.result = null;

            const summary = document.getElementById('scanSummary');
            summary.classList.remove('d-none', 'alert-danger', 'alert-info');
            summary.classList.add(data.has_chain_suffix ? 'alert-info' : 'alert-danger');
            summary.textContent = data.summary || '扫描完成';

            if (!data.has_chain_suffix || !Array.isArray(data.all_chains) || data.all_chains.length === 0) {
                throw new Error('当前 treemap 模块仅支持包含链后缀的文件命名，例如 SAMPLE__TRA.csv.gz');
            }

            this.renderChainSelection(data.all_chains);
            document.getElementById('step2Card').style.display = 'block';
            document.getElementById('step3Card').style.display = 'none';
            document.getElementById('step4Card').style.display = 'none';
            document.getElementById('resultsCard').style.display = 'none';
            this.updateStepIndicator(2);
            document.getElementById('step2Card').scrollIntoView({ behavior: 'smooth', block: 'start' });
        } catch (error) {
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    },

    renderChainSelection(chains) {
        const container = document.getElementById('chainList');
        container.innerHTML = '';
        this.selectedChains = [...chains];
        this.selectedSampleKeys = new Set();
        this.detectedSampleSelectionInitialized = false;

        chains.forEach((chain, index) => {
            const item = document.createElement('div');
            item.className = 'chain-item selected';
            item.innerHTML = `
                <input type="checkbox" class="form-check-input mt-0" value="${chain}" checked data-index="${index}">
                <span class="fw-medium">${chain}</span>
            `;
            const checkbox = item.querySelector('input');
            checkbox.addEventListener('click', event => {
                event.stopPropagation();
                item.classList.toggle('selected', checkbox.checked);
                this.updateSelectedChains();
            });
            item.addEventListener('click', (event) => {
                if (event.target.tagName !== 'INPUT') {
                    checkbox.checked = !checkbox.checked;
                    item.classList.toggle('selected', checkbox.checked);
                    this.updateSelectedChains();
                }
            });
            container.appendChild(item);
        });

        this.renderDetectedSamples();
    },

    updateSelectedChains() {
        this.selectedChains = Array.from(document.querySelectorAll('#chainList input[type="checkbox"]'))
            .filter(checkbox => checkbox.checked)
            .map(checkbox => checkbox.value);
        this.renderDetectedSamples();
    },

    selectAllChains() {
        document.querySelectorAll('#chainList input[type="checkbox"]').forEach(checkbox => {
            checkbox.checked = true;
            checkbox.closest('.chain-item').classList.add('selected');
        });
        this.updateSelectedChains();
    },

    invertChains() {
        document.querySelectorAll('#chainList input[type="checkbox"]').forEach(checkbox => {
            checkbox.checked = !checkbox.checked;
            checkbox.closest('.chain-item').classList.toggle('selected', checkbox.checked);
        });
        this.updateSelectedChains();
    },

    clearChains() {
        document.querySelectorAll('#chainList input[type="checkbox"]').forEach(checkbox => {
            checkbox.checked = false;
            checkbox.closest('.chain-item').classList.remove('selected');
        });
        this.updateSelectedChains();
    },

    getDetectedSamplesForSelectedChains() {
        if (!this.selectedChains.length) return [];

        return this.samples
            .map(sample => {
                const matchedChains = [];
                for (const fileInfo of sample.data_files || []) {
                    const name = String(fileInfo.filename || '').replace(/\.(csv|tsv|txt)(\.gz)?$/i, '');
                    for (const chain of this.selectedChains) {
                        if ((name.endsWith(`__${chain}`) || name.endsWith(`_${chain}`)) && !matchedChains.includes(chain)) {
                            matchedChains.push(chain);
                        }
                    }
                }

                if (!matchedChains.length) return null;
                return {
                    ...sample,
                    sample_key: `${sample.display_name || sample.original_name || 'sample'}::${sample.folder_path || ''}`,
                    matched_chains: matchedChains
                };
            })
            .filter(Boolean);
    },

    syncDetectedSampleSelection(detectedSamples) {
        if (!this.detectedSampleSelectionInitialized) {
            this.selectedSampleKeys = new Set(detectedSamples.map(sample => sample.sample_key));
            this.detectedSampleSelectionInitialized = true;
        }
    },

    updateDetectedSampleSummary(detectedCount = null) {
        const summary = document.getElementById('sampleDetectSummary');
        if (!summary) return;

        if (!this.selectedChains.length) {
            summary.textContent = '尚未选择链';
            return;
        }

        const total = detectedCount === null ? this.getDetectedSamplesForSelectedChains().length : detectedCount;
        summary.textContent = `共识别到 ${total} 个样本，已选择 ${this.selectedSampleKeys.size} 个`;
    },

    renderDetectedSamples() {
        const list = document.getElementById('sampleDetectList');
        if (!list) return;

        const detectedSamples = this.getDetectedSamplesForSelectedChains();
        this.syncDetectedSampleSelection(detectedSamples);
        list.innerHTML = '';

        if (!this.selectedChains.length) {
            this.updateDetectedSampleSummary(detectedSamples.length);
            list.innerHTML = '<div class="text-muted small">请先选择至少一条链。</div>';
            return;
        }

        this.updateDetectedSampleSummary(detectedSamples.length);

        if (!detectedSamples.length) {
            list.innerHTML = '<div class="text-muted small">当前链选择下没有匹配到样本。</div>';
            return;
        }

        detectedSamples.forEach(sample => {
            const card = document.createElement('div');
            const checked = this.selectedSampleKeys.has(sample.sample_key);
            card.className = `sample-detect-card${checked ? ' selected' : ''}`;
            card.innerHTML = `
                <div class="sample-detect-head">
                    <input type="checkbox" class="form-check-input mt-1 sample-detect-checkbox" ${checked ? 'checked' : ''}>
                    <div class="sample-detect-name">${sample.display_name || sample.original_name}</div>
                </div>
                <div class="sample-chain-badges">
                    ${sample.matched_chains.map(chain => `<span class="badge text-bg-primary">${chain}</span>`).join('')}
                </div>
            `;
            const checkbox = card.querySelector('.sample-detect-checkbox');
            checkbox.addEventListener('click', event => event.stopPropagation());
            checkbox.addEventListener('change', () => {
                this.setDetectedSampleSelection(sample.sample_key, checkbox.checked, card);
            });
            card.addEventListener('click', event => {
                if (event.target.tagName !== 'INPUT') {
                    checkbox.checked = !checkbox.checked;
                }
                this.setDetectedSampleSelection(sample.sample_key, checkbox.checked, card);
            });
            list.appendChild(card);
        });
    },

    setDetectedSampleSelection(sampleKey, checked, card = null) {
        if (checked) this.selectedSampleKeys.add(sampleKey);
        else this.selectedSampleKeys.delete(sampleKey);

        if (card) {
            card.classList.toggle('selected', checked);
            const checkbox = card.querySelector('.sample-detect-checkbox');
            if (checkbox) checkbox.checked = checked;
        }

        this.updateDetectedSampleSummary();
    },

    selectAllDetectedSamples() {
        const detectedSamples = this.getDetectedSamplesForSelectedChains();
        this.selectedSampleKeys = new Set(detectedSamples.map(sample => sample.sample_key));
        this.renderDetectedSamples();
    },

    invertDetectedSamples() {
        const detectedSamples = this.getDetectedSamplesForSelectedChains();
        const nextSelection = new Set();
        detectedSamples.forEach(sample => {
            if (!this.selectedSampleKeys.has(sample.sample_key)) {
                nextSelection.add(sample.sample_key);
            }
        });
        this.selectedSampleKeys = nextSelection;
        this.detectedSampleSelectionInitialized = true;
        this.renderDetectedSamples();
    },

    clearDetectedSamples() {
        this.selectedSampleKeys = new Set();
        this.detectedSampleSelectionInitialized = true;
        this.renderDetectedSamples();
    },

    updateDetectedSampleSummary(detectedCount = null) {
        const summary = document.getElementById('sampleDetectSummary');
        if (!summary) return;

        if (!this.selectedChains.length) {
            summary.textContent = '尚未选择链';
            return;
        }

        const total = detectedCount === null ? this.getDetectedSamplesForSelectedChains().length : detectedCount;
        const selectedVisibleCount = this.getSelectedDetectedSamples().length;
        summary.textContent = `共识别到 ${total} 个样本，已选择 ${selectedVisibleCount} 个`;
    },

    getSelectedDetectedSamples() {
        return this.getDetectedSamplesForSelectedChains()
            .filter(sample => this.selectedSampleKeys.has(sample.sample_key));
    },

    async confirmChainSelection() {
        if (!this.selectedChains.length) {
            this.showError('请至少选择一条链');
            return;
        }

        const detectedSamples = this.getSelectedDetectedSamples();
        if (!detectedSamples.length) {
            this.showError('请至少选择一个样本');
            return;
        }

        const sampleFilePath = this.findSampleFilePath();
        if (!sampleFilePath) {
            this.showError('未找到与所选链匹配的数据文件');
            return;
        }

        this.selectedFilePath = sampleFilePath;
        this.showLoading('正在读取表头并准备字段映射...');
        try {
            const response = await fetch('/api/auto-heatmap/get-file-columns', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath: sampleFilePath })
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || '读取字段失败');
            }

            this.fileColumns = data.columns || [];
            this.renderFieldMapping(data);
            document.getElementById('step3Card').style.display = 'block';
            document.getElementById('step4Card').style.display = 'none';
            this.updateStepIndicator(3);
            document.getElementById('step3Card').scrollIntoView({ behavior: 'smooth', block: 'start' });
        } catch (error) {
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    },

    findSampleFilePath() {
        for (const sample of this.getSelectedDetectedSamples()) {
            for (const fileInfo of sample.data_files || []) {
                const name = String(fileInfo.filename || '').replace(/\.(csv|tsv|txt)(\.gz)?$/i, '');
                const matched = this.selectedChains.some(chain => name.endsWith(`__${chain}`) || name.endsWith(`_${chain}`));
                if (matched) return fileInfo.filepath;
            }
        }
        return null;
    },

    buildSelectOptions(selectId, columns, selectedValue = '') {
        const select = document.getElementById(selectId);
        select.innerHTML = '<option value="">-- 请选择 --</option>';
        columns.forEach(column => {
            const option = document.createElement('option');
            option.value = column;
            option.textContent = column;
            select.appendChild(option);
        });
        select.value = selectedValue || '';
    },

    renderFieldMapping(data) {
        const columns = data.columns || [];
        const suggested = {
            cdr3_column: data.suggested_cdr3 || this.findSuggestedColumn(columns, 'cdr3_column'),
            copy_column: data.suggested_copy || this.findSuggestedColumn(columns, 'copy_column'),
            v_column: this.findSuggestedColumn(columns, 'v_column'),
            j_column: this.findSuggestedColumn(columns, 'j_column')
        };

        Object.entries(suggested).forEach(([key, value]) => {
            this.fieldMapping[key] = value || '';
        });

        this.buildSelectOptions('cdr3Column', columns, this.fieldMapping.cdr3_column);
        this.buildSelectOptions('copyColumn', columns, this.fieldMapping.copy_column);
        this.buildSelectOptions('vColumn', columns, this.fieldMapping.v_column);
        this.buildSelectOptions('jColumn', columns, this.fieldMapping.j_column);

        document.getElementById('cdr3Column').onchange = () => { this.fieldMapping.cdr3_column = document.getElementById('cdr3Column').value; };
        document.getElementById('copyColumn').onchange = () => { this.fieldMapping.copy_column = document.getElementById('copyColumn').value; };
        document.getElementById('vColumn').onchange = () => { this.fieldMapping.v_column = document.getElementById('vColumn').value; };
        document.getElementById('jColumn').onchange = () => { this.fieldMapping.j_column = document.getElementById('jColumn').value; };

        this.renderPreviewTable(columns, data.sample_data || []);
    },

    renderPreviewTable(columns, rows) {
        const thead = document.querySelector('#previewTable thead');
        const tbody = document.querySelector('#previewTable tbody');
        thead.innerHTML = '';
        tbody.innerHTML = '';

        const headerRow = document.createElement('tr');
        columns.forEach(column => {
            const th = document.createElement('th');
            th.textContent = column;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);

        rows.forEach(row => {
            const tr = document.createElement('tr');
            row.forEach(cell => {
                const td = document.createElement('td');
                td.textContent = cell === null || cell === undefined ? '' : String(cell);
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
    },

    confirmFieldMapping() {
        this.fieldMapping.cdr3_column = document.getElementById('cdr3Column').value;
        this.fieldMapping.copy_column = document.getElementById('copyColumn').value;
        this.fieldMapping.v_column = document.getElementById('vColumn').value;
        this.fieldMapping.j_column = document.getElementById('jColumn').value;

        if (!this.fieldMapping.cdr3_column) {
            this.showError('请选择 CDR3 列');
            return;
        }
        if (!this.fieldMapping.copy_column) {
            this.showError('请选择 copy 列');
            return;
        }
        if (!this.fieldMapping.v_column) {
            this.showError('请选择 V 列');
            return;
        }
        if (!this.fieldMapping.j_column) {
            this.showError('请选择 J 列');
            return;
        }

        document.getElementById('step4Card').style.display = 'block';
        this.updateStepIndicator(4);
        document.getElementById('step4Card').scrollIntoView({ behavior: 'smooth', block: 'start' });
    },

    async generateTreemap() {
        if (!this.samples.length) {
            this.showError('请先扫描目录');
            return;
        }
        if (!this.selectedChains.length) {
            this.showError('请至少选择一条链');
            return;
        }
        if (!this.fieldMapping.cdr3_column || !this.fieldMapping.copy_column || !this.fieldMapping.v_column || !this.fieldMapping.j_column) {
            this.showError('请先完成字段映射');
            return;
        }

        const detectedSamples = this.getSelectedDetectedSamples();
        if (!detectedSamples.length) {
            this.showError('请至少选择一个样本进行生成');
            return;
        }

        const payload = {
            samples: detectedSamples,
            selected_chains: this.selectedChains,
            field_mapping: this.fieldMapping,
            config: {
                output_name: document.getElementById('outputName').value.trim(),
                min_copy_default: Number(document.getElementById('minCopyDefault').value || 30),
                top_n: Number(document.getElementById('topN').value || 100),
                layout_mode: document.getElementById('layoutModeSelect')?.value || 'tetris',
                canvas_shape: document.getElementById('canvasShapeSelect')?.value || 'square',
                topclone_only: Boolean(document.getElementById('topcloneOnly')?.checked)
            }
        };

        this.showLoading('正在生成 treemap 结果...');
        try {
            const response = await fetch('/api/treemap/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || '生成 treemap 失败');
            }

            this.activeTaskId = data.task_id;
            this.updateProgress(
                0,
                '任务已创建',
                '任务已进入队列，等待开始。',
                [
                    {
                        progress: 0,
                        stage: '任务已创建',
                        detail: '任务已进入队列，等待开始。',
                        timestamp: new Date().toLocaleTimeString()
                    }
                ],
                {
                    phase: 'queued',
                    total_samples: detectedSamples.length,
                    selected_chain_count: this.selectedChains.length,
                    selected_chains: [...this.selectedChains]
                },
                'queued'
            );
            this.stopTaskPolling();
            this.pollTaskStatus(data.task_id);
        } catch (error) {
            this.showError(error.message);
            this.hideLoading();
        }
    },

    resetRemoteTreeState() {
        this.remoteBrowsePath = '';
        this.remoteSelectedPath = '';
        this.remoteParentPath = null;
        this.remoteTreeNodes = {};
        this.remoteTreeRootPath = '';
        this.remoteTreeFilter = '';
        this.remoteBrowserMessage = '';
        this.isBrowsingRemote = false;
        const search = document.getElementById('remoteTreeSearch');
        if (search) search.value = '';
    },

    getRemoteNodeLabel(path, fallback = '') {
        const parts = String(path || '').split('/').filter(Boolean);
        return parts.length ? parts[parts.length - 1] : (fallback || '/');
    },

    getRemoteRootLabel(rootPath, source = null) {
        if (source?.name) {
            return `${source.name} root`;
        }
        return this.getRemoteNodeLabel(rootPath, rootPath || '/');
    },

    upsertRemoteTreeNode(node) {
        if (!node || !node.path) return null;
        const existing = this.remoteTreeNodes[node.path] || {};
        const merged = {
            path: node.path,
            name: node.name || existing.name || this.getRemoteNodeLabel(node.path, node.path),
            parentPath: node.parentPath !== undefined ? node.parentPath : (existing.parentPath ?? null),
            childrenPaths: Array.isArray(node.childrenPaths) ? node.childrenPaths : (existing.childrenPaths || []),
            childrenLoaded: node.childrenLoaded !== undefined ? node.childrenLoaded : Boolean(existing.childrenLoaded),
            expanded: node.expanded !== undefined ? node.expanded : Boolean(existing.expanded),
            isLoading: node.isLoading !== undefined ? node.isLoading : false,
            fileCount: node.fileCount !== undefined ? node.fileCount : (existing.fileCount || 0),
            sourceName: node.sourceName !== undefined ? node.sourceName : (existing.sourceName || '')
        };
        this.remoteTreeNodes[node.path] = merged;
        return merged;
    },

    handleRemoteTreeSearch(value = '') {
        this.remoteTreeFilter = String(value || '').trim().toLowerCase();
        this.renderRemoteBrowser();
    },

    remoteTreeNodeMatchesFilter(nodePath) {
        const node = this.remoteTreeNodes[nodePath];
        if (!node) return false;
        if (!this.remoteTreeFilter) return true;

        const haystacks = [node.name, node.path, node.sourceName]
            .filter(Boolean)
            .map(item => String(item).toLowerCase());
        if (haystacks.some(item => item.includes(this.remoteTreeFilter))) {
            return true;
        }

        return (node.childrenPaths || []).some(childPath => this.remoteTreeNodeMatchesFilter(childPath));
    },

    async loadRemoteSources() {
        const remoteSourceSelect = document.getElementById('remoteSourceSelect');
        if (!remoteSourceSelect) return;

        this.resetRemoteTreeState();

        try {
            const response = await fetch('/api/remote-sources');
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to load SSH data sources');
            }

            this.remoteSources = Array.isArray(data.sources) ? data.sources : [];
            remoteSourceSelect.innerHTML = '';

            if (!this.remoteSources.length) {
                remoteSourceSelect.disabled = true;
                remoteSourceSelect.innerHTML = '<option value="">No SSH source configured</option>';
                this.remoteSourceId = '';
                this.remoteBrowserMessage = 'No SSH data source is configured yet.';
                this.renderRemoteBrowser();
                this.updateRemotePathDisplay();
                this.updateRemoteHint(this.remoteBrowserMessage, 'danger');
                return;
            }

            remoteSourceSelect.disabled = false;
            this.remoteSources.forEach(source => {
                const option = document.createElement('option');
                option.value = source.id;
                option.textContent = `${source.name} (${source.username}@${source.host}:${source.port})`;
                remoteSourceSelect.appendChild(option);
            });

            this.remoteSourceId = this.remoteSources[0].id;
            remoteSourceSelect.value = this.remoteSourceId;
            this.remoteBrowserMessage = 'Test the connection or expand the tree to choose a folder.';
            this.renderRemoteBrowser();
            this.updateRemoteHint('SSH data sources loaded. Use the tree to expand folders in place.', 'secondary');

            if (this.dataSourceMode === 'remote') {
                await this.browseRemoteRoot();
            }
        } catch (error) {
            this.remoteSources = [];
            this.remoteSourceId = '';
            this.remoteBrowserMessage = error.message;
            this.renderRemoteBrowser();
            this.updateRemoteHint(error.message, 'danger');
        }
    },

    async handleRemoteSourceChange() {
        const select = document.getElementById('remoteSourceSelect');
        this.remoteSourceId = select ? select.value : '';
        this.resetRemoteTreeState();
        this.updateRemotePathDisplay();

        if (this.remoteSourceId) {
            await this.browseRemoteRoot();
        }
    },

    updateRemotePathDisplay() {
        const currentPathEl = document.getElementById('remoteCurrentPath');
        const selectedPathEl = document.getElementById('remoteSelectedPath');
        if (currentPathEl) currentPathEl.textContent = this.remoteBrowsePath || '-';
        if (selectedPathEl) selectedPathEl.textContent = this.remoteSelectedPath || '-';
    },

    renderRemoteBrowser() {
        const container = document.getElementById('remoteBrowserList');
        if (!container) return;

        container.innerHTML = '';

        if (!this.remoteTreeRootPath) {
            const empty = document.createElement('div');
            empty.className = 'remote-tree-empty';
            empty.textContent = this.remoteBrowserMessage || 'Test the SSH connection to load the root folder tree.';
            container.appendChild(empty);
            return;
        }

        const rootNode = this.remoteTreeNodes[this.remoteTreeRootPath];
        if (!rootNode) {
            const empty = document.createElement('div');
            empty.className = 'remote-tree-empty';
            empty.textContent = this.remoteBrowserMessage || 'Remote root is not available yet.';
            container.appendChild(empty);
            return;
        }

        const rootElement = this.renderRemoteTreeNode(rootNode, 0);
        if (!rootElement) {
            const empty = document.createElement('div');
            empty.className = 'remote-tree-empty';
            empty.textContent = 'No loaded folder matches the current filter.';
            container.appendChild(empty);
            return;
        }

        const shell = document.createElement('div');
        shell.className = 'remote-tree-shell';
        shell.appendChild(rootElement);
        container.appendChild(shell);
    },

    renderRemoteTreeNode(node, depth) {
        if (!node || !this.remoteTreeNodeMatchesFilter(node.path)) {
            return null;
        }

        const branch = document.createElement('div');
        branch.className = 'remote-tree-branch';

        const row = document.createElement('div');
        row.className = 'remote-tree-node';
        row.style.setProperty('--tree-depth', String(depth));
        if (this.remoteBrowsePath === node.path) {
            row.classList.add('active');
        }
        if (this.remoteSelectedPath === node.path) {
            row.classList.add('selected');
        }

        const toggleBtn = document.createElement('button');
        toggleBtn.type = 'button';
        toggleBtn.className = 'remote-tree-toggle';
        const hasKnownChildren = !node.childrenLoaded || (node.childrenPaths || []).length > 0;
        if (!hasKnownChildren && depth > 0) {
            toggleBtn.disabled = true;
            toggleBtn.innerHTML = '<i class="bi bi-dot"></i>';
        } else {
            toggleBtn.innerHTML = `<i class="bi ${node.expanded ? 'bi-chevron-down' : 'bi-chevron-right'}"></i>`;
            toggleBtn.addEventListener('click', async event => {
                event.stopPropagation();
                await this.toggleRemoteNode(node.path);
            });
        }
        row.appendChild(toggleBtn);

        const entryBtn = document.createElement('button');
        entryBtn.type = 'button';
        entryBtn.className = 'remote-tree-entry';
        entryBtn.addEventListener('click', () => this.selectRemotePath(node.path));

        const icon = document.createElement('i');
        icon.className = `bi ${node.expanded ? 'bi-folder2-open' : 'bi-folder'} remote-tree-icon`;
        entryBtn.appendChild(icon);

        const textWrap = document.createElement('div');
        textWrap.className = 'remote-tree-text';

        const title = document.createElement('div');
        title.className = 'remote-tree-name';
        title.textContent = node.name || this.getRemoteNodeLabel(node.path, '/');
        textWrap.appendChild(title);

        const meta = document.createElement('div');
        meta.className = 'remote-tree-meta';
        const metaParts = [node.path];
        if (node.fileCount > 0) {
            metaParts.push(`${node.fileCount} file(s)`);
        }
        if (this.remoteSelectedPath === node.path) {
            metaParts.push('selected');
        } else if (this.remoteBrowsePath === node.path) {
            metaParts.push('current');
        }
        meta.textContent = metaParts.join('  |  ');
        textWrap.appendChild(meta);

        entryBtn.appendChild(textWrap);
        row.appendChild(entryBtn);
        branch.appendChild(row);

        if (node.expanded) {
            if (node.isLoading) {
                const loading = document.createElement('div');
                loading.className = 'remote-tree-empty';
                loading.style.setProperty('--tree-depth', String(depth + 1));
                loading.textContent = 'Loading subfolders...';
                branch.appendChild(loading);
            } else if (node.childrenLoaded && !(node.childrenPaths || []).length) {
                const empty = document.createElement('div');
                empty.className = 'remote-tree-empty';
                empty.style.setProperty('--tree-depth', String(depth + 1));
                empty.textContent = 'No subfolders under this node. You can select it directly.';
                branch.appendChild(empty);
            } else if ((node.childrenPaths || []).length) {
                const children = document.createElement('div');
                children.className = 'remote-tree-children';
                node.childrenPaths.forEach(childPath => {
                    const childElement = this.renderRemoteTreeNode(this.remoteTreeNodes[childPath], depth + 1);
                    if (childElement) {
                        children.appendChild(childElement);
                    }
                });
                if (children.childElementCount > 0) {
                    branch.appendChild(children);
                }
            }
        }

        return branch;
    },

    selectRemotePath(path) {
        this.remoteSelectedPath = path || '';
        this.remoteBrowsePath = path || '';
        const node = this.remoteTreeNodes[this.remoteSelectedPath];
        this.remoteParentPath = node?.parentPath || null;
        this.updateRemotePathDisplay();
        this.renderRemoteBrowser();
    },

    async browseRemoteRoot() {
        await this.browseRemote(this.remoteTreeRootPath || null);
    },

    async browseRemoteParent() {
        if (!this.remoteParentPath) return;

        const parentNode = this.remoteTreeNodes[this.remoteParentPath];
        if (parentNode) {
            parentNode.expanded = true;
            this.remoteTreeNodes[parentNode.path] = parentNode;
            this.remoteBrowsePath = parentNode.path;
            this.remoteParentPath = parentNode.parentPath || null;
            this.updateRemotePathDisplay();
            this.renderRemoteBrowser();
            return;
        }

        await this.browseRemote(this.remoteParentPath);
    },

    selectCurrentRemotePath() {
        if (!this.remoteBrowsePath) {
            this.showError('There is no remote folder selected yet');
            return;
        }
        this.selectRemotePath(this.remoteBrowsePath);
    },

    async refreshRemoteNode() {
        if (!this.remoteSourceId) {
            this.showError('Please select an SSH data source first');
            return;
        }
        await this.browseRemote(this.remoteBrowsePath || this.remoteTreeRootPath || null);
    },

    async toggleRemoteNode(path) {
        const node = this.remoteTreeNodes[path];
        if (!node) return;

        this.remoteBrowsePath = path;
        this.remoteParentPath = node.parentPath || null;
        this.updateRemotePathDisplay();

        if (node.childrenLoaded) {
            node.expanded = !node.expanded;
            this.remoteTreeNodes[path] = node;
            this.renderRemoteBrowser();
            return;
        }

        node.isLoading = true;
        node.expanded = true;
        this.remoteTreeNodes[path] = node;
        this.renderRemoteBrowser();
        await this.browseRemote(path, true);
    },

    async browseRemote(path = null, skipLoading = false) {
        if (!this.remoteSourceId) {
            this.showError('Please select an SSH data source first');
            return;
        }

        if (this.isBrowsingRemote) {
            return;
        }
        this.isBrowsingRemote = true;

        if (!skipLoading) {
            this.showLoading('Loading remote folders...');
        }

        try {
            const response = await fetch('/api/remote-sources/browse', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_id: this.remoteSourceId, path })
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to load remote directory');
            }

            const rootPath = data.root_path || data.current_path || '/';
            const currentPath = data.current_path || rootPath;
            const currentEntries = Array.isArray(data.entries) ? data.entries : [];
            const childDirs = currentEntries.filter(entry => entry && entry.is_dir);
            const fileCount = currentEntries.length - childDirs.length;

            if (!this.remoteTreeRootPath || currentPath === rootPath) {
                this.remoteTreeRootPath = rootPath;
            }

            this.upsertRemoteTreeNode({
                path: this.remoteTreeRootPath,
                name: this.getRemoteRootLabel(this.remoteTreeRootPath, data.source),
                parentPath: null,
                expanded: true,
                sourceName: data.source?.name || ''
            });

            const currentNodeName = currentPath === this.remoteTreeRootPath
                ? this.getRemoteRootLabel(this.remoteTreeRootPath, data.source)
                : this.getRemoteNodeLabel(currentPath, currentPath);

            const childPaths = [];
            childDirs.forEach(entry => {
                childPaths.push(entry.path);
                const existingNode = this.remoteTreeNodes[entry.path];
                this.upsertRemoteTreeNode({
                    path: entry.path,
                    name: entry.name || this.getRemoteNodeLabel(entry.path, entry.path),
                    parentPath: currentPath,
                    childrenLoaded: existingNode?.childrenLoaded || false,
                    expanded: existingNode?.expanded || false,
                    isLoading: false,
                    fileCount: existingNode?.fileCount || 0
                });
            });

            this.upsertRemoteTreeNode({
                path: currentPath,
                name: currentNodeName,
                parentPath: currentPath === this.remoteTreeRootPath ? null : (data.parent_path || this.remoteTreeNodes[currentPath]?.parentPath || null),
                childrenPaths: childPaths,
                childrenLoaded: true,
                expanded: true,
                isLoading: false,
                fileCount
            });

            this.remoteBrowsePath = currentPath;
            this.remoteParentPath = data.parent_path || null;
            this.remoteBrowserMessage = childDirs.length
                ? ''
                : 'This folder has no subfolders. Select it directly if this is the folder you want to sync.';
            this.updateRemotePathDisplay();
            this.renderRemoteBrowser();
            this.updateRemoteHint(`Browsing ${data.source?.name || this.remoteSourceId}: ${this.remoteBrowsePath}`, 'info');
        } catch (error) {
            const targetNode = path ? this.remoteTreeNodes[path] : null;
            if (targetNode) {
                targetNode.isLoading = false;
                this.remoteTreeNodes[path] = targetNode;
            }
            this.remoteBrowserMessage = error.message;
            this.updateRemoteHint(error.message, 'danger');
            this.renderRemoteBrowser();
            if (!skipLoading) this.showError(error.message);
        } finally {
            this.isBrowsingRemote = false;
            if (!skipLoading) this.hideLoading();
        }
    },

    async testRemoteSource() {
        if (!this.remoteSourceId) {
            this.showError('Please select an SSH data source first');
            return;
        }

        this.showLoading('Testing SSH connection...');
        try {
            const response = await fetch('/api/remote-sources/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_id: this.remoteSourceId })
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'SSH connection test failed');
            }

            this.updateRemoteHint(`SSH connected. Root path: ${data.test_result.root_path}`, 'success');
            await this.browseRemoteRoot();
        } catch (error) {
            this.updateRemoteHint(error.message, 'danger');
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    },

    async syncRemoteAndScan() {
        if (!this.remoteSourceId) {
            this.showError('Please select an SSH data source first');
            return;
        }
        if (!this.remoteSelectedPath) {
            this.showError('Please select a remote folder to sync');
            return;
        }

        this.showLoading('Syncing remote folder...');
        try {
            const response = await fetch('/api/remote-sources/sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source_id: this.remoteSourceId,
                    remote_path: this.remoteSelectedPath
                })
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to sync remote folder');
            }

            this.activeSyncTaskId = data.task_id;
            this.stopSyncPolling();
            this.pollSyncTaskStatus(data.task_id);
        } catch (error) {
            this.hideLoading();
            this.showError(error.message);
        }
    },

    async pollSyncTaskStatus(taskId) {
        try {
            const response = await fetch(`/api/remote-sources/sync-task/${encodeURIComponent(taskId)}`);
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to read sync task status');
            }

            this.updateProgress(data.progress, data.stage, data.detail, data.history || [], data.meta || {}, data.status);

            if (data.status === 'completed') {
                this.stopSyncPolling();
                const localCachePath = data.result?.local_cache_path || '';
                document.getElementById('basePath').value = localCachePath;
                this.setScanSummary(
                    `Remote folder ${data.result?.remote_path || this.remoteSelectedPath} synced. Starting local scan...`,
                    'info'
                );
                await this.scanLocalFolder(localCachePath, 'Scanning synced folder...');
                return;
            }

            if (data.status === 'failed') {
                this.stopSyncPolling();
                this.hideLoading();
                this.showError(data.error || data.detail || 'Remote sync failed');
                return;
            }

            this.syncPollTimer = setTimeout(() => this.pollSyncTaskStatus(taskId), 1000);
        } catch (error) {
            this.stopSyncPolling();
            this.hideLoading();
            this.showError(error.message);
        }
    },

    async scanLocalFolder(basePath, loadingText = 'Scanning directory...') {
        this.showLoading(loadingText);
        try {
            const response = await fetch('/api/auto-heatmap/scan-folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ base_path: basePath })
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to scan directory');
            }

            this.basePath = basePath;
            this.scanResult = data;
            this.samples = data.samples || [];
            this.result = null;

            this.setScanSummary(data.summary || 'Scan completed', data.has_chain_suffix ? 'info' : 'danger');

            if (!data.has_chain_suffix || !Array.isArray(data.all_chains) || !data.all_chains.length) {
                throw new Error('Treemap currently requires chain-suffixed filenames such as SAMPLE__TRA.csv.gz');
            }

            this.renderChainSelection(data.all_chains);
            document.getElementById('step2Card').style.display = 'block';
            document.getElementById('step3Card').style.display = 'none';
            document.getElementById('step4Card').style.display = 'none';
            document.getElementById('resultsCard').style.display = 'none';
            this.updateStepIndicator(2);
            document.getElementById('step2Card').scrollIntoView({ behavior: 'smooth', block: 'start' });
        } finally {
            this.hideLoading();
        }
    },

    async scanFolder() {
        if (this.dataSourceMode === 'remote') {
            await this.syncRemoteAndScan();
            return;
        }

        const basePath = document.getElementById('basePath').value.trim();
        if (!basePath) {
            this.showError('Please enter a data directory');
            return;
        }

        try {
            await this.scanLocalFolder(basePath, 'Scanning directory...');
        } catch (error) {
            this.showError(error.message);
        }
    },

    openViewer() {
        if (!this.result || !this.result.viewer_url) {
            this.showError('当前没有可打开的查看器');
            return;
        }
        window.open(this.result.viewer_url, '_blank', 'noopener');
    },

    downloadZip() {
        if (!this.result || !this.result.zip_url) {
            this.showError('当前没有可下载的 ZIP');
            return;
        }
        window.open(this.result.zip_url, '_blank', 'noopener');
    }
};

document.addEventListener('DOMContentLoaded', () => {
    TreemapAnalysis.init();
});
