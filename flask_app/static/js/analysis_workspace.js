(function () {
    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function getContainer() {
        return document.querySelector('.container-fluid.py-4');
    }

    function defaultShowError(message) {
        window.alert(message);
    }

    const AnalysisWorkspace = {
        enhance(target, config = {}) {
            if (!target) return target;

            const workspaceConfig = {
                analysisType: config.analysisType || '',
                displayName: config.displayName || 'Analysis',
                projectResultType: config.projectResultType || config.analysisType || '',
            };

            Object.assign(target, {
                workspaceConfig,
                projectContext: null,
                remoteSources: target.remoteSources || [],
                remoteSourceId: target.remoteSourceId || '',
                remoteBrowsePath: target.remoteBrowsePath || '',
                remoteSelectedPath: target.remoteSelectedPath || '',
                remoteParentPath: target.remoteParentPath || null,
                remoteTreeFilter: target.remoteTreeFilter || '',
                remoteBrowserEntries: target.remoteBrowserEntries || [],

                escapeHtml,

                getProjectContext() {
                    if (this.projectContext) return this.projectContext;
                    const params = new URLSearchParams(window.location.search);
                    this.projectContext = {
                        projectId: params.get('project_id') || '',
                        projectName: params.get('project_name') || '',
                        basePath: params.get('base_path') || '',
                        autoScan: params.get('auto_scan') === '1',
                    };
                    return this.projectContext;
                },

                initializeFromProjectContext() {
                    const context = this.getProjectContext();
                    if (!context.projectId) return;

                    const container = getContainer();
                    if (container && !container.querySelector('[data-project-context-banner]')) {
                        const banner = document.createElement('div');
                        banner.className = 'alert alert-primary d-flex justify-content-between align-items-center gap-3';
                        banner.setAttribute('data-project-context-banner', '1');
                        banner.innerHTML = `
                            <div>
                                <div class="fw-semibold">Project workspace enabled</div>
                                <div class="small">Current project: ${escapeHtml(context.projectName || context.projectId)}. ${escapeHtml(this.workspaceConfig.displayName)} will read data directly from the project asset directory.</div>
                            </div>
                            <a class="btn btn-sm btn-outline-primary" href="/projects/${encodeURIComponent(context.projectId)}">Back to project</a>
                        `;
                        container.insertBefore(banner, container.firstChild);
                    }

                    const basePathInput = document.getElementById('basePath');
                    if (basePathInput && context.basePath) {
                        basePathInput.value = context.basePath;
                    }

                    if (context.autoScan && context.basePath && !this._workspaceAutoScanTriggered) {
                        this._workspaceAutoScanTriggered = true;
                        this.scanFolder?.();
                    }
                },

                async registerProjectResult(payload) {
                    const context = this.getProjectContext ? this.getProjectContext() : { projectId: '' };
                    if (!context.projectId || !this.workspaceConfig.projectResultType) return;

                    try {
                        await fetch(`/api/projects/${encodeURIComponent(context.projectId)}/analysis/${encodeURIComponent(this.workspaceConfig.projectResultType)}/register-result`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload || {}),
                        });
                    } catch (error) {
                        console.warn(`Failed to register ${this.workspaceConfig.projectResultType} result for project:`, error);
                    }
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

                resetRemoteTreeState() {
                    this.remoteBrowsePath = '';
                    this.remoteSelectedPath = '';
                    this.remoteParentPath = null;
                    this.remoteTreeFilter = '';
                    this.remoteBrowserEntries = [];
                    const searchInput = document.getElementById('remoteTreeSearch');
                    if (searchInput) searchInput.value = '';
                },

                updateRemoteHint(message, variant = 'secondary') {
                    const hint = document.getElementById('remoteSourceHint');
                    if (!hint) return;
                    hint.className = `alert alert-${variant} mb-3`;
                    hint.textContent = message || '';
                },

                updateRemotePathDisplay() {
                    const currentPathEl = document.getElementById('remoteCurrentPath');
                    const selectedPathEl = document.getElementById('remoteSelectedPath');
                    if (currentPathEl) currentPathEl.textContent = this.remoteBrowsePath || '-';
                    if (selectedPathEl) selectedPathEl.textContent = this.remoteSelectedPath || '-';
                },

                handleRemoteTreeSearch(value) {
                    this.remoteTreeFilter = String(value || '').trim().toLowerCase();
                    this.renderRemoteBrowser();
                },

                renderRemoteBrowser() {
                    const container = document.getElementById('remoteBrowserList');
                    if (!container) return;

                    const entries = Array.isArray(this.remoteBrowserEntries) ? this.remoteBrowserEntries : [];
                    const filter = String(this.remoteTreeFilter || '').trim().toLowerCase();
                    const visibleEntries = filter
                        ? entries.filter((entry) => {
                            const haystack = `${entry.name || ''} ${entry.path || ''}`.toLowerCase();
                            return haystack.includes(filter);
                        })
                        : entries;

                    if (!visibleEntries.length) {
                        container.innerHTML = '<div class="text-muted small p-3">No directories available in the current view.</div>';
                        return;
                    }

                    container.innerHTML = visibleEntries.map((entry) => {
                        const isSelected = this.remoteSelectedPath === entry.path;
                        const rowClass = isSelected ? 'border-primary bg-primary-subtle' : 'border-light-subtle';
                        const actionButton = entry.is_dir
                            ? `<button class="btn btn-sm btn-outline-primary" data-remote-browse="${escapeHtml(entry.path)}">Open</button>`
                            : `<button class="btn btn-sm btn-outline-secondary" data-remote-select="${escapeHtml(entry.path)}">Use file path</button>`;

                        return `
                            <div class="border rounded-3 p-2 mb-2 ${rowClass}">
                                <div class="d-flex justify-content-between align-items-start gap-3">
                                    <div class="min-w-0">
                                        <div class="fw-semibold text-break">${escapeHtml(entry.name || entry.path || '-')}</div>
                                        <div class="small text-muted text-break">${escapeHtml(entry.path || '-')}</div>
                                        <div class="small text-muted">${entry.is_dir ? 'Directory' : 'File'}</div>
                                    </div>
                                    <div class="d-flex flex-column gap-2">
                                        ${actionButton}
                                        ${entry.is_dir ? `<button class="btn btn-sm btn-outline-secondary" data-remote-select="${escapeHtml(entry.path)}">Use folder</button>` : ''}
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('');

                    container.querySelectorAll('[data-remote-browse]').forEach((button) => {
                        button.addEventListener('click', () => this.browseRemotePath(button.dataset.remoteBrowse));
                    });
                    container.querySelectorAll('[data-remote-select]').forEach((button) => {
                        button.addEventListener('click', () => {
                            this.remoteSelectedPath = button.dataset.remoteSelect || '';
                            this.updateRemotePathDisplay();
                            this.renderRemoteBrowser();
                        });
                    });
                },

                async loadRemoteSources() {
                    const remoteSourceSelect = document.getElementById('remoteSourceSelect');
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
                            this.resetRemoteTreeState();
                            this.updateRemotePathDisplay();
                            this.updateRemoteHint('No SSH source is configured on the server.', 'danger');
                            this.renderRemoteBrowser();
                            return;
                        }

                        remoteSourceSelect.disabled = false;
                        this.remoteSources.forEach((source) => {
                            const option = document.createElement('option');
                            option.value = source.id;
                            option.textContent = source.name || source.id;
                            remoteSourceSelect.appendChild(option);
                        });

                        const nextSourceId = this.remoteSources.some((source) => source.id === this.remoteSourceId)
                            ? this.remoteSourceId
                            : this.remoteSources[0].id;
                        this.remoteSourceId = nextSourceId;
                        remoteSourceSelect.value = nextSourceId;
                        this.updateRemoteHint('SSH data sources loaded. Select a remote directory to continue.', 'secondary');

                        if (this.dataSourceMode === 'remote') {
                            await this.browseRemoteRoot();
                        }
                    } catch (error) {
                        this.remoteSources = [];
                        this.remoteSourceId = '';
                        this.resetRemoteTreeState();
                        this.updateRemotePathDisplay();
                        this.updateRemoteHint(error.message, 'danger');
                        this.renderRemoteBrowser();
                    }
                },

                async handleRemoteSourceChange() {
                    const select = document.getElementById('remoteSourceSelect');
                    this.remoteSourceId = select ? select.value : '';
                    this.resetRemoteTreeState();
                    this.updateRemotePathDisplay();
                    this.renderRemoteBrowser();
                    if (this.remoteSourceId) {
                        await this.browseRemoteRoot();
                    }
                },

                async browseRemotePath(path = '', options = {}) {
                    if (!this.remoteSourceId) {
                        (this.showError || defaultShowError)('Please select an SSH data source first');
                        return;
                    }

                    const skipLoading = Boolean(options.skipLoading);
                    if (!skipLoading) this.showLoading?.('Loading remote directory...');

                    try {
                        const response = await fetch('/api/remote-sources/browse', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ source_id: this.remoteSourceId, path }),
                        });
                        const data = await response.json();
                        if (!data.success) {
                            throw new Error(data.message || 'Failed to browse remote directory');
                        }

                        this.remoteBrowsePath = data.current_path || path || '';
                        this.remoteParentPath = data.parent_path || null;
                        this.remoteBrowserEntries = Array.isArray(data.entries) ? data.entries : [];
                        if (!this.remoteSelectedPath) {
                            this.remoteSelectedPath = this.remoteBrowsePath;
                        }
                        this.updateRemotePathDisplay();
                        this.updateRemoteHint(`Browsing ${data.source?.name || this.remoteSourceId}: ${this.remoteBrowsePath}`, 'info');
                        this.renderRemoteBrowser();
                    } catch (error) {
                        this.updateRemoteHint(error.message, 'danger');
                        this.renderRemoteBrowser();
                        if (!skipLoading) (this.showError || defaultShowError)(error.message);
                    } finally {
                        if (!skipLoading) this.hideLoading?.();
                    }
                },

                async browseRemoteRoot() {
                    this.resetRemoteTreeState();
                    await this.browseRemotePath('', { skipLoading: false });
                },

                async browseRemoteParent() {
                    if (!this.remoteParentPath) return;
                    await this.browseRemotePath(this.remoteParentPath);
                },

                selectCurrentRemotePath() {
                    this.remoteSelectedPath = this.remoteBrowsePath || '';
                    this.updateRemotePathDisplay();
                    this.renderRemoteBrowser();
                },

                async refreshRemoteNode() {
                    await this.browseRemotePath(this.remoteBrowsePath || '');
                },

                async testRemoteSource() {
                    if (!this.remoteSourceId) {
                        (this.showError || defaultShowError)('Please select an SSH data source first');
                        return;
                    }

                    this.showLoading?.('Testing SSH connection...');
                    try {
                        const response = await fetch('/api/remote-sources/test', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ source_id: this.remoteSourceId }),
                        });
                        const data = await response.json();
                        if (!data.success) {
                            throw new Error(data.message || 'SSH connection test failed');
                        }

                        this.updateRemoteHint(`SSH connected. Root path: ${data.test_result.root_path}`, 'success');
                        await this.browseRemoteRoot();
                    } catch (error) {
                        this.updateRemoteHint(error.message, 'danger');
                        (this.showError || defaultShowError)(error.message);
                    } finally {
                        this.hideLoading?.();
                    }
                },

                async syncRemoteAndScan() {
                    if (!this.remoteSourceId) {
                        (this.showError || defaultShowError)('Please select an SSH data source first');
                        return;
                    }

                    const remotePath = this.remoteSelectedPath || this.remoteBrowsePath;
                    if (!remotePath) {
                        (this.showError || defaultShowError)('Please select a remote directory first');
                        return;
                    }

                    this.showLoading?.('Syncing remote directory...');
                    try {
                        const response = await fetch('/api/remote-sources/sync', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                source_id: this.remoteSourceId,
                                remote_path: remotePath,
                            }),
                        });
                        const data = await response.json();
                        if (!data.success) {
                            throw new Error(data.message || 'Failed to queue remote sync');
                        }

                        this.stopSyncPolling?.();
                        this.pollSyncTaskStatus(data.task_id);
                    } catch (error) {
                        this.hideLoading?.();
                        (this.showError || defaultShowError)(error.message);
                    }
                },

                async pollSyncTaskStatus(taskId) {
                    try {
                        const response = await fetch(`/api/remote-sources/sync-task/${encodeURIComponent(taskId)}`);
                        const data = await response.json();
                        if (!data.success) {
                            throw new Error(data.message || 'Failed to read remote sync status');
                        }

                        this.updateProgress?.(data.progress, data.stage, data.detail, data.history || [], data.meta || {}, data.status);

                        if (data.status === 'completed') {
                            this.stopSyncPolling?.();
                            const localCachePath = data.result?.local_cache_path || '';
                            const basePathInput = document.getElementById('basePath');
                            if (basePathInput) basePathInput.value = localCachePath;
                            if (typeof this.setScanSummary === 'function') {
                                this.setScanSummary(`Remote directory ${data.result?.remote_path || this.remoteSelectedPath} synced to local cache. Starting scan...`, 'info');
                            }
                            await this.scanLocalFolder?.(localCachePath, 'Scanning synced directory...');
                            return;
                        }

                        if (data.status === 'failed') {
                            this.stopSyncPolling?.();
                            this.hideLoading?.();
                            (this.showError || defaultShowError)(data.error || data.detail || 'Remote sync failed');
                            return;
                        }

                        this.syncPollTimer = window.setTimeout(() => this.pollSyncTaskStatus(taskId), 1000);
                    } catch (error) {
                        this.stopSyncPolling?.();
                        this.hideLoading?.();
                        (this.showError || defaultShowError)(error.message);
                    }
                },
            });

            return target;
        },
    };

    window.AnalysisWorkspace = AnalysisWorkspace;
})();
