const CombinedAnalysis = {
    basePath: '',
    projectContext: null,
    activeModule: '',
    scanResult: null,
    samples: [],
    selectedChains: [],
    selectedSampleKeys: new Set(),
    selectedFilePath: null,
    fileColumns: [],
    fieldMapping: {
        cdr3_column: '',
        copy_column: '',
        v_column: '',
        j_column: ''
    },
    result: null,
    activeTaskId: null,
    pollTimer: null,
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

    COLUMN_HINTS: {
        cdr3_column: ['cdr3(pep)', 'cdr3_pep', 'cdr3aa', 'cdr3_aa', 'cdr3'],
        copy_column: ['copy', 'copies', 'count', 'reads', 'umis', 'umi'],
        v_column: ['v', 'v_gene', 'vgene', 'bestvgene', 'v_call'],
        j_column: ['j', 'j_gene', 'jgene', 'bestjgene', 'j_call']
    },

    init() {
        this.updateStepIndicator(1);
        this.projectContext = this.getProjectContext();
        const modeSelect = document.getElementById('dataSourceMode');
        const remoteSourceSelect = document.getElementById('remoteSourceSelect');
        const remoteTreeSearch = document.getElementById('remoteTreeSearch');

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

        this.loadRemoteSources();
        this.loadProjects();

        const projectSelect = document.getElementById('combinedProjectSelect');
        if (projectSelect) {
            projectSelect.addEventListener('change', () => this.onProjectChange(projectSelect.value));
        }

        const chainList = document.getElementById('chainList');
        const sampleDetectList = document.getElementById('sampleDetectList');
        if (chainList) {
            chainList.addEventListener('click', event => {
                const card = event.target.closest('[data-chain]');
                if (!card) return;
                this.toggleChain(card.dataset.chain || '');
            });
            chainList.addEventListener('keydown', event => {
                if (event.key !== 'Enter' && event.key !== ' ') return;
                const card = event.target.closest('[data-chain]');
                if (!card) return;
                event.preventDefault();
                this.toggleChain(card.dataset.chain || '');
            });
        }
        if (sampleDetectList) {
            sampleDetectList.addEventListener('click', event => {
                const card = event.target.closest('[data-sample-key]');
                if (!card) return;
                this.toggleDetectedSample(card.dataset.sampleKey || '');
            });
            sampleDetectList.addEventListener('keydown', event => {
                if (event.key !== 'Enter' && event.key !== ' ') return;
                const card = event.target.closest('[data-sample-key]');
                if (!card) return;
                event.preventDefault();
                this.toggleDetectedSample(card.dataset.sampleKey || '');
            });
        }

        document.querySelectorAll('.module-option-input').forEach(input => {
            input.addEventListener('change', () => this.updateModuleConfigVisibility());
        });

        this.applyInitialModuleSelection();
        this.initializeProjectContext();
        this.updateModuleConfigVisibility();
    },

    getProjectContext() {
        const params = new URLSearchParams(window.location.search);
        return {
            projectId: params.get('project_id') || '',
            projectName: params.get('project_name') || '',
            basePath: params.get('base_path') || '',
            autoScan: params.get('auto_scan') === '1',
            analysisType: params.get('analysis_type') || '',
            activeModule: params.get('active_module') || ''
        };
    },

    initializeProjectContext() {
        const context = this.projectContext || this.getProjectContext();
        this.activeModule = context.activeModule || '';

        if (context.basePath) {
            const basePathInput = document.getElementById('basePath');
            if (basePathInput && !basePathInput.value) {
                basePathInput.value = context.basePath;
            }
        }

        if (context.projectId) {
            const container = document.querySelector('.container-fluid.py-4');
            if (container && !container.querySelector('[data-project-context-banner]')) {
                const banner = document.createElement('div');
                banner.className = 'alert alert-primary d-flex justify-content-between align-items-center gap-3';
                banner.setAttribute('data-project-context-banner', '1');
                banner.innerHTML = `
                    <div>
                        <div class="fw-semibold">Project workspace enabled</div>
                        <div class="small">Current project: ${this.escapeHtml(context.projectName || context.projectId)}. The unified analysis workspace will read data directly from the project asset directory.</div>
                    </div>
                    <a class="btn btn-sm btn-outline-primary" href="/projects/${encodeURIComponent(context.projectId)}">Back to project</a>
                `;
                container.insertBefore(banner, container.firstChild);
            }
        }

        if (context.autoScan && context.basePath && !this._autoScanTriggered) {
            this._autoScanTriggered = true;
            this.scanFolder();
        }
    },

    applyInitialModuleSelection() {
        const activeModule = (this.projectContext?.activeModule || '').trim().toLowerCase();
        if (!activeModule) return;

        const inputs = Array.from(document.querySelectorAll('.module-option-input'));
        let matched = false;
        inputs.forEach(input => {
            const isMatch = (input.value || '').toLowerCase() === activeModule;
            input.checked = isMatch;
            if (isMatch) matched = true;
        });

        if (!matched) {
            inputs.forEach(input => {
                input.checked = ['heatmap', 'treemap', 'chord'].includes(input.value);
            });
        }
    },



    updateStepIndicator(step) {
        const stepItems = document.querySelectorAll('.step-item');
        stepItems.forEach((item, index) => {
            item.classList.toggle('active', index === step - 1);
            item.classList.toggle('completed', index < step - 1);
        });
    },

    showLoading(text = '正在处理...') {
        document.getElementById('loadingStage').textContent = '正在处理...';
        document.getElementById('loadingText').textContent = text;
        this.updateProgress(0, '正在处理...', text, []);
        document.getElementById('loadingOverlay').style.display = 'flex';
    },

    hideLoading() {
        document.getElementById('loadingOverlay').style.display = 'none';
    },

    showError(message) {
        alert(message);
    },

    async loadProjects() {
        const select = document.getElementById('combinedProjectSelect');
        if (!select) return;
        try {
            const response = await fetch('/api/projects');
            const data = await response.json();
            const projects = Array.isArray(data.projects) ? data.projects : [];
            projects.forEach(p => {
                const opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = p.name || p.id;
                select.appendChild(opt);
            });
            const context = this.projectContext || this.getProjectContext();
            if (context.projectId) {
                select.value = context.projectId;
                this.onProjectChange(context.projectId);
            }
        } catch (error) {
            console.warn('Failed to load projects for charts:', error);
        }
    },

    async onProjectChange(projectId) {
        if (!projectId) return;
        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}`);
            const project = await response.json();
            const pepAssets = (project.assets || []).filter(a => a.asset_type === 'pep');
            if (pepAssets.length > 0) {
                const basePathInput = document.getElementById('basePath');
                if (basePathInput && !basePathInput.value) {
                    basePathInput.value = pepAssets[0].storage_path;
                }
            }
        } catch (error) {
            console.warn('Failed to load project assets for charts:', error);
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

    setScanSummary(message, tone = 'info') {
        const summary = document.getElementById('scanSummary');
        if (!summary) return;
        summary.classList.remove('d-none', 'alert-info', 'alert-success', 'alert-warning', 'alert-danger');
        summary.classList.add(`alert-${tone}`);
        summary.textContent = message || '';
    },

toggleDataSourceMode(mode = 'local') {
        this.dataSourceMode = mode;
        const remotePanel = document.getElementById('remoteSourcePanel');
        const basePathInput = document.getElementById('basePath');
        const scanButton = document.querySelector('button[onclick="CombinedAnalysis.scanFolder()"]');
        
        if (remotePanel) {
            remotePanel.classList.toggle('d-none', mode !== 'remote');
        }
        
        // Show/hide local input based on mode
        if (basePathInput) {
            basePathInput.closest('.row').style.display = mode === 'local' ? '' : 'none';
        }
        if (scanButton) {
            scanButton.closest('.col-lg-3').style.display = mode === 'local' ? '' : 'none';
        }
        
        // Only browse remote root when we switch to remote mode and have a source
        if (mode === 'remote' && this.remoteSourceId && !this.remoteBrowsePath) {
            this.browseRemoteRoot();
        }
    },

    handleRemoteSourceChange() {
        const remoteSourceSelect = document.getElementById('remoteSourceSelect');
        if (!remoteSourceSelect) return;
        this.remoteSourceId = remoteSourceSelect.value;
        // Reset browsing state when source changes
        this.remoteBrowsePath = '';
        this.remoteSelectedPath = '';
        this.remoteParentPath = null;
        this.updateRemotePathDisplay();
        
        // Only browse remote root when we have a source and are in remote mode
        if (this.remoteSourceId && this.dataSourceMode === 'remote') {
            this.browseRemoteRoot();
        }
    },

    async loadRemoteSources() {
        const remoteSourceSelect = document.getElementById('remoteSourceSelect');
        if (!remoteSourceSelect) return;

        try {
            const response = await fetch('/api/remote-sources');
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || '加载 SSH 数据源失败');
            }

            this.remoteSources = Array.isArray(data.sources) ? data.sources : [];
            remoteSourceSelect.innerHTML = '';

            if (!this.remoteSources.length) {
                remoteSourceSelect.disabled = true;
                remoteSourceSelect.innerHTML = '<option value="">未配置 SSH 数据源</option>';
                this.remoteSourceId = '';
                this.remoteBrowsePath = '';
                this.remoteSelectedPath = '';
                this.remoteParentPath = null;
                this.updateRemotePathDisplay();
                this.updateRemoteHint('当前未配置 SSH Linux 数据源。请先在服务端配置 SSH_REMOTE_SOURCES。', 'danger');
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
            this.updateRemoteHint('已加载 SSH 数据源，请选择目录后点击"同步并扫描目录"。', 'secondary');

            if (this.dataSourceMode === 'remote') {
                await this.browseRemoteRoot();
            }
        } catch (error) {
            this.remoteSources = [];
            this.remoteSourceId = '';
            remoteSourceSelect.innerHTML = '<option value="">加载 SSH 数据源失败</option>';
            remoteSourceSelect.disabled = true;
            this.updateRemotePathDisplay();
            this.updateRemoteHint(error.message, 'danger');
        }
    },

    updateRemoteHint(message, tone = 'secondary') {
        const hint = document.getElementById('remoteSourceHint');
        if (!hint) return;
        hint.classList.remove('alert-secondary', 'alert-info', 'alert-danger', 'alert-success');
        hint.classList.add(`alert-${tone}`);
        hint.textContent = message;
    },

    async testRemoteSource() {
        if (!this.remoteSourceId) {
            this.showError('请先选择 SSH 数据源');
            return;
        }

        this.showLoading('正在测试 SSH 连接...');
        try {
            const response = await fetch('/api/remote-sources/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_id: this.remoteSourceId })
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'SSH 连接测试失败');
            }

            this.updateRemoteHint(`SSH 连接成功，根目录: ${data.test_result.root_path}`, 'success');
        } catch (error) {
            this.updateRemoteHint(error.message, 'danger');
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    },

    refreshRemoteNode() {
        if (this.remoteBrowsePath) {
            this.browseRemotePath(this.remoteBrowsePath);
        }
    },

    handleRemoteTreeSearch(query) {
        this.remoteTreeFilter = query || '';
        this.updateRemoteTreeDisplay();
    },

    async browseRemoteRoot() {
        if (!this.remoteSourceId) {
            this.showError('请先选择 SSH 数据源');
            return;
        }

        this.showLoading('正在读取根目录...');
        this.isBrowsingRemote = true;
        try {
            const response = await fetch('/api/remote-sources/browse', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_id: this.remoteSourceId })
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '读取根目录失败');

            const rootPath = data.current_path || '/';
            this.remoteBrowsePath = rootPath;
            this.remoteSelectedPath = rootPath;
            this.remoteParentPath = data.parent_path || null;
            this.remoteTreeRootPath = rootPath;
            this.remoteTreeNodes = data.entries || {};
            this.updateRemoteTreeDisplay();
            this.updateRemotePathDisplay();
        } catch (error) {
            this.showError(error.message || '读取根目录失败');
        } finally {
            this.hideLoading();
            this.isBrowsingRemote = false;
        }
    },

    async browseRemoteParent() {
        if (!this.remoteBrowsePath || !this.remoteParentPath) return;
        this.browseRemotePath(this.remoteParentPath);
    },

    async browseRemotePath(path) {
        if (!path || !this.remoteSourceId) return;
        this.showLoading('正在浏览目录...');
        this.isBrowsingRemote = true;
        try {
            const response = await fetch('/api/remote-sources/browse', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    source_id: this.remoteSourceId,
                    path: path 
                })
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '浏览目录失败');
            
            this.remoteBrowsePath = data.current_path || path;
            this.remoteParentPath = data.parent_path || null;
            
            // Convert entries to nodes format for backward compatibility
            this.remoteTreeNodes = {};
            if (Array.isArray(data.entries)) {
                data.entries.forEach(entry => {
                    this.remoteTreeNodes[entry.path] = entry.is_dir;
                });
            }
            
            this.renderRemoteBrowser(data.entries || [], '当前目录为空');
            this.updateRemotePathDisplay();
        } catch (error) {
            this.showError(error.message || '浏览目录失败');
        } finally {
            this.hideLoading();
            this.isBrowsingRemote = false;
        }
    },

    selectCurrentRemotePath() {
        this.remoteSelectedPath = this.remoteBrowsePath;
        this.updateRemotePathDisplay();
    },

    async syncRemoteAndScan() {
        if (!this.remoteSelectedPath) {
            this.showError('请先选择要同步的目录');
            return;
        }

        this.showLoading('正在同步目录...');
        try {
            // First sync the remote directory
            const syncResponse = await fetch('/api/remote-sources/sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source_id: this.remoteSourceId,
                    remote_path: this.remoteSelectedPath
                })
            });
            const syncData = await syncResponse.json();
            if (!syncData.success) throw new Error(syncData.message || '同步失败');

            // Wait for sync to complete
            const taskId = syncData.task_id;
            await this.waitForSyncCompletion(taskId);
            
            // Get the local cache path from sync result
            const taskStatus = this.getSyncTaskStatus(taskId);
            const localCachePath = taskStatus?.result?.local_cache_path || '';
            if (!localCachePath) {
                throw new Error('无法获取同步后的本地路径');
            }

            // Now scan the local directory
            await this.scanLocalFolder(localCachePath, '正在扫描已同步的目录...');
        } catch (error) {
            this.showError(error.message || '同步和扫描失败');
            this.setScanSummary(error.message || '同步和扫描失败', 'danger');
        } finally {
            this.hideLoading();
        }
    },

    async waitForSyncCompletion(taskId) {
        return new Promise((resolve, reject) => {
            const checkStatus = async () => {
                try {
                    const response = await fetch(`/api/remote-sources/sync-task/${encodeURIComponent(taskId)}`);
                    const data = await response.json();
                    
                    if (data.status === 'completed') {
                        resolve();
                        return;
                    }
                    
                    if (data.status === 'failed') {
                        reject(new Error(data.detail || data.error || '同步失败'));
                        return;
                    }
                    
                    // Still running, check again
                    setTimeout(checkStatus, 1000);
                } catch (error) {
                    reject(error);
                }
            };
            checkStatus();
        });
    },

    getSyncTaskStatus(taskId) {
        // This is a simplified version - in a real app, you might want to poll the API
        return null; // Will be updated by actual API calls
    },

    async scanLocalFolder(basePath, message = '正在扫描目录...') {
        this.showLoading(message);
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
            if (!data.has_chain_suffix) {
                throw new Error('当前模块仅支持带链后缀的 repertoire 文件，例如 SAMPLE__IGH.csv.gz');
            }

            this.basePath = basePath;
            this.scanResult = data;
            this.samples = Array.isArray(data.samples) ? data.samples : [];
            this.selectedChains = Array.isArray(data.all_chains) ? [...data.all_chains] : [];
            this.selectedSampleKeys = new Set(this.samples.map(sample => this.getSampleKey(sample)));
            this.result = null;
            this.activeTaskId = null;
            this.selectedFilePath = null;
            this.fileColumns = [];
            this.fieldMapping = { cdr3_column: '', copy_column: '', v_column: '', j_column: '' };

            this.renderChainList();
            this.renderDetectedSamples();
            this.updateStepIndicator(2);
            document.getElementById('step2Card').style.display = '';
            document.getElementById('step3Card').style.display = 'none';
            document.getElementById('step4Card').style.display = 'none';
            document.getElementById('resultsCard').style.display = 'none';
            this.setScanSummary(data.summary || `找到 ${this.samples.length} 个样本`, 'success');
        } catch (error) {
            this.showError(error.message || '扫描目录失败');
            this.setScanSummary(error.message || '扫描目录失败', 'danger');
        }
    },

    renderRemoteBrowser(entries = [], emptyMessage = '当前目录为空') {
        const container = document.getElementById('remoteBrowserList');
        if (!container) return;

        container.innerHTML = '';
        if (!entries.length) {
            const emptyHint = this.remoteBrowsePath
                ? `${emptyMessage}<div class="mt-2">当前目录为空，请返回上一级或选择其他目录。</div>`
                : emptyMessage;
            container.innerHTML = `<div class="text-muted small">${emptyHint}</div>`;
            return;
        }

        entries.forEach(entry => {
            const item = document.createElement('div');
            item.className = `remote-browser-item${this.remoteSelectedPath === entry.path ? ' selected' : ''}`;

            const title = document.createElement('div');
            title.className = 'fw-semibold mb-2';
            title.textContent = entry.name || entry.path;
            item.appendChild(title);

            const path = document.createElement('div');
            path.className = 'remote-browser-path text-muted mb-3';
            path.textContent = entry.path;
            item.appendChild(path);

            const meta = document.createElement('div');
            meta.className = 'small text-muted mb-3';
            meta.textContent = entry.is_dir ? '目录' : `文件 ${entry.size || 0} bytes`;
            item.appendChild(meta);

            const actions = document.createElement('div');
            actions.className = 'd-flex flex-wrap gap-2';

            if (entry.is_dir) {
                const browseBtn = document.createElement('button');
                browseBtn.className = 'btn btn-outline-secondary btn-sm';
                browseBtn.textContent = '进入';
                browseBtn.addEventListener('click', () => this.browseRemotePath(entry.path));
                actions.appendChild(browseBtn);

                const selectBtn = document.createElement('button');
                selectBtn.className = 'btn btn-outline-primary btn-sm';
                selectBtn.textContent = '选择此目录';
                selectBtn.addEventListener('click', () => {
                    this.remoteSelectedPath = entry.path;
                    this.updateRemotePathDisplay();
                });
                actions.appendChild(selectBtn);
            }

            item.appendChild(actions);
            container.appendChild(item);
        });
    },

    updateRemoteTreeDisplay() {
        // This method now just renders the browser using entries
        const entries = Object.entries(this.remoteTreeNodes || {}).map(([name, isDir]) => ({
            name: name,
            path: name,
            is_dir: isDir,
            size: isDir ? 0 : 1024 // Placeholder size
        }));
        this.renderRemoteBrowser(entries);
    },

    updateRemotePathDisplay() {
        const currentPathEl = document.getElementById('remoteCurrentPath');
        const selectedPathEl = document.getElementById('remoteSelectedPath');
        if (currentPathEl) currentPathEl.textContent = this.remoteBrowsePath || '-';
        if (selectedPathEl) selectedPathEl.textContent = this.remoteSelectedPath || '-';
    },

    updateProgress(progress, stage, detail, history = []) {
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

    getSampleKey(sample) {
        return `${sample.original_name || ''}::${sample.folder_path || ''}`;
    },

    escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    },

    filenameMatchesChain(filename, chain) {
        const nameWithoutExt = String(filename || '').replace(/\.(csv|tsv|txt)(\.gz)?$/i, '');
        const normalizedName = nameWithoutExt.toUpperCase();
        const normalizedChain = String(chain || '').toUpperCase();
        return normalizedName.endsWith(`__${normalizedChain}`) || normalizedName.endsWith(`_${normalizedChain}`);
    },

    getSampleAvailableChains(sample) {
        const available = new Set();
        (sample.data_files || []).forEach(fileInfo => {
            this.selectedChains.forEach(chain => {
                if (this.filenameMatchesChain(fileInfo.filename, chain)) {
                    available.add(chain);
                }
            });
        });
        return Array.from(available);
    },

    getVisibleSamples() {
        if (!this.selectedChains.length) return [];
        return this.samples
            .map(sample => ({ sample, chains: this.getSampleAvailableChains(sample) }))
            .filter(item => item.chains.length > 0);
    },

    getVisibleSelectedSampleCount() {
        return this.getVisibleSamples()
            .filter(({ sample }) => this.selectedSampleKeys.has(this.getSampleKey(sample)))
            .length;
    },

    getSelectedVisibleSamplesPayload() {
        const visibleKeys = new Set(this.getVisibleSamples().map(item => this.getSampleKey(item.sample)));
        return this.samples
            .filter(sample => visibleKeys.has(this.getSampleKey(sample)) && this.selectedSampleKeys.has(this.getSampleKey(sample)))
            .map(sample => ({
                original_name: sample.original_name,
                display_name: sample.display_name,
                folder_path: sample.folder_path,
                data_files: (sample.data_files || []).map(fileInfo => ({
                    filename: fileInfo.filename,
                    filepath: fileInfo.filepath,
                    size: fileInfo.size,
                    rows: fileInfo.rows,
                    columns: fileInfo.columns
                }))
            }));
    },

    getSelectedModules() {
        return Array.from(document.querySelectorAll('.module-option-input:checked'))
            .map(input => input.value);
    },

    updateModuleConfigVisibility() {
        return;
    },

    async scanFolder() {
        const basePath = document.getElementById('basePath').value.trim();
        if (!basePath) {
            this.showError('请输入文件夹路径');
            return;
        }

        this.showLoading('正在扫描文件夹...');
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
            if (!data.has_chain_suffix) {
                throw new Error('当前模块仅支持带链后缀的 repertoire 文件，例如 SAMPLE__IGH.csv.gz');
            }

            this.basePath = basePath;
            this.scanResult = data;
            this.samples = Array.isArray(data.samples) ? data.samples : [];
            this.selectedChains = Array.isArray(data.all_chains) ? [...data.all_chains] : [];
            this.selectedSampleKeys = new Set(this.samples.map(sample => this.getSampleKey(sample)));
            this.result = null;
            this.activeTaskId = null;
            this.selectedFilePath = null;
            this.fileColumns = [];
            this.fieldMapping = { cdr3_column: '', copy_column: '', v_column: '', j_column: '' };

            this.renderChainList();
            this.renderDetectedSamples();
            this.updateStepIndicator(2);
            document.getElementById('step2Card').style.display = '';
            document.getElementById('step3Card').style.display = 'none';
            document.getElementById('step4Card').style.display = 'none';
            document.getElementById('resultsCard').style.display = 'none';
            this.setScanSummary(data.summary || `找到 ${this.samples.length} 个样本`, 'success');
        } catch (error) {
            this.showError(error.message || '扫描目录失败');
            this.setScanSummary(error.message || '扫描目录失败', 'danger');
        } finally {
            this.hideLoading();
        }
    },

    renderChainList() {
        const chainList = document.getElementById('chainList');
        const chainSummary = document.getElementById('chainSummary');
        if (!chainList) return;
        const allChains = Array.isArray(this.scanResult?.all_chains) ? this.scanResult.all_chains : [];
        if (!allChains.length) {
            chainList.innerHTML = '<div class="selection-empty">当前目录没有识别到可用链。</div>';
            if (chainSummary) chainSummary.textContent = '0 条链';
            return;
        }

        chainList.innerHTML = allChains.map(chain => {
            const matchedSamples = this.samples.filter(sample =>
                (sample.data_files || []).some(fileInfo => this.filenameMatchesChain(fileInfo.filename, chain))
            ).length;
            const selected = this.selectedChains.includes(chain);
            return `
                <div class="chain-item ${selected ? 'selected' : ''}" data-chain="${this.escapeHtml(chain)}" role="button" tabindex="0" aria-pressed="${selected ? 'true' : 'false'}">
                    <span class="selection-check"><i class="bi bi-check-lg"></i></span>
                    <div class="chain-name">${this.escapeHtml(chain)}</div>
                    <div class="chain-meta">${matchedSamples} 个样本可用</div>
                </div>
            `;
        }).join('');
        if (chainSummary) {
            chainSummary.textContent = `已选 ${this.selectedChains.length} / ${allChains.length} 条链`;
        }
    },

    toggleChain(chain) {
        if (!chain) return;
        if (this.selectedChains.includes(chain)) {
            this.selectedChains = this.selectedChains.filter(item => item !== chain);
        } else {
            this.selectedChains.push(chain);
        }
        this.renderChainList();
        this.renderDetectedSamples();
    },

    selectAllChains() {
        this.selectedChains = Array.isArray(this.scanResult?.all_chains) ? [...this.scanResult.all_chains] : [];
        this.renderChainList();
        this.renderDetectedSamples();
    },

    invertChains() {
        const allChains = Array.isArray(this.scanResult?.all_chains) ? this.scanResult.all_chains : [];
        this.selectedChains = allChains.filter(chain => !this.selectedChains.includes(chain));
        this.renderChainList();
        this.renderDetectedSamples();
    },

    clearChains() {
        this.selectedChains = [];
        this.renderChainList();
        this.renderDetectedSamples();
    },

    renderDetectedSamples() {
        const sampleList = document.getElementById('sampleDetectList');
        const summary = document.getElementById('sampleDetectSummary');
        if (!sampleList || !summary) return;

        const visibleSamples = this.getVisibleSamples();

        if (!this.selectedChains.length) {
            sampleList.innerHTML = '<div class="selection-empty">请先选择至少 1 条链。</div>';
            summary.textContent = '尚未选择链';
            return;
        }

        if (!visibleSamples.length) {
            sampleList.innerHTML = '<div class="selection-empty">当前所选链下没有可用样本。</div>';
            summary.textContent = '0 个可选样本';
            return;
        }

        sampleList.innerHTML = visibleSamples.map(({ sample, chains }) => {
            const sampleKey = this.getSampleKey(sample);
            const selected = this.selectedSampleKeys.has(sampleKey);
            const fileCount = Array.isArray(sample.data_files) ? sample.data_files.length : 0;
            return `
                <div class="sample-detect-card ${selected ? 'selected' : ''}" data-sample-key="${this.escapeHtml(sampleKey)}" role="button" tabindex="0" aria-pressed="${selected ? 'true' : 'false'}">
                    <div class="sample-detect-head">
                        <span class="selection-check"><i class="bi bi-check-lg"></i></span>
                        <div>
                            <p class="sample-detect-name">${sample.display_name || sample.original_name}</p>
                            <div class="sample-detect-meta">${chains.length} 条匹配链 · ${fileCount} 个文件</div>
                        </div>
                    </div>
                    <div class="sample-chain-badges">
                        ${chains.map(chain => `<span class="badge bg-light text-dark border">${this.escapeHtml(chain)}</span>`).join('')}
                    </div>
                </div>
            `;
        }).join('');

        const visibleSelectedCount = this.getVisibleSelectedSampleCount();
        const hiddenSelectedCount = this.selectedSampleKeys.size - visibleSelectedCount;
        summary.textContent = hiddenSelectedCount > 0
            ? `当前已选 ${visibleSelectedCount} / ${visibleSamples.length} 个样本，另有 ${hiddenSelectedCount} 个历史选择暂未显示`
            : `已选 ${visibleSelectedCount} / ${visibleSamples.length} 个样本`;
    },

    toggleDetectedSample(sampleKey) {
        if (!sampleKey) return;
        if (this.selectedSampleKeys.has(sampleKey)) this.selectedSampleKeys.delete(sampleKey);
        else this.selectedSampleKeys.add(sampleKey);
        this.renderDetectedSamples();
    },

    selectAllDetectedSamples() {
        const nextSelected = new Set(this.selectedSampleKeys);
        this.getVisibleSamples().forEach(item => nextSelected.add(this.getSampleKey(item.sample)));
        this.selectedSampleKeys = nextSelected;
        this.renderDetectedSamples();
    },

    invertDetectedSamples() {
        const visibleKeys = new Set(this.getVisibleSamples().map(item => this.getSampleKey(item.sample)));
        const nextSelected = new Set(
            Array.from(this.selectedSampleKeys).filter(key => !visibleKeys.has(key))
        );
        this.getVisibleSamples().forEach(({ sample }) => {
            const key = this.getSampleKey(sample);
            if (!this.selectedSampleKeys.has(key)) nextSelected.add(key);
        });
        this.selectedSampleKeys = nextSelected;
        this.renderDetectedSamples();
    },

    clearDetectedSamples() {
        const visibleKeys = new Set(this.getVisibleSamples().map(item => this.getSampleKey(item.sample)));
        this.selectedSampleKeys = new Set(
            Array.from(this.selectedSampleKeys).filter(key => !visibleKeys.has(key))
        );
        this.renderDetectedSamples();
    },

    getSelectedSamplesPayload() {
        return this.getSelectedVisibleSamplesPayload();
    },

    getPreviewFilePath() {
        const selectedSamples = this.getSelectedSamplesPayload();
        for (const sample of selectedSamples) {
            for (const chain of this.selectedChains) {
                const fileInfo = (sample.data_files || []).find(item => this.filenameMatchesChain(item.filename, chain));
                if (fileInfo?.filepath) return fileInfo.filepath;
            }
        }
        return null;
    },

    async confirmChainSelection() {
        if (!this.selectedChains.length) {
            this.showError('请至少选择 1 条链');
            return;
        }
        if (this.getSelectedVisibleSamplesPayload().length < 2) {
            this.showError('请至少选择 2 个样本');
            return;
        }

        const previewPath = this.getPreviewFilePath();
        if (!previewPath) {
            this.showError('没有找到可用于字段映射的文件');
            return;
        }

        this.selectedFilePath = previewPath;
        await this.loadFileColumns(previewPath);
        this.updateStepIndicator(3);
        document.getElementById('step3Card').style.display = '';
        document.getElementById('step4Card').style.display = 'none';
        document.getElementById('resultsCard').style.display = 'none';
    },

    async loadFileColumns(filepath) {
        this.showLoading('正在读取字段信息...');
        try {
            const response = await fetch('/api/auto-heatmap/get-file-columns', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath })
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '读取字段失败');

            this.fileColumns = Array.isArray(data.columns) ? data.columns : [];
            this.populateFieldSelect('cdr3Column', this.fileColumns, data.suggested_cdr3, 'cdr3_column');
            this.populateFieldSelect('copyColumn', this.fileColumns, data.suggested_copy, 'copy_column');
            this.populateFieldSelect('vColumn', this.fileColumns, null, 'v_column');
            this.populateFieldSelect('jColumn', this.fileColumns, null, 'j_column');
            this.renderPreviewTable(data.sample_data || []);
        } catch (error) {
            this.showError(error.message || '读取字段失败');
        } finally {
            this.hideLoading();
        }
    },

    populateFieldSelect(elementId, columns, suggested, mappingKey) {
        const select = document.getElementById(elementId);
        if (!select) return;
        select.innerHTML = ['<option value="">-- 请选择 --</option>']
            .concat((columns || []).map(column => `<option value="${column}">${column}</option>`))
            .join('');

        const lowerHints = (this.COLUMN_HINTS[mappingKey] || []).map(item => item.toLowerCase());
        let selected = suggested && columns.includes(suggested) ? suggested : '';
        if (!selected) {
            selected = (columns || []).find(column => lowerHints.includes(String(column).toLowerCase())) || '';
        }
        if (selected) {
            select.value = selected;
            this.fieldMapping[mappingKey] = selected;
        }
        select.onchange = () => {
            this.fieldMapping[mappingKey] = select.value || '';
        };
    },

    renderPreviewTable(sampleData) {
        const thead = document.querySelector('#previewTable thead');
        const tbody = document.querySelector('#previewTable tbody');
        if (!thead || !tbody) return;

        const columns = this.fileColumns || [];
        thead.innerHTML = `<tr>${columns.map(column => `<th>${column}</th>`).join('')}</tr>`;
        tbody.innerHTML = (sampleData || []).map(row => `
            <tr>${columns.map((_, index) => `<td>${row[index] ?? ''}</td>`).join('')}</tr>
        `).join('');
    },

    confirmFieldMapping() {
        this.fieldMapping.cdr3_column = document.getElementById('cdr3Column')?.value || '';
        this.fieldMapping.copy_column = document.getElementById('copyColumn')?.value || '';
        this.fieldMapping.v_column = document.getElementById('vColumn')?.value || '';
        this.fieldMapping.j_column = document.getElementById('jColumn')?.value || '';

        if (Object.values(this.fieldMapping).some(value => !value)) {
            this.showError('请完成所有字段映射');
            return;
        }

        this.updateStepIndicator(4);
        document.getElementById('step4Card').style.display = '';
    },

    async generateAll() {
        const samples = this.getSelectedSamplesPayload();
        const selectedModules = this.getSelectedModules();
        if (samples.length < 2) {
            this.showError('请至少选择 2 个样本');
            return;
        }
        if (!selectedModules.length) {
            this.showError('请至少选择 1 个生成内容');
            return;
        }

        this.showLoading('正在创建一键分析任务...');
        try {
            const response = await fetch('/api/combined-analysis/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    samples,
                    selected_chains: this.selectedChains,
                    selected_modules: selectedModules,
                    field_mapping: this.fieldMapping,
                    config: {
                        base_path: this.basePath || document.getElementById('basePath')?.value?.trim() || null,
                        output_name: document.getElementById('outputName')?.value?.trim() || null,
                        heatmap_color_scheme: document.getElementById('heatmapColorScheme')?.value || 'viridis',
                        heatmap_annotation: document.getElementById('heatmapAnnotation')?.checked ?? true,
                        treemap_min_copy_default: Number(document.getElementById('treemapMinCopyDefault')?.value || 30),
                        treemap_top_n: Number(document.getElementById('treemapTopN')?.value || 100),
                        treemap_layout_mode: document.getElementById('treemapLayoutMode')?.value || 'tetris',
                        treemap_topclone_only: document.getElementById('treemapTopcloneOnly')?.checked ?? false
                    }
                })
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '创建任务失败');

            this.activeTaskId = data.task_id;
            this.pollTaskStatus(data.task_id);
        } catch (error) {
            this.hideLoading();
            this.showError(error.message || '创建任务失败');
        }
    },

    async pollTaskStatus(taskId) {
        try {
            const response = await fetch(`/api/combined-analysis/task/${encodeURIComponent(taskId)}`);
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '读取任务状态失败');

            this.updateProgress(data.progress, data.stage, data.detail, data.history || []);

            if (data.status === 'completed') {
                this.stopTaskPolling();
                this.hideLoading();
                this.result = data.result;
                document.getElementById('resultsCard').style.display = '';
                document.getElementById('resultSummary').className =
                    `alert ${data.result.failed_modules?.length ? 'alert-warning' : 'alert-success'} mb-3`;
                document.getElementById('resultSummary').textContent = data.result.summary || '结果已生成';
                this.renderModuleResults(data.result.modules || {}, data.result.selected_modules || []);
                await this.registerProjectResult(data.result);
                return;
            }

            if (data.status === 'failed') {
                this.stopTaskPolling();
                this.hideLoading();
                throw new Error(data.detail || data.error || '任务执行失败');
            }

            this.pollTimer = setTimeout(() => this.pollTaskStatus(taskId), 1500);
        } catch (error) {
            this.stopTaskPolling();
            this.hideLoading();
            this.showError(error.message || '读取任务状态失败');
        }
    },

    renderModuleResults(modules, selectedModules) {
        const container = document.getElementById('moduleResults');
        if (!container) return;

        const moduleOrder = (selectedModules && selectedModules.length)
            ? selectedModules.map(key => [key, this.getModuleLabel(key)])
            : [['heatmap', 'Heatmap'], ['treemap', 'Treemap'], ['chord', 'Chord']];

        container.innerHTML = moduleOrder.map(([key, fallbackLabel]) => {
            const moduleInfo = modules[key] || {};
            const status = moduleInfo.status || 'failed';
            const label = moduleInfo.label || fallbackLabel;
            const message = moduleInfo.message || (
                status === 'completed'
                    ? (moduleInfo.topclone_only
                        ? '结果已生成，本次仅导出 TopClone CSV，可打开结果页或下载 ZIP。'
                        : '结果已生成，可直接打开查看器或下载 ZIP。')
                    : '该模块本次未成功生成。'
            );
            const statusText = status === 'completed' ? '已生成' : '失败';
            const statusClass = status === 'completed' ? 'success' : 'failed';
            const cardClass = status === 'completed' ? 'is-success' : 'is-failed';
            const buttons = [];

            if (moduleInfo.viewer_url) {
                buttons.push(`<button class="btn btn-sm btn-primary" onclick="window.open('${moduleInfo.viewer_url}', '_blank', 'noopener')">打开查看器</button>`);
            }
            if (moduleInfo.zip_url) {
                buttons.push(`<button class="btn btn-sm btn-outline-primary" onclick="window.open('${moduleInfo.zip_url}', '_blank', 'noopener')">下载 ZIP</button>`);
            }
            if (moduleInfo.metadata_url) {
                buttons.push(`<button class="btn btn-sm btn-outline-secondary" onclick="window.open('${moduleInfo.metadata_url}', '_blank', 'noopener')">Metadata</button>`);
            }

            return `
                <div class="module-card ${cardClass}">
                    <div class="d-flex justify-content-between align-items-center gap-2 mb-2">
                        <h3 class="h6 mb-0">${label}</h3>
                        <span class="module-status ${statusClass}">${statusText}</span>
                    </div>
                    <div class="text-muted small mb-3">${message}</div>
                    <div class="d-flex flex-wrap gap-2">
                        ${buttons.length ? buttons.join('') : '<span class="text-muted small">无可用输出</span>'}
                    </div>
                </div>
            `;
        }).join('');
    },

    getModuleLabel(key) {
        const labels = {
            heatmap: 'Heatmap',
            treemap: 'Treemap',
            chord: 'Chord'
        };
        return labels[key] || (key ? key.charAt(0).toUpperCase() + key.slice(1) : 'Module');
    },

    async registerProjectResult(result) {
        const context = this.projectContext || this.getProjectContext();
        if (!context.projectId || !result?.output_base) return;

        const analysisType = context.analysisType || context.activeModule || 'combined-analysis';
        try {
            await fetch(`/api/projects/${encodeURIComponent(context.projectId)}/analysis/${encodeURIComponent(analysisType)}/register-result`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    job_id: result.job_id || '',
                    output_base: result.output_base || '',
                    report_path: result.report_path || '',
                    report_url: result.viewer_url || '',
                    viewer_url: result.viewer_url || '',
                    metadata_url: result.metadata_url || '',
                    metadata: {
                        selected_modules: result.selected_modules || [],
                        failed_modules: result.failed_modules || [],
                        summary: result.summary || ''
                    }
                })
            });
        } catch (error) {
            console.warn('Failed to register combined analysis result for project:', error);
        }
    },

    openCombinedViewer() {
        if (!this.result?.viewer_url) {
            this.showError('总览页尚未生成');
            return;
        }
        window.open(this.result.viewer_url, '_blank', 'noopener');
    },

    openMetadata() {
        if (!this.result?.metadata_url) {
            this.showError('metadata 尚未生成');
            return;
        }
        window.open(this.result.metadata_url, '_blank', 'noopener');
    }
};

document.addEventListener('DOMContentLoaded', () => CombinedAnalysis.init());
