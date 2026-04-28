const ScriptHubPage = {
    projectContext: null,
    inspectData: null,
    result: null,
    activeTaskId: null,
    taskPollTimer: null,
    syncPollTimer: null,
    dataSourceMode: 'local',
    activeModule: 'db-alignment',
    remoteSources: [],
    remoteSourceId: '',
    remoteBrowsePath: '',
    remoteSelectedPath: '',
    remoteParentPath: null,
    remoteEntries: [],
    uiState: 'idle',
    touchedFields: new Set(),
    lastInspectedBasePath: '',
    isApplyingAutoValues: false,

    CONFIG_FIELD_IDS: [
        'scriptHubOutputName',
        'scriptHubCdr3Column',
        'scriptHubCopyColumn',
        'scriptHubProfilePath',
        'scriptHubCategories',
        'scriptHubPathologyFilter',
        'scriptHubPathologyValues',
    ],

    init() {
        this.bindEvents();
        this.projectContext = this.getProjectContext();
        this.dataSourceMode = document.getElementById('scriptHubDataSourceMode')?.value || 'local';
        this.activeModule = document.getElementById('scriptHubModule')?.value || 'db-alignment';
        this.toggleDataSourceMode(this.dataSourceMode);
        this.syncModuleUI();
        this.loadRemoteSources();
        this.initializeProjectContext();
        this.syncStageUI();
    },

    bindEvents() {
        document.getElementById('scriptHubDataSourceMode')?.addEventListener('change', (event) => {
            this.toggleDataSourceMode(event.target.value || 'local');
        });
        document.getElementById('scriptHubModule')?.addEventListener('change', (event) => {
            this.switchModule(event.target.value || 'db-alignment');
        });
        document.getElementById('scriptHubInspectBtn')?.addEventListener('click', () => this.inspectBasePath());
        document.getElementById('scriptHubRunBtn')?.addEventListener('click', () => this.runDbAlignment());
        document.getElementById('scriptHubRemoteSourceSelect')?.addEventListener('change', () => this.handleRemoteSourceChange());
        document.getElementById('scriptHubBrowseRemoteRootBtn')?.addEventListener('click', () => this.browseRemoteRoot());
        document.getElementById('scriptHubBrowseRemoteParentBtn')?.addEventListener('click', () => this.browseRemoteParent());
        document.getElementById('scriptHubSelectRemoteCurrentBtn')?.addEventListener('click', () => this.selectCurrentRemotePath());
        document.getElementById('scriptHubTestRemoteBtn')?.addEventListener('click', () => this.testRemoteSource());
        document.getElementById('scriptHubSyncRemoteBtn')?.addEventListener('click', () => this.syncRemoteAndInspect());
        document.getElementById('scriptHubOpenViewerBtn')?.addEventListener('click', () => this.openResultUrl('viewer_url'));
        document.getElementById('scriptHubOpenZipBtn')?.addEventListener('click', () => this.openResultUrl('zip_url'));
        document.getElementById('scriptHubOpenMetadataBtn')?.addEventListener('click', () => this.openResultUrl('metadata_url'));
        document.getElementById('scriptHubOpenBpMetadataBtn')?.addEventListener('click', () => this.openResultUrl('metadata_url'));
        document.getElementById('scriptHubBasePath')?.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                this.inspectBasePath();
            }
        });

        this.CONFIG_FIELD_IDS.forEach((fieldId) => {
            const element = document.getElementById(fieldId);
            if (!element) return;
            const eventName = element.tagName === 'SELECT' || element.type === 'checkbox' ? 'change' : 'input';
            element.addEventListener(eventName, () => this.markFieldTouched(fieldId));
        });
    },

    getProjectContext() {
        const params = new URLSearchParams(window.location.search);
        return {
            projectId: params.get('project_id') || '',
            projectName: params.get('project_name') || '',
            basePath: params.get('base_path') || '',
            autoScan: params.get('auto_scan') === '1',
            analysisType: params.get('analysis_type') || 'script-hub',
        };
    },

    initializeProjectContext() {
        const context = this.projectContext || this.getProjectContext();
        if (context.basePath) {
            const basePathInput = document.getElementById('scriptHubBasePath');
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
                        <div class="small">Current project: ${this.escapeHtml(context.projectName || context.projectId)}. Script Hub will use the project asset root as the default base path.</div>
                    </div>
                    <a class="btn btn-sm btn-outline-primary" href="/projects/${encodeURIComponent(context.projectId)}">Back to project</a>
                `;
                container.insertBefore(banner, container.firstChild);
            }
        }

        if (context.autoScan && context.basePath && !this._autoInspectTriggered) {
            this._autoInspectTriggered = true;
            this.inspectBasePath(context.basePath);
        }
    },

    toggleDataSourceMode(mode = 'local') {
        this.dataSourceMode = mode;
        document.getElementById('scriptHubLocalPanel')?.classList.toggle('sh-hidden', mode !== 'local');
        document.getElementById('scriptHubRemotePanel')?.classList.toggle('sh-hidden', mode !== 'remote');
        if (mode === 'remote' && this.remoteSourceId && !this.remoteBrowsePath) {
            this.browseRemoteRoot();
        }
    },

    switchModule(moduleKey = 'db-alignment') {
        this.activeModule = moduleKey;
        this.resetDownstreamState();
        this.syncModuleUI();
    },

    syncModuleUI() {
        const module = this.activeModule || 'db-alignment';
        const isBoxPlot = module === 'boxplot';

        document.querySelectorAll('[data-module]').forEach((el) => {
            const allowed = el.getAttribute('data-module');
            if (allowed === module) {
                el.style.display = '';
            } else {
                el.style.display = 'none';
            }
        });

        document.getElementById('scriptHubRunBtnLabel').textContent = isBoxPlot ? 'Run BoxPlot Analysis' : 'Run DB Alignment';
        document.getElementById('scriptHubConfigHint').textContent = isBoxPlot
            ? 'Classification and parameter ranges can be adjusted before running the BoxPlot analysis.'
            : '字段与 Profile 设置会基于检测结果自动填充；之后你可以逐项修改。';
        document.getElementById('scriptHubResultSummary').textContent = isBoxPlot ? 'BoxPlot analysis completed.' : 'DB alignment completed.';
        document.getElementById('scriptHubResultMeta').textContent = isBoxPlot
            ? '任务完成后在这里查看 BoxPlot 结果、PNGs 和 p-value CSVs。'
            : '任务完成后在这里查看输出、下载结果或打开 viewer。';

        const inspectBtn = document.getElementById('scriptHubInspectBtn');
        if (inspectBtn) {
            inspectBtn.querySelector('i').className = isBoxPlot ? 'bi bi-table me-1' : 'bi bi-search me-1';
            const btnLabel = document.getElementById('scriptHubInspectBtnLabel');
            if (btnLabel) btnLabel.textContent = isBoxPlot ? 'Detect Datapoint' : 'Detect Assets';
        }
    },

    showError(message) {
        alert(message);
    },

    escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    },

    setUiState(nextState) {
        this.uiState = nextState || 'idle';
        this.syncStageUI();
    },

    syncStageUI() {
        const assetsVisible = ['inspected', 'running', 'completed'].includes(this.uiState);
        const configVisible = ['inspected', 'running', 'completed'].includes(this.uiState);
        const resultVisible = this.uiState === 'completed';

        this.toggleStage('scriptHubAssetsStage', assetsVisible);
        this.toggleStage('scriptHubConfigStage', configVisible);
        this.toggleStage('scriptHubResultStage', resultVisible);

        this.setStageStatus(
            'scriptHubSourceState',
            this.uiState === 'running'
                ? { text: 'Source locked', tone: 'warning' }
                : this.uiState === 'completed'
                    ? { text: 'Ready', tone: 'success' }
                    : this.uiState === 'inspected'
                        ? { text: 'Detected', tone: 'success' }
                        : this.uiState === 'inspecting'
                            ? { text: 'Inspecting', tone: 'active' }
                            : { text: 'Awaiting input', tone: 'active' }
        );

        this.setStageStatus(
            'scriptHubAssetsState',
            resultVisible || configVisible
                ? { text: 'Detected', tone: 'success' }
                : { text: 'Hidden', tone: 'default' }
        );

        this.setStageStatus(
            'scriptHubConfigState',
            this.uiState === 'running'
                ? { text: 'Running', tone: 'warning' }
                : this.uiState === 'completed'
                    ? { text: 'Applied', tone: 'success' }
                    : configVisible
                        ? { text: 'Ready to edit', tone: 'active' }
                        : { text: 'Locked', tone: 'default' }
        );

        this.setStageStatus(
            'scriptHubResultState',
            this.uiState === 'completed'
                ? { text: 'Ready', tone: 'success' }
                : this.uiState === 'running'
                    ? { text: 'Waiting', tone: 'warning' }
                    : { text: 'Waiting', tone: 'default' }
        );
    },

    toggleStage(stageId, visible) {
        const stage = document.getElementById(stageId);
        if (!stage) return;
        stage.classList.toggle('sh-hidden', !visible);
        stage.classList.toggle('is-visible', Boolean(visible));
    },

    setStageStatus(elementId, config) {
        const element = document.getElementById(elementId);
        if (!element) return;
        const tone = config?.tone || 'default';
        element.textContent = config?.text || '';
        element.classList.remove('is-active', 'is-success', 'is-warning');
        if (tone === 'active') element.classList.add('is-active');
        if (tone === 'success') element.classList.add('is-success');
        if (tone === 'warning') element.classList.add('is-warning');
    },

    showSourceFeedback(message, tone = 'info') {
        const feedback = document.getElementById('scriptHubSourceFeedback');
        if (!feedback) return;
        feedback.className = `alert alert-${tone} sh-source-feedback is-visible`;
        feedback.textContent = message || '';
    },

    showLoading(text = '处理中...', stage = '处理中...') {
        const overlay = document.getElementById('scriptHubLoadingOverlay');
        if (!overlay) return;
        document.getElementById('scriptHubLoadingStage').textContent = stage;
        document.getElementById('scriptHubLoadingText').textContent = text;
        this.updateLoadingProgress(0, stage, text, []);
        overlay.style.display = 'flex';
    },

    hideLoading() {
        const overlay = document.getElementById('scriptHubLoadingOverlay');
        if (overlay) overlay.style.display = 'none';
    },

    updateLoadingProgress(progress, stage, detail, history = []) {
        const value = Math.max(0, Math.min(100, Number(progress || 0)));
        const progressBar = document.getElementById('scriptHubLoadingProgressBar');
        if (progressBar) {
            progressBar.style.width = `${value}%`;
            progressBar.setAttribute('aria-valuenow', String(value));
            progressBar.textContent = `${Math.round(value)}%`;
        }
        document.getElementById('scriptHubLoadingStage').textContent = stage || '处理中...';
        document.getElementById('scriptHubLoadingText').textContent = detail || '';

        const logEl = document.getElementById('scriptHubLoadingLog');
        if (!logEl) return;
        logEl.innerHTML = Array.isArray(history) && history.length
            ? history.slice().reverse().map((item) => `
                <div class="mb-2">
                    <div class="fw-semibold">${this.escapeHtml(item.stage || '处理中')} <span class="text-muted">(${Math.round(item.progress || 0)}%)</span></div>
                    <div class="text-muted small">${this.escapeHtml(item.timestamp || '')}</div>
                    <div>${this.escapeHtml(item.detail || '')}</div>
                </div>
            `).join('')
            : '等待任务开始。';
    },

    setInspectSummary(message, tone = 'info') {
        const summary = document.getElementById('scriptHubInspectSummary');
        if (!summary) return;
        summary.className = `alert alert-${tone} mb-3`;
        summary.textContent = message || '';
    },

    updateRemoteHint(message, tone = 'secondary') {
        const hint = document.getElementById('scriptHubRemoteHint');
        if (!hint) return;
        hint.className = `alert alert-${tone} mb-3`;
        hint.textContent = message || '';
    },

    updateRemotePathDisplay() {
        const currentPathEl = document.getElementById('scriptHubRemoteCurrentPath');
        const selectedPathEl = document.getElementById('scriptHubRemoteSelectedPath');
        if (currentPathEl) currentPathEl.textContent = this.remoteBrowsePath || '-';
        if (selectedPathEl) selectedPathEl.textContent = this.remoteSelectedPath || '-';
    },

    markFieldTouched(fieldId) {
        if (this.isApplyingAutoValues) return;
        this.touchedFields.add(fieldId);
    },

    clearTouchedFields() {
        this.touchedFields = new Set();
    },

    shouldPreserveField(fieldId) {
        return this.touchedFields.has(fieldId);
    },

    applyAutoValue(fieldId, nextValue, { force = false } = {}) {
        const element = document.getElementById(fieldId);
        if (!element) return;

        const normalizedValue = element.type === 'checkbox'
            ? Boolean(nextValue)
            : String(nextValue ?? '');
        const currentValue = element.type === 'checkbox'
            ? Boolean(element.checked)
            : String(element.value ?? '');
        const preserve = !force && this.shouldPreserveField(fieldId) && currentValue !== '';

        if (preserve) return;

        this.isApplyingAutoValues = true;
        if (element.type === 'checkbox') {
            element.checked = normalizedValue;
        } else {
            element.value = normalizedValue;
        }
        this.isApplyingAutoValues = false;
    },

    resetDownstreamState() {
        this.inspectData = null;
        this.result = null;
        this.activeTaskId = null;
        this.stopTaskPolling();
        this.setInspectSummary('等待检测目录。', 'info');
        document.getElementById('scriptHubResultLog').textContent = '等待结果。';
        document.getElementById('scriptHubResultSummary').textContent = this.activeModule === 'boxplot' ? 'BoxPlot analysis completed.' : 'DB alignment completed.';
        document.getElementById('scriptHubResultMeta').textContent = this.activeModule === 'boxplot'
            ? '任务完成后在这里查看 BoxPlot 结果、PNGs 和 p-value CSVs。'
            : '任务完成后在这里查看输出、下载结果或打开 viewer。';
        document.getElementById('scriptHubPreviewFileMeta').textContent = '等待检测 preview 文件。';
        this.renderPreviewTable([], []);
        document.getElementById('scriptHubDatapointPath').value = '';
        document.getElementById('scriptHubClassBegin').innerHTML = '<option value="">Select column</option>';
        document.getElementById('scriptHubClassOver').innerHTML = '<option value="">Select column</option>';
        document.getElementById('scriptHubParamBegin').innerHTML = '<option value="">Select column</option>';
        document.getElementById('scriptHubParamOver').innerHTML = '<option value="">Select column</option>';
        document.getElementById('scriptHubColumnChips').innerHTML = '<span class="sh-chip">No columns detected</span>';
        document.getElementById('scriptHubBpClassSuggestion').textContent = '-';
        document.getElementById('scriptHubBpParamSuggestion').textContent = '-';
        document.getElementById('scriptHubBpSuggestions')?.classList.add('sh-hidden');
        document.getElementById('scriptHubBoxPlotImages').innerHTML = '';
        document.getElementById('scriptHubBoxPlotPvalueLinks').innerHTML = '';
        this.setUiState('idle');
        this.syncModuleUI();
    },

    async loadRemoteSources() {
        const remoteSourceSelect = document.getElementById('scriptHubRemoteSourceSelect');
        if (!remoteSourceSelect) return;

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
                this.remoteEntries = [];
                this.renderRemoteBrowser();
                this.updateRemoteHint('No SSH data source is configured yet.', 'danger');
                return;
            }

            remoteSourceSelect.disabled = false;
            this.remoteSources.forEach((source) => {
                const option = document.createElement('option');
                option.value = source.id;
                option.textContent = `${source.name} (${source.username}@${source.host}:${source.port})`;
                remoteSourceSelect.appendChild(option);
            });

            this.remoteSourceId = this.remoteSources[0].id;
            remoteSourceSelect.value = this.remoteSourceId;
            this.updateRemoteHint('SSH data sources loaded. Choose a folder and sync it before running the script.', 'secondary');
            if (this.dataSourceMode === 'remote') {
                await this.browseRemoteRoot();
            }
        } catch (error) {
            this.remoteSources = [];
            this.remoteSourceId = '';
            remoteSourceSelect.innerHTML = '<option value="">Failed to load SSH sources</option>';
            remoteSourceSelect.disabled = true;
            this.remoteEntries = [];
            this.renderRemoteBrowser();
            this.updateRemoteHint(error.message, 'danger');
        }
    },

    async handleRemoteSourceChange() {
        const select = document.getElementById('scriptHubRemoteSourceSelect');
        this.remoteSourceId = select ? select.value : '';
        this.remoteBrowsePath = '';
        this.remoteSelectedPath = '';
        this.remoteParentPath = null;
        this.remoteEntries = [];
        this.updateRemotePathDisplay();
        this.renderRemoteBrowser();
        if (this.remoteSourceId) {
            await this.browseRemoteRoot();
        }
    },

    async testRemoteSource() {
        if (!this.remoteSourceId) {
            this.showError('Please select an SSH data source first');
            return;
        }

        this.showLoading('Testing SSH connection...', 'Remote connection');
        try {
            const response = await fetch('/api/remote-sources/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_id: this.remoteSourceId }),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || 'SSH connection test failed');

            this.updateRemoteHint(`SSH connected. Root path: ${data.test_result.root_path}`, 'success');
            await this.browseRemoteRoot();
        } catch (error) {
            this.updateRemoteHint(error.message, 'danger');
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    },

    async browseRemoteRoot() {
        await this.browseRemote();
    },

    async browseRemoteParent() {
        if (!this.remoteParentPath) return;
        await this.browseRemote(this.remoteParentPath);
    },

    async browseRemote(path) {
        if (!this.remoteSourceId) return;

        this.showLoading('Loading remote folders...', 'Remote browser');
        try {
            const body = { source_id: this.remoteSourceId };
            if (path) {
                body.path = path;
            }
            const response = await fetch('/api/remote-sources/browse', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || 'Failed to browse remote directory');

            this.remoteBrowsePath = data.current_path || path;
            this.remoteParentPath = data.parent_path || null;
            this.remoteEntries = Array.isArray(data.entries) ? data.entries : [];
            if (!this.remoteSelectedPath) {
                this.remoteSelectedPath = this.remoteBrowsePath;
            }
            this.updateRemotePathDisplay();
            this.renderRemoteBrowser();
            this.updateRemoteHint(`Browsing ${data.source?.name || this.remoteSourceId}: ${this.remoteBrowsePath}`, 'info');
        } catch (error) {
            this.updateRemoteHint(error.message, 'danger');
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    },

    renderRemoteBrowser() {
        const container = document.getElementById('scriptHubRemoteBrowserList');
        if (!container) return;

        if (!this.remoteEntries.length) {
            container.innerHTML = '<div class="text-muted small p-3">No remote directory loaded yet.</div>';
            return;
        }

        container.innerHTML = this.remoteEntries.map((entry) => `
            <div class="remote-browser-item${this.remoteSelectedPath === entry.path ? ' selected' : ''}">
                <div class="fw-semibold mb-2">${this.escapeHtml(entry.name || entry.path)}</div>
                <div class="remote-browser-path text-muted mb-3">${this.escapeHtml(entry.path || '')}</div>
                <div class="small text-muted mb-3">${entry.is_dir ? 'Directory' : `File ${this.escapeHtml(String(entry.size || 0))} bytes`}</div>
                <div class="d-flex flex-wrap gap-2">
                    ${entry.is_dir ? `<button class="btn btn-outline-secondary btn-sm" data-remote-browse="${this.escapeHtml(entry.path)}">进入</button>` : ''}
                    ${entry.is_dir ? `<button class="btn btn-outline-primary btn-sm" data-remote-select="${this.escapeHtml(entry.path)}">选择此目录</button>` : ''}
                </div>
            </div>
        `).join('');

        container.querySelectorAll('[data-remote-browse]').forEach((button) => {
            button.addEventListener('click', () => this.browseRemote(button.dataset.remoteBrowse || ''));
        });
        container.querySelectorAll('[data-remote-select]').forEach((button) => {
            button.addEventListener('click', () => {
                this.remoteSelectedPath = button.dataset.remoteSelect || '';
                this.updateRemotePathDisplay();
                this.renderRemoteBrowser();
            });
        });
    },

    selectCurrentRemotePath() {
        if (!this.remoteBrowsePath) {
            this.showError('There is no remote folder selected yet');
            return;
        }
        this.remoteSelectedPath = this.remoteBrowsePath;
        this.updateRemotePathDisplay();
        this.renderRemoteBrowser();
    },

    stopSyncPolling() {
        if (this.syncPollTimer) {
            clearTimeout(this.syncPollTimer);
            this.syncPollTimer = null;
        }
    },

    async syncRemoteAndInspect() {
        if (!this.remoteSourceId) {
            this.showError('Please select an SSH data source first');
            return;
        }
        if (!this.remoteSelectedPath) {
            this.showError('Please select a remote folder to sync');
            return;
        }

        this.showLoading('Syncing remote folder...', 'Remote sync');
        this.setUiState('inspecting');
        this.showSourceFeedback(`Syncing remote path ${this.remoteSelectedPath} before inspection.`, 'secondary');
        try {
            const response = await fetch('/api/remote-sources/sync', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source_id: this.remoteSourceId,
                    remote_path: this.remoteSelectedPath,
                }),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || 'Failed to sync remote folder');

            this.stopSyncPolling();
            this.pollSyncTaskStatus(data.task_id);
        } catch (error) {
            this.hideLoading();
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.showSourceFeedback(error.message || 'Remote sync failed.', 'danger');
            this.showError(error.message);
        }
    },

    async pollSyncTaskStatus(taskId) {
        try {
            const response = await fetch(`/api/remote-sources/sync-task/${encodeURIComponent(taskId)}`);
            const data = await response.json();
            if (!data.success) throw new Error(data.message || 'Failed to read sync task status');

            this.updateLoadingProgress(data.progress, data.stage, data.detail, data.history || []);

            if (data.status === 'completed') {
                this.stopSyncPolling();
                const localCachePath = data.result?.local_cache_path || '';
                document.getElementById('scriptHubBasePath').value = localCachePath;
                await this.inspectBasePath(localCachePath, '正在检测同步后的本地缓存目录...');
                return;
            }

            if (data.status === 'failed') {
                this.stopSyncPolling();
                this.hideLoading();
                this.setUiState(this.inspectData ? 'inspected' : 'idle');
                this.showSourceFeedback(data.error || data.detail || 'Remote sync failed.', 'danger');
                this.showError(data.error || data.detail || 'Remote sync failed');
                return;
            }

            this.syncPollTimer = setTimeout(() => this.pollSyncTaskStatus(taskId), 1000);
        } catch (error) {
            this.stopSyncPolling();
            this.hideLoading();
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.showSourceFeedback(error.message || 'Remote sync failed.', 'danger');
            this.showError(error.message);
        }
    },

    populateFieldSelect(selectId, columns, selectedValue) {
        const select = document.getElementById(selectId);
        if (!select) return;

        const safeColumns = Array.isArray(columns) ? columns : [];
        const previousValue = String(select.value || '');
        select.innerHTML = safeColumns.length
            ? safeColumns.map((column) => `<option value="${this.escapeHtml(column)}">${this.escapeHtml(column)}</option>`).join('')
            : '<option value="">No columns detected</option>';

        if (previousValue && safeColumns.includes(previousValue)) {
            select.value = previousValue;
        } else if (selectedValue && safeColumns.includes(selectedValue)) {
            select.value = selectedValue;
        } else if (safeColumns.length) {
            select.value = safeColumns[0];
        }
    },

    renderPreviewTable(columns, rows) {
        const table = document.getElementById('scriptHubPreviewTable');
        if (!table) return;

        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');
        const safeColumns = Array.isArray(columns) ? columns : [];
        const safeRows = Array.isArray(rows) ? rows : [];

        if (!safeColumns.length) {
            thead.innerHTML = '';
            tbody.innerHTML = '<tr><td class="text-muted">No preview data</td></tr>';
            return;
        }

        thead.innerHTML = `<tr>${safeColumns.map((column) => `<th>${this.escapeHtml(column)}</th>`).join('')}</tr>`;
        tbody.innerHTML = safeRows.length
            ? safeRows.map((row) => `<tr>${safeColumns.map((_, index) => `<td>${this.escapeHtml(row[index] ?? '')}</td>`).join('')}</tr>`).join('')
            : '<tr><td class="text-muted" colspan="99">No preview rows</td></tr>';
    },

    renderInspection(data) {
        const previousBasePath = this.lastInspectedBasePath;
        const nextBasePath = String(data.base_path || '');
        const isNewInspectionContext = previousBasePath && previousBasePath !== nextBasePath;

        if (isNewInspectionContext) {
            this.clearTouchedFields();
        }

        this.inspectData = data;
        this.result = null;
        this.lastInspectedBasePath = nextBasePath;
        this.setUiState('inspected');

        this.showSourceFeedback(
            `Inspection completed. Detected ${data.sample_count || 0} sample(s) from ${data.base_path || 'the selected directory'}.`,
            'success'
        );
        this.setInspectSummary(data.summary || `Detected ${data.sample_count || 0} sample(s) for DB alignment.`, 'success');

        const summaryGrid = document.getElementById('scriptHubSummaryGrid');
        if (summaryGrid) {
            summaryGrid.innerHTML = `
                <div class="sh-metric">
                    <span class="sh-metric-label">Samples</span>
                    <div class="sh-metric-value">${this.escapeHtml(String(data.sample_count || 0))}</div>
                </div>
                <div class="sh-metric">
                    <span class="sh-metric-label">Chains</span>
                    <div class="sh-metric-value">${this.escapeHtml((data.selected_chains || []).join(', ') || '-')}</div>
                </div>
                <div class="sh-metric">
                    <span class="sh-metric-label">Pep Files</span>
                    <div class="sh-metric-value">${this.escapeHtml(String(data.pep_file_count || 0))}</div>
                </div>
                <div class="sh-metric">
                    <span class="sh-metric-label">Profile</span>
                    <div class="sh-metric-value">${this.escapeHtml(data.profile_path || 'Auto not found')}</div>
                </div>
            `;
        }

        const samplePreview = document.getElementById('scriptHubSamplePreview');
        if (samplePreview) {
            const sampleItems = Array.isArray(data.sample_preview) ? data.sample_preview : [];
            samplePreview.innerHTML = sampleItems.length
                ? sampleItems.map((item) => `
                    <span class="sh-chip">
                        <strong>${this.escapeHtml(item.sample_name || '')}</strong>
                        <span class="text-muted">${this.escapeHtml((item.chains || []).join('/'))}</span>
                    </span>
                `).join('')
                : '<span class="sh-chip">No sample detected</span>';
        }

        const categoryChips = document.getElementById('scriptHubCategoryChips');
        const availableCategories = Array.isArray(data.available_categories) ? data.available_categories : [];
        if (categoryChips) {
            categoryChips.innerHTML = availableCategories.length
                ? availableCategories.map((item) => `<span class="sh-chip">${this.escapeHtml(item)}</span>`).join('')
                : '<span class="sh-chip">No profile columns</span>';
        }

        const datapointChips = document.getElementById('scriptHubDatapointChips');
        const datapointCandidates = Array.isArray(data.datapoint_candidates) ? data.datapoint_candidates : [];
        if (datapointChips) {
            datapointChips.innerHTML = datapointCandidates.length
                ? datapointCandidates.map((item) => `<span class="sh-chip">${this.escapeHtml(item)}</span>`).join('')
                : '<span class="sh-chip">No datapoint file detected</span>';
        }

        this.populateFieldSelect('scriptHubCdr3Column', data.preview_columns || [], data.resolved_field_mapping?.cdr3_column || '');
        this.populateFieldSelect('scriptHubCopyColumn', data.preview_columns || [], data.resolved_field_mapping?.copy_column || '');
        this.applyAutoValue('scriptHubCdr3Column', data.resolved_field_mapping?.cdr3_column || '', { force: isNewInspectionContext || !previousBasePath });
        this.applyAutoValue('scriptHubCopyColumn', data.resolved_field_mapping?.copy_column || '', { force: isNewInspectionContext || !previousBasePath });
        this.applyAutoValue('scriptHubProfilePath', data.profile_path || '', { force: isNewInspectionContext || !previousBasePath });

        const defaultCategories = availableCategories.filter((item) => ['therapy', 'disease'].includes(String(item).toLowerCase()));
        const fallbackCategories = defaultCategories.length ? defaultCategories : availableCategories.slice(0, 2);
        this.applyAutoValue('scriptHubCategories', fallbackCategories.join(','), { force: isNewInspectionContext || !previousBasePath });

        document.getElementById('scriptHubPreviewFileMeta').textContent = data.preview_file_path
            ? `Preview file: ${data.preview_file_path}`
            : 'No preview file detected.';
        document.getElementById('scriptHubConfigHint').textContent = data.preview_file_path
            ? `Auto-filled from ${data.preview_file_path}. You can adjust any value before running.`
            : 'Field suggestions are based on the current inspection result. You can adjust any value before running.';
        this.renderPreviewTable(data.preview_columns || [], data.preview_rows || []);

        document.getElementById('scriptHubResultLog').textContent = '等待结果。';
        document.getElementById('scriptHubResultSummary').textContent = 'DB alignment completed.';
        document.getElementById('scriptHubResultMeta').textContent = '任务完成后在这里查看输出、下载结果或打开 viewer。';

        window.setTimeout(() => {
            document.getElementById('scriptHubAssetsStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 80);
    },

    async inspectBasePath(explicitBasePath = '', loadingText = 'Scanning asset directory...') {
        const module = this.activeModule || 'db-alignment';
        if (module === 'boxplot') {
            return this.inspectBoxPlot(explicitBasePath, loadingText);
        }

        const basePath = explicitBasePath || document.getElementById('scriptHubBasePath')?.value?.trim() || '';
        if (!basePath) {
            this.showSourceFeedback('Please provide a base path first.', 'warning');
            this.showError('Please provide a base path first');
            return;
        }

        this.setUiState('inspecting');
        this.showSourceFeedback(`Inspecting ${basePath}...`, 'secondary');
        this.showLoading(loadingText, 'Inspect assets');
        try {
            const response = await fetch('/api/script-hub/db-alignment/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    base_path: basePath,
                    profile_path: document.getElementById('scriptHubProfilePath')?.value?.trim() || null,
                    field_mapping: {
                        cdr3_column: document.getElementById('scriptHubCdr3Column')?.value || '',
                        copy_column: document.getElementById('scriptHubCopyColumn')?.value || '',
                    },
                }),
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to inspect DB alignment assets');
            }

            document.getElementById('scriptHubBasePath').value = data.base_path || basePath;
            this.renderInspection(data);
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.setInspectSummary(error.message || 'Asset inspection failed', 'danger');
            this.showSourceFeedback(error.message || 'Asset inspection failed.', 'danger');
            this.showError(error.message || 'Asset inspection failed');
        } finally {
            this.hideLoading();
        }
    },

    async inspectBoxPlot(explicitBasePath = '', loadingText = 'Scanning for Datapoint files...') {
        const basePath = explicitBasePath || document.getElementById('scriptHubBasePath')?.value?.trim() || '';
        const sourceId = this.remoteSourceId || '';
        const remotePath = this.remoteSelectedPath || '';

        if (!basePath && !(sourceId && remotePath)) {
            this.showSourceFeedback('Please provide a base path or select a remote directory first.', 'warning');
            this.showError('Please provide a base path or select a remote directory first');
            return;
        }

        this.setUiState('inspecting');
        this.showSourceFeedback(`Inspecting for BoxPlot datapoint...`, 'secondary');
        this.showLoading(loadingText || 'Scanning for Datapoint files...', 'Inspect BoxPlot assets');
        try {
            const body = {};
            if (!explicitBasePath && sourceId && remotePath && this.dataSourceMode === 'remote') {
                body.source_id = sourceId;
                body.remote_path = remotePath;
            } else {
                body.base_path = basePath;
            }

            const response = await fetch('/api/script-hub/boxplot/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to inspect BoxPlot assets');
            }

            this.inspectData = data;
            this.result = null;
            this.lastInspectedBasePath = basePath;
            this.setUiState('inspected');

            this.showSourceFeedback(
                `BoxPlot inspection completed. Detected ${data.column_count || 0} columns in ${data.datapoint_path || 'the datapoint file'}.`,
                'success'
            );
            this.setInspectSummary(`Datapoint: ${data.datapoint_path} — ${data.column_count} columns`, 'success');

            const summaryGrid = document.getElementById('scriptHubSummaryGrid');
            if (summaryGrid) {
                summaryGrid.innerHTML = `
                    <div class="sh-metric">
                        <span class="sh-metric-label">Datapoint</span>
                        <div class="sh-metric-value sh-path-block">${this.escapeHtml(data.datapoint_path || '-')}</div>
                    </div>
                    <div class="sh-metric">
                        <span class="sh-metric-label">Columns</span>
                        <div class="sh-metric-value">${this.escapeHtml(String(data.column_count || 0))}</div>
                    </div>
                `;
            }

            document.getElementById('scriptHubColumnCount').textContent = data.column_count || 0;
            const columns = Array.isArray(data.columns) ? data.columns : [];
            document.getElementById('scriptHubColumnChips').innerHTML = columns.length
                ? columns.map((col) => `<span class="sh-chip">${this.escapeHtml(col)}</span>`).join('')
                : '<span class="sh-chip">No columns detected</span>';

            const classBegin = document.getElementById('scriptHubClassBegin');
            const classOver = document.getElementById('scriptHubClassOver');
            const paramBegin = document.getElementById('scriptHubParamBegin');
            const paramOver = document.getElementById('scriptHubParamOver');

            [classBegin, classOver, paramBegin, paramOver].forEach((select) => {
                select.innerHTML = columns.map((col) => `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`).join('');
            });

            if (classBegin && columns.length) classBegin.value = data.suggested_classification_begin || columns[0];
            if (classOver && columns.length) classOver.value = data.suggested_classification_over || columns[0];
            if (paramBegin && columns.length) paramBegin.value = data.suggested_param_begin || columns[0];
            if (paramOver && columns.length) paramOver.value = data.suggested_param_over || (columns.length > 1 ? columns[columns.length - 1] : columns[0]);

            document.getElementById('scriptHubDatapointPath').value = data.datapoint_path || '';
            document.getElementById('scriptHubBpClassSuggestion').textContent = `${data.suggested_classification_begin || '-'} → ${data.suggested_classification_over || '-'}`;
            document.getElementById('scriptHubBpParamSuggestion').textContent = `${data.suggested_param_begin || '-'} → ${data.suggested_param_over || '-'}`;
            document.getElementById('scriptHubBpSuggestions')?.classList.remove('sh-hidden');

            document.getElementById('scriptHubResultLog').textContent = '等待结果。';
            document.getElementById('scriptHubResultSummary').textContent = 'BoxPlot analysis completed.';
            document.getElementById('scriptHubResultMeta').textContent = '任务完成后在这里查看 BoxPlot 结果、PNGs 和 p-value CSVs。';

            window.setTimeout(() => {
                document.getElementById('scriptHubAssetsStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 80);
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.setInspectSummary(error.message || 'BoxPlot inspection failed', 'danger');
            this.showSourceFeedback(error.message || 'BoxPlot inspection failed.', 'danger');
            this.showError(error.message || 'BoxPlot inspection failed');
        } finally {
            this.hideLoading();
        }
    },

    collectRunPayload() {
        if (this.activeModule === 'boxplot') {
            const datapointPath = document.getElementById('scriptHubDatapointPath')?.value?.trim() || '';
            if (!datapointPath || !this.inspectData) {
                throw new Error('Please inspect a datapoint file before running BoxPlot');
            }
            const sourceId = this.remoteSourceId || null;
            const remotePath = this.dataSourceMode === 'remote' ? (this.remoteSelectedPath || null) : null;
            return {
                module: 'boxplot',
                datapoint_path: datapointPath,
                classification_begin: document.getElementById('scriptHubClassBegin')?.value || '',
                classification_over: document.getElementById('scriptHubClassOver')?.value || '',
                param_begin: document.getElementById('scriptHubParamBegin')?.value || '',
                param_over: document.getElementById('scriptHubParamOver')?.value || '',
                pvalue_threshold: parseFloat(document.getElementById('scriptHubPvalueThreshold')?.value || '0.05'),
                output_name: document.getElementById('scriptHubOutputName')?.value?.trim() || null,
                source_id: sourceId,
                remote_path: remotePath,
            };
        }

        const basePath = document.getElementById('scriptHubBasePath')?.value?.trim() || '';
        if (!basePath || !this.inspectData) {
            throw new Error('Please inspect a base path before running the script');
        }
        return {
            module: 'db-alignment',
            base_path: basePath,
            output_name: document.getElementById('scriptHubOutputName')?.value?.trim() || null,
            profile_path: document.getElementById('scriptHubProfilePath')?.value?.trim() || null,
            field_mapping: {
                cdr3_column: document.getElementById('scriptHubCdr3Column')?.value || '',
                copy_column: document.getElementById('scriptHubCopyColumn')?.value || '',
            },
            categories: (document.getElementById('scriptHubCategories')?.value || '')
                .split(',')
                .map((item) => item.trim())
                .filter(Boolean),
            contained_pathology: document.getElementById('scriptHubPathologyFilter')?.checked ?? false,
            pathology_values: (document.getElementById('scriptHubPathologyValues')?.value || '')
                .split(/[\n,]+/)
                .map((item) => item.trim())
                .filter(Boolean),
        };
    },

    async runDbAlignment() {
        try {
            const payload = this.collectRunPayload();
            const module = this.activeModule || 'db-alignment';
            const isBoxPlot = module === 'boxplot';
            const endpoint = isBoxPlot ? '/api/script-hub/boxplot/run' : '/api/script-hub/db-alignment/run';
            const label = isBoxPlot ? 'BoxPlot' : 'DB alignment';

            this.setUiState('running');
            this.showSourceFeedback(`Configuration locked. Submitting ${label} task...`, 'info');
            this.showLoading(`Submitting ${label} task...`, 'Queue task');

            const response = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || `Failed to queue ${label} task`);
            }

            this.activeTaskId = data.task_id;
            this.stopTaskPolling();
            this.pollTaskStatus(data.task_id);
        } catch (error) {
            this.hideLoading();
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.showSourceFeedback(error.message || 'Failed to run analysis.', 'danger');
            this.showError(error.message || 'Failed to run analysis');
        }
    },

    stopTaskPolling() {
        if (this.taskPollTimer) {
            clearTimeout(this.taskPollTimer);
            this.taskPollTimer = null;
        }
    },

    async pollTaskStatus(taskId) {
        try {
            const response = await fetch(`/api/script-hub/task/${encodeURIComponent(taskId)}`);
            const data = await response.json();
            if (!data.success) throw new Error(data.message || 'Failed to read task status');

            this.updateLoadingProgress(data.progress, data.stage, data.detail, data.history || []);

            if (data.status === 'completed') {
                this.stopTaskPolling();
                this.hideLoading();
                this.result = data.result || null;
                this.renderResult(this.result);
                await this.registerProjectResult(this.result);
                return;
            }

            if (data.status === 'failed') {
                this.stopTaskPolling();
                this.hideLoading();
                throw new Error(data.detail || data.error || 'DB alignment failed');
            }

            this.taskPollTimer = setTimeout(() => this.pollTaskStatus(taskId), 1500);
        } catch (error) {
            this.stopTaskPolling();
            this.hideLoading();
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.showSourceFeedback(error.message || 'Failed to read task status.', 'danger');
            this.showError(error.message || 'Failed to read task status');
        }
    },

    renderResult(result) {
        if (!result) return;

        const isBoxPlot = (result.module || '') === 'boxplot';
        this.setUiState('completed');

        if (isBoxPlot) {
            this.renderBoxPlotResult(result);
            return;
        }

        this.showSourceFeedback(`DB alignment completed for ${result.sample_count || 0} sample(s).`, 'success');
        document.getElementById('scriptHubResultSummary').textContent =
            `DB alignment completed for ${result.sample_count || 0} sample(s).`;
        document.getElementById('scriptHubResultMeta').textContent =
            `Chains: ${(result.selected_chains || []).join(', ') || '-'} | Profile: ${result.profile_path || 'not merged'}`;
        document.getElementById('scriptHubResultLog').textContent =
            JSON.stringify(result.metadata || {}, null, 2);

        window.setTimeout(() => {
            document.getElementById('scriptHubResultStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 80);
    },

    renderBoxPlotResult(result) {
        this.showSourceFeedback(`BoxPlot analysis completed. Generated ${result.png_urls?.length || 0} plot(s).`, 'success');
        document.getElementById('scriptHubResultSummary').textContent =
            `BoxPlot analysis completed. Generated ${result.png_urls?.length || 0} plot(s).`;
        document.getElementById('scriptHubResultMeta').textContent =
            `P-value threshold: ${result.metadata?.pvalue_threshold || 0.05} | Classification: ${result.metadata?.classification_begin || '-'} → ${result.metadata?.classification_over || '-'} | Parameters: ${result.metadata?.param_begin || '-'} → ${result.metadata?.param_over || '-'}`;
        document.getElementById('scriptHubResultLog').textContent =
            JSON.stringify(result.metadata || {}, null, 2);

        const imagesContainer = document.getElementById('scriptHubBoxPlotImages');
        if (imagesContainer && result.png_urls) {
            imagesContainer.innerHTML = result.png_urls.map((url) => `
                <div class="sh-boxplot-img-card">
                    <a href="${this.escapeHtml(url)}" target="_blank" rel="noopener">
                        <img src="${this.escapeHtml(url)}" alt="BoxPlot" class="sh-boxplot-thumb" loading="lazy">
                    </a>
                    <div class="small text-muted mt-1 sh-path-block">${this.escapeHtml(url.split('/').pop() || '')}</div>
                </div>
            `).join('');
        }

        const pvalueContainer = document.getElementById('scriptHubBoxPlotPvalueLinks');
        if (pvalueContainer && result.pvalue_urls) {
            pvalueContainer.innerHTML = result.pvalue_urls.map((url) => `
                <a href="${this.escapeHtml(url)}" class="btn btn-sm btn-outline-secondary" target="_blank" rel="noopener" download>
                    <i class="bi bi-download me-1"></i>${this.escapeHtml(url.split('/').pop() || 'pvalues.csv')}
                </a>
            `).join('');
        }

        window.setTimeout(() => {
            document.getElementById('scriptHubResultStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 80);
    },

    openResultUrl(key) {
        const targetUrl = this.result?.[key];
        if (!targetUrl) {
            this.showError('No result file is available for this action');
            return;
        }
        window.open(targetUrl, '_blank', 'noopener');
    },

    async registerProjectResult(result) {
        const context = this.projectContext || this.getProjectContext();
        if (!context.projectId || !result?.output_base) return;

        try {
            await fetch(`/api/projects/${encodeURIComponent(context.projectId)}/analysis/${encodeURIComponent(context.analysisType || 'script-hub')}/register-result`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    job_id: result.job_id || '',
                    output_base: result.output_base || '',
                    report_path: result.report_path || '',
                    report_url: result.viewer_url || '',
                    metadata_url: result.metadata_url || '',
                    zip_url: result.zip_url || '',
                    viewer_url: result.viewer_url || '',
                    metadata: result.metadata || {},
                }),
            });
        } catch (error) {
            console.warn('Failed to register script hub result for project:', error);
        }
    },
};

document.addEventListener('DOMContentLoaded', () => {
    ScriptHubPage.init();
});
