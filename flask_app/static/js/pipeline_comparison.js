const PipelineComparisonPage = {
    storageKey: 'pipeline_comparison_page_config_v2',
    isRunning: false,
    isScanning: false,
    isBrowsingRemote: false,
    scanData: null,
    pendingOverrides: [],
    projectContext: null,
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
    syncPollTimer: null,

    init() {
        this.bindEvents();
        this.loadConfig();

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
            remoteTreeSearch.addEventListener('input', (event) => this.handleRemoteTreeSearch(event.target.value));
        }

        this.loadRemoteSources();
        this.initializeFromProjectContext();
        this.log('Pipeline Comparison 页面已就绪。');
    },

    bindEvents() {
        document.getElementById('pcGenerateBtn')?.addEventListener('click', () => this.generate());
        document.getElementById('pcSaveConfigBtn')?.addEventListener('click', () => this.saveConfig(true));
        document.getElementById('pcClearLogBtn')?.addEventListener('click', () => this.clearLog());
        document.getElementById('pcScanBtn')?.addEventListener('click', () => this.scanRootFolder());
        document.getElementById('pcBrowseRemoteRootBtn')?.addEventListener('click', () => this.browseRemoteRoot());
        document.getElementById('pcTestRemoteBtn')?.addEventListener('click', () => this.testRemoteSource());
        document.getElementById('pcBrowseRemoteParentBtn')?.addEventListener('click', () => this.browseRemoteParent());
        document.getElementById('pcSelectRemoteCurrentBtn')?.addEventListener('click', () => this.selectCurrentRemotePath());
        document.getElementById('pcSyncRemoteBtn')?.addEventListener('click', () => this.syncRemoteAndScan());
        document.getElementById('pcRefreshRemoteNodeBtn')?.addEventListener('click', () => this.refreshRemoteNode());
        document.getElementById('pcBasePath')?.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                this.scanRootFolder();
            }
        });
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
        if (container && !container.querySelector('[data-project-context-banner]')) {
            const banner = document.createElement('div');
            banner.className = 'alert alert-primary d-flex justify-content-between align-items-center gap-3';
            banner.setAttribute('data-project-context-banner', '1');
            banner.innerHTML = `
                <div>
                    <div class="fw-semibold">项目桥接已启用</div>
                    <div class="small">当前项目：${this.escapeHtml(context.projectName || context.projectId)}。页面会复用项目目录作为默认 pipeline 根目录。</div>
                </div>
                <a class="btn btn-sm btn-outline-primary" href="/projects/${encodeURIComponent(context.projectId)}">返回项目详情</a>
            `;
            container.insertBefore(banner, container.firstChild);
        }

        const basePathInput = document.getElementById('pcBasePath');
        if (basePathInput && context.basePath) {
            basePathInput.value = context.basePath;
        }
        if (context.autoScan && context.basePath && !this._autoScanTriggered) {
            this._autoScanTriggered = true;
            this.scanRootFolder();
        }
    },

    async registerProjectResult(payload) {
        const context = this.getProjectContext();
        if (!context.projectId) return;
        try {
            await fetch(`/api/projects/${encodeURIComponent(context.projectId)}/analysis/pipeline-comparison/register-result`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (error) {
            console.warn('Failed to register pipeline comparison result for project:', error);
        }
    },

    parseCsvList(raw) {
        return String(raw || '')
            .split(',')
            .map((item) => item.trim())
            .filter(Boolean);
    },

    normalizePath(path) {
        return String(path || '').trim();
    },

    escapeHtml(text) {
        return String(text || '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    },

    showError(message) {
        alert(message);
    },

    log(message) {
        const el = document.getElementById('pcLog');
        if (!el) return;
        const now = new Date().toLocaleTimeString('zh-CN', { hour12: false });
        const prefix = `[${now}] `;
        if (!el.textContent || el.textContent === '空闲。') {
            el.textContent = `${prefix}${message}`;
        } else {
            el.textContent += `\n${prefix}${message}`;
        }
        el.scrollTop = el.scrollHeight;
    },

    clearLog() {
        const el = document.getElementById('pcLog');
        if (el) el.textContent = '空闲。';
    },

    showLoading(text = '处理中...', stage = '处理中...') {
        const overlay = document.getElementById('pcLoadingOverlay');
        if (!overlay) return;
        document.getElementById('pcLoadingStage').textContent = stage;
        document.getElementById('pcLoadingText').textContent = text;
        this.updateLoadingProgress(0, stage, text, []);
        overlay.style.display = 'flex';
    },

    hideLoading() {
        const overlay = document.getElementById('pcLoadingOverlay');
        if (overlay) overlay.style.display = 'none';
    },

    updateLoadingProgress(progress, stage, detail, history = []) {
        const progressBar = document.getElementById('pcLoadingProgressBar');
        const stageEl = document.getElementById('pcLoadingStage');
        const detailEl = document.getElementById('pcLoadingText');
        const logEl = document.getElementById('pcLoadingProgressLog');
        const value = Math.max(0, Math.min(100, Number(progress || 0)));

        if (progressBar) {
            progressBar.style.width = `${value}%`;
            progressBar.setAttribute('aria-valuenow', String(value));
            progressBar.textContent = `${Math.round(value)}%`;
        }
        if (stageEl) stageEl.textContent = stage || '处理中...';
        if (detailEl) detailEl.textContent = detail || '';
        if (logEl) {
            logEl.innerHTML = Array.isArray(history) && history.length
                ? history.slice().reverse().map((item) => `
                    <div class="mb-2">
                        <div class="fw-semibold">${this.escapeHtml(item.stage || '处理中')} <span class="text-muted">(${Math.round(item.progress || 0)}%)</span></div>
                        <div class="text-muted small">${this.escapeHtml(item.timestamp || '')}</div>
                        <div class="text-muted">${this.escapeHtml(item.detail || '')}</div>
                    </div>
                `).join('')
                : '<div class="text-muted">等待任务开始...</div>';
        }
    },

    stopSyncPolling() {
        if (this.syncPollTimer) {
            clearTimeout(this.syncPollTimer);
            this.syncPollTimer = null;
        }
    },

    setRunning(running) {
        this.isRunning = running;
        const btn = document.getElementById('pcGenerateBtn');
        if (btn) {
            btn.disabled = running;
            btn.innerHTML = running
                ? '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>运行中...'
                : '<i class="bi bi-play-fill me-1"></i>运行 Pipeline Comparison';
        }
        this.setScanRunning(this.isScanning);
    },

    setScanRunning(running) {
        this.isScanning = running;
        const scanBtn = document.getElementById('pcScanBtn');
        if (!scanBtn) return;
        scanBtn.disabled = running || this.isRunning;
        scanBtn.innerHTML = running
            ? '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>扫描中...'
            : '<i class="bi bi-search me-1"></i>扫描 Pipeline';
    },

    setScanSummary(text, isError = false) {
        const el = document.getElementById('pcScanSummary');
        if (!el) return;
        el.textContent = text || '尚未扫描。';
        el.style.borderColor = isError ? '#e4b4b4' : '#bfd7e8';
        el.style.background = isError ? '#fff7f7' : '#f8fcff';
        el.style.color = isError ? '#7a2525' : '#2b516e';
    },

    updateRemoteHint(message, variant = 'secondary') {
        const hint = document.getElementById('pcRemoteHint');
        if (!hint) return;
        hint.className = `alert alert-${variant} mb-3`;
        hint.textContent = message || '';
    },

    toggleDataSourceMode(mode = 'local') {
        this.dataSourceMode = mode;
        const localPanel = document.getElementById('localSourcePanel');
        const remotePanel = document.getElementById('remoteSourcePanel');
        if (localPanel) localPanel.classList.toggle('pc-hidden', mode !== 'local');
        if (remotePanel) remotePanel.classList.toggle('pc-hidden', mode !== 'remote');
        if (mode === 'remote' && this.remoteSourceId && !this.remoteBrowsePath) {
            this.browseRemoteRoot();
        }
        this.saveConfig(false);
    },

    getCardPipelineName(card) {
        return card?.dataset?.pipelineName || '';
    },

    getPipelineCards() {
        return Array.from(document.querySelectorAll('.pc-pipeline-item'));
    },

    getCompatiblePipelines(pipelines) {
        const source = Array.isArray(pipelines) ? pipelines : [];
        return source.filter((pipeline) => {
            const files = Array.isArray(pipeline?.pep_files) ? pipeline.pep_files : [];
            return files.length > 0;
        });
    },

    renderPipelineOrderList(availableNames) {
        const listEl = document.getElementById('pcPipelineOrderList');
        const inputEl = document.getElementById('pcPipelines');
        if (!listEl || !inputEl) return;

        const names = Array.isArray(availableNames)
            ? availableNames.map((name) => String(name || '').trim()).filter(Boolean)
            : [];
        const orderedNames = this.resolvePipelineOrder(names);

        if (orderedNames.length === 0) {
            listEl.innerHTML = '<li class="list-group-item text-muted">请先扫描并识别可配置的 pipeline。</li>';
            inputEl.value = '';
            return;
        }

        listEl.innerHTML = orderedNames.map((name, index) => `
            <li class="list-group-item pc-order-item" draggable="true" data-pipeline-name="${this.escapeHtml(name)}">
                <span class="pc-order-handle" aria-hidden="true"><i class="bi bi-grip-vertical"></i></span>
                <span class="pc-order-index">${index + 1}.</span>
                <span class="pc-order-name">${this.escapeHtml(name)}</span>
            </li>
        `).join('');

        this.bindPipelineOrderDragEvents();
        this.syncPipelineOrderFromList();
    },

    refreshPipelineOrderIndices() {
        const items = Array.from(document.querySelectorAll('#pcPipelineOrderList .pc-order-item'));
        items.forEach((item, index) => {
            const indexEl = item.querySelector('.pc-order-index');
            if (indexEl) indexEl.textContent = `${index + 1}.`;
        });
    },

    syncPipelineOrderFromList() {
        const listEl = document.getElementById('pcPipelineOrderList');
        const inputEl = document.getElementById('pcPipelines');
        if (!listEl || !inputEl) return;

        const orderedNames = Array.from(listEl.querySelectorAll('.pc-order-item'))
            .map((item) => (item.dataset.pipelineName || '').trim())
            .filter(Boolean);
        inputEl.value = orderedNames.join(',');
        this.refreshPipelineOrderIndices();
    },

    bindPipelineOrderDragEvents() {
        const listEl = document.getElementById('pcPipelineOrderList');
        if (!listEl) return;

        let draggedItem = null;
        const getItem = (eventTarget) => eventTarget?.closest?.('.pc-order-item');

        listEl.querySelectorAll('.pc-order-item').forEach((item) => {
            item.addEventListener('dragstart', (event) => {
                draggedItem = item;
                item.classList.add('dragging');
                if (event.dataTransfer) {
                    event.dataTransfer.effectAllowed = 'move';
                    try {
                        event.dataTransfer.setData('text/plain', item.dataset.pipelineName || '');
                    } catch (_) {
                        // Ignore browser-specific drag MIME restrictions.
                    }
                }
            });

            item.addEventListener('dragover', (event) => {
                const targetItem = getItem(event.target);
                if (!draggedItem || !targetItem || draggedItem === targetItem) return;
                event.preventDefault();
                targetItem.classList.add('drag-over');

                const rect = targetItem.getBoundingClientRect();
                const afterTarget = (event.clientY - rect.top) > (rect.height / 2);
                const referenceNode = afterTarget ? targetItem.nextSibling : targetItem;
                if (referenceNode !== draggedItem) {
                    listEl.insertBefore(draggedItem, referenceNode);
                }
            });

            item.addEventListener('dragleave', (event) => {
                const targetItem = getItem(event.target);
                if (targetItem) targetItem.classList.remove('drag-over');
            });

            item.addEventListener('drop', (event) => {
                event.preventDefault();
                const targetItem = getItem(event.target);
                if (targetItem) targetItem.classList.remove('drag-over');
            });

            item.addEventListener('dragend', () => {
                listEl.querySelectorAll('.pc-order-item').forEach((node) => {
                    node.classList.remove('drag-over');
                    node.classList.remove('dragging');
                });
                draggedItem = null;
                this.syncPipelineOrderFromList();
                this.saveConfig(false);
            });
        });
    },

    showSelectedPipelineCard(pipelineName) {
        const target = String(pipelineName || '').toLowerCase();
        const cards = this.getPipelineCards();
        cards.forEach((card) => {
            const name = this.getCardPipelineName(card).toLowerCase();
            card.style.display = name === target ? '' : 'none';
        });
    },

    buildPipelineCardHtml(pipeline, index) {
        const files = Array.isArray(pipeline.pep_files) ? pipeline.pep_files : [];
        const fileOptions = files.length
            ? files.map((file, fileIndex) => {
                const label = file.relative_path || file.filename || `pep_file_${fileIndex + 1}`;
                return `<option value="${fileIndex}">${this.escapeHtml(label)}</option>`;
            }).join('')
            : '<option value="">未找到兼容文件</option>';

        const defaultHint = pipeline.default_config_matched ? '已匹配默认配置。' : '请确认当前 pipeline 目录的字段定义。';

        return `
            <div class="pc-pipeline-item"
                 data-pipeline-name="${this.escapeHtml(pipeline.name)}"
                 data-pipeline-dir="${this.escapeHtml(pipeline.directory || '')}"
                 data-pipeline-index="${index}">
                <div class="pc-pipeline-head">
                    <div class="pc-pipeline-name">${this.escapeHtml(pipeline.name)}</div>
                    <span class="badge text-bg-light">${files.length} 个兼容文件</span>
                </div>
                <div class="pc-filepath mb-2">${this.escapeHtml(pipeline.directory || '')}</div>
                <div class="row g-2">
                    <div class="col-12">
                        <label class="form-label pc-label mb-1">代表性数据文件</label>
                        <select class="form-select form-select-sm pc-pep-select">${fileOptions}</select>
                    </div>
                    <div class="col-12">
                        <label class="form-label pc-label mb-1">文件命名模式</label>
                        <input type="text"
                               class="form-control form-control-sm pc-pattern-input"
                               value="${this.escapeHtml(pipeline.suggested_file_pattern || '')}"
                               placeholder="{sample}_{chain}_pep.csv">
                    </div>
                    <div class="col-md-6">
                        <label class="form-label pc-label mb-1">CDR3 列</label>
                        <select class="form-select form-select-sm pc-cdr3-select"></select>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label pc-label mb-1">Copy 列</label>
                        <select class="form-select form-select-sm pc-copy-select"></select>
                    </div>
                </div>
                <div class="pc-note mt-2 pc-filepath pc-selected-file"></div>
                <div class="pc-note mt-1">${this.escapeHtml(defaultHint)}</div>
            </div>
        `;
    },

    appendOptionIfMissing(selectEl, value) {
        if (!selectEl || !value) return;
        const exists = Array.from(selectEl.options).some((opt) => opt.value === value);
        if (!exists) {
            selectEl.innerHTML += `<option value="${this.escapeHtml(value)}">${this.escapeHtml(value)}</option>`;
        }
    },

    populateSelectOptions(selectEl, columns, preferredValue) {
        if (!selectEl) return;
        const safeColumns = Array.isArray(columns) ? columns : [];
        let options = '<option value="">请选择...</option>';
        safeColumns.forEach((columnName) => {
            options += `<option value="${this.escapeHtml(columnName)}">${this.escapeHtml(columnName)}</option>`;
        });
        selectEl.innerHTML = options;

        if (preferredValue && safeColumns.includes(preferredValue)) {
            selectEl.value = preferredValue;
            return;
        }
        if (safeColumns.length > 0) {
            selectEl.value = safeColumns[0];
        }
    },

    updateCardByFileSelection(card, pipeline) {
        if (!card || !pipeline) return;

        const pepSelect = card.querySelector('.pc-pep-select');
        const cdr3Select = card.querySelector('.pc-cdr3-select');
        const copySelect = card.querySelector('.pc-copy-select');
        const selectedFileEl = card.querySelector('.pc-selected-file');
        const files = Array.isArray(pipeline.pep_files) ? pipeline.pep_files : [];

        const selectedIndex = pepSelect?.value !== '' ? Number(pepSelect.value) : -1;
        const selectedFile = selectedIndex >= 0 && selectedIndex < files.length ? files[selectedIndex] : null;

        const columns = selectedFile?.columns || [];
        const suggestedCdr3 = selectedFile?.suggested_cdr3 || pipeline.suggested_cdr3 || '';
        const suggestedCopy = selectedFile?.suggested_copy || pipeline.suggested_copy || '';

        this.populateSelectOptions(cdr3Select, columns, suggestedCdr3);
        this.populateSelectOptions(copySelect, columns, suggestedCopy);

        if (!selectedFile) {
            this.appendOptionIfMissing(cdr3Select, pipeline.suggested_cdr3 || '');
            this.appendOptionIfMissing(copySelect, pipeline.suggested_copy || '');
            if (pipeline.suggested_cdr3) cdr3Select.value = pipeline.suggested_cdr3;
            if (pipeline.suggested_copy) copySelect.value = pipeline.suggested_copy;
        }

        if (selectedFileEl) {
            selectedFileEl.textContent = selectedFile?.filepath
                ? `已选文件: ${selectedFile.filepath}`
                : '未选择兼容文件。';
        }
    },

    renderPipelineCards(pipelines) {
        const section = document.getElementById('pcPipelineConfigSection');
        const list = document.getElementById('pcPipelineList');
        const selector = document.getElementById('pcPipelineSelector');
        const selectorHint = document.getElementById('pcPipelineSelectorHint');
        if (!section || !list || !selector || !selectorHint) return;

        const allPipelines = Array.isArray(pipelines) ? pipelines : [];
        const safePipelines = this.getCompatiblePipelines(allPipelines);
        const skippedCount = Math.max(0, allPipelines.length - safePipelines.length);
        if (safePipelines.length === 0) {
            section.classList.add('pc-hidden');
            list.innerHTML = '';
            selector.innerHTML = '';
            selectorHint.textContent = '';
            this.renderPipelineOrderList([]);
            return;
        }

        list.innerHTML = safePipelines.map((pipeline, index) => this.buildPipelineCardHtml(pipeline, index)).join('');
        section.classList.remove('pc-hidden');

        const selectedNameBefore = selector.value;
        selector.innerHTML = safePipelines
            .map((pipeline) => `<option value="${this.escapeHtml(pipeline.name)}">${this.escapeHtml(pipeline.name)}</option>`)
            .join('');
        const availableNames = safePipelines.map((pipeline) => pipeline.name);
        selector.value = availableNames.includes(selectedNameBefore) ? selectedNameBefore : availableNames[0];
        this.renderPipelineOrderList(availableNames);

        selectorHint.textContent = skippedCount > 0
            ? `共识别 ${allPipelines.length} 个目录，显示 ${safePipelines.length} 个可配置 pipeline，隐藏 ${skippedCount} 个无兼容文件目录。`
            : `共识别 ${safePipelines.length} 个可配置 pipeline。`;

        selector.onchange = () => {
            this.showSelectedPipelineCard(selector.value);
        };

        const cards = this.getPipelineCards();
        cards.forEach((card, index) => {
            const pepSelect = card.querySelector('.pc-pep-select');
            const pipeline = safePipelines[index];
            this.updateCardByFileSelection(card, pipeline);
            pepSelect?.addEventListener('change', () => this.updateCardByFileSelection(card, pipeline));
        });
        this.showSelectedPipelineCard(selector.value);
    },

    getPipelineOverridesSnapshot() {
        return this.getPipelineCards().map((card) => ({
            name: this.getCardPipelineName(card),
            directory: card.dataset.pipelineDir || '',
            selected_file_index: card.querySelector('.pc-pep-select')?.value ?? '',
            file_pattern: card.querySelector('.pc-pattern-input')?.value?.trim() || '',
            cdr3_col: card.querySelector('.pc-cdr3-select')?.value || '',
            copy_col: card.querySelector('.pc-copy-select')?.value || ''
        }));
    },

    applyPipelineOverrides() {
        if (!Array.isArray(this.pendingOverrides) || this.pendingOverrides.length === 0) return;

        const cardsByName = new Map(
            this.getPipelineCards().map((card) => [this.getCardPipelineName(card).toLowerCase(), card])
        );

        this.pendingOverrides.forEach((override) => {
            const card = cardsByName.get(String(override.name || '').toLowerCase());
            if (!card) return;

            const patternInput = card.querySelector('.pc-pattern-input');
            const pepSelect = card.querySelector('.pc-pep-select');
            const cdr3Select = card.querySelector('.pc-cdr3-select');
            const copySelect = card.querySelector('.pc-copy-select');

            if (patternInput && override.file_pattern) patternInput.value = override.file_pattern;
            if (pepSelect && override.selected_file_index !== '') {
                pepSelect.value = String(override.selected_file_index);
                pepSelect.dispatchEvent(new Event('change'));
            }
            if (cdr3Select && override.cdr3_col) {
                this.appendOptionIfMissing(cdr3Select, override.cdr3_col);
                cdr3Select.value = override.cdr3_col;
            }
            if (copySelect && override.copy_col) {
                this.appendOptionIfMissing(copySelect, override.copy_col);
                copySelect.value = override.copy_col;
            }
        });
    },

    resolvePipelineOrder(availableNames) {
        const names = Array.isArray(availableNames) ? availableNames : [];
        const requestedOrder = this.parseCsvList(document.getElementById('pcPipelines')?.value || '');
        if (requestedOrder.length === 0) return [...names];

        const byLower = new Map(names.map((name) => [name.toLowerCase(), name]));
        const ordered = [];
        requestedOrder.forEach((rawName) => {
            const matched = byLower.get(rawName.toLowerCase());
            if (matched && !ordered.includes(matched)) ordered.push(matched);
        });
        names.forEach((name) => {
            if (!ordered.includes(name)) ordered.push(name);
        });
        return ordered;
    },

    collectPipelineConfigs() {
        const cards = this.getPipelineCards();
        if (cards.length === 0) return null;

        const availableNames = cards
            .map((card) => this.getCardPipelineName(card))
            .filter(Boolean);

        const orderedPipelines = this.resolvePipelineOrder(availableNames);
        if (orderedPipelines.length < 2) {
            throw new Error('至少需要 2 个已识别的 pipeline。');
        }

        const cardByName = new Map(cards.map((card) => [this.getCardPipelineName(card), card]));
        const pipelineConfigs = {};

        orderedPipelines.forEach((pipelineName) => {
            const card = cardByName.get(pipelineName);
            if (!card) return;

            const filePattern = (card.querySelector('.pc-pattern-input')?.value || '').trim();
            const cdr3Column = (card.querySelector('.pc-cdr3-select')?.value || '').trim();
            const copyColumn = (card.querySelector('.pc-copy-select')?.value || '').trim();
            const directory = card.dataset.pipelineDir || '';

            if (!filePattern) {
                throw new Error(`Pipeline ${pipelineName} 的文件命名模式不能为空。`);
            }
            if (!cdr3Column || !copyColumn) {
                throw new Error(`Pipeline ${pipelineName} 必须设置 CDR3 / Copy 列。`);
            }

            pipelineConfigs[pipelineName] = {
                directory,
                cdr3_col: cdr3Column,
                copy_col: copyColumn,
                file_pattern: filePattern
            };
        });

        return {
            pipelines: orderedPipelines,
            pipeline_configs: pipelineConfigs
        };
    },

    collectPayload() {
        const basePath = this.normalizePath(document.getElementById('pcBasePath')?.value || '');
        if (!basePath) {
            throw new Error('请输入根目录路径。');
        }

        const pipelineConfigPayload = this.collectPipelineConfigs();
        let pipelines = [];
        let pipelineConfigs = null;

        if (pipelineConfigPayload) {
            pipelines = pipelineConfigPayload.pipelines;
            pipelineConfigs = pipelineConfigPayload.pipeline_configs;
        } else {
            pipelines = this.parseCsvList(document.getElementById('pcPipelines')?.value || '').map((item) => item.toUpperCase());
            if (pipelines.length < 2) {
                throw new Error('至少需要 2 个 pipeline。');
            }
        }

        const samples = this.parseCsvList(document.getElementById('pcSamples')?.value || '');
        const chains = this.parseCsvList(document.getElementById('pcChains')?.value || '').map((item) => item.toUpperCase());
        const outputName = (document.getElementById('pcOutputName')?.value || '').trim();

        return {
            base_path: basePath,
            pipelines,
            pipeline_configs: pipelineConfigs,
            samples: samples.length > 0 ? samples : null,
            selected_chains: chains.length > 0 ? chains : null,
            output_name: outputName || null,
            enable_heatmap: document.getElementById('pcEnableHeatmap')?.checked ?? true,
            enable_venn: document.getElementById('pcEnableVenn')?.checked ?? true,
            enable_html_report: document.getElementById('pcEnableHtmlReport')?.checked ?? true,
            include_cdr3_analysis: document.getElementById('pcIncludeCdr3')?.checked ?? false,
            embed_images: document.getElementById('pcEmbedImages')?.checked ?? false
        };
    },

    buildConfigSnapshot() {
        return {
            data_source_mode: this.dataSourceMode,
            remote_source_id: this.remoteSourceId,
            base_path: this.normalizePath(document.getElementById('pcBasePath')?.value || ''),
            pipelines_input: document.getElementById('pcPipelines')?.value || '',
            samples_input: document.getElementById('pcSamples')?.value || '',
            chains_input: document.getElementById('pcChains')?.value || '',
            output_name: (document.getElementById('pcOutputName')?.value || '').trim(),
            enable_heatmap: document.getElementById('pcEnableHeatmap')?.checked ?? true,
            enable_venn: document.getElementById('pcEnableVenn')?.checked ?? true,
            enable_html_report: document.getElementById('pcEnableHtmlReport')?.checked ?? true,
            include_cdr3_analysis: document.getElementById('pcIncludeCdr3')?.checked ?? false,
            embed_images: document.getElementById('pcEmbedImages')?.checked ?? false,
            pipeline_overrides: this.getPipelineOverridesSnapshot()
        };
    },

    saveConfig(showAlert = false) {
        localStorage.setItem(this.storageKey, JSON.stringify(this.buildConfigSnapshot()));
        this.log('参数已保存到本地存储。');
        if (showAlert) alert('参数已保存。');
    },

    loadConfig() {
        const raw = localStorage.getItem(this.storageKey);
        if (!raw) return;

        try {
            const cfg = JSON.parse(raw);
            if (cfg.base_path) document.getElementById('pcBasePath').value = cfg.base_path;
            if (cfg.pipelines_input !== undefined) document.getElementById('pcPipelines').value = cfg.pipelines_input;
            if (cfg.samples_input !== undefined) document.getElementById('pcSamples').value = cfg.samples_input;
            if (cfg.chains_input !== undefined) document.getElementById('pcChains').value = cfg.chains_input;
            if (cfg.output_name) document.getElementById('pcOutputName').value = cfg.output_name;
            if (cfg.data_source_mode) document.getElementById('dataSourceMode').value = cfg.data_source_mode;
            if (cfg.remote_source_id) this.remoteSourceId = cfg.remote_source_id;
            if (typeof cfg.enable_heatmap === 'boolean') document.getElementById('pcEnableHeatmap').checked = cfg.enable_heatmap;
            if (typeof cfg.enable_venn === 'boolean') document.getElementById('pcEnableVenn').checked = cfg.enable_venn;
            if (typeof cfg.enable_html_report === 'boolean') document.getElementById('pcEnableHtmlReport').checked = cfg.enable_html_report;
            if (typeof cfg.include_cdr3_analysis === 'boolean') document.getElementById('pcIncludeCdr3').checked = cfg.include_cdr3_analysis;
            if (typeof cfg.embed_images === 'boolean') document.getElementById('pcEmbedImages').checked = cfg.embed_images;
            if (Array.isArray(cfg.pipeline_overrides)) this.pendingOverrides = cfg.pipeline_overrides;
            this.log('已从本地存储加载参数。');
        } catch (error) {
            this.log(`加载参数失败: ${error.message}`);
        }
    },

    async scanLocalFolder(basePath, loadingText = '正在扫描 Pipeline 根目录...') {
        this.setScanRunning(true);
        this.setScanSummary(`正在扫描: ${basePath}`);
        this.log(`开始扫描 pipeline 根目录: ${basePath}`);
        this.showLoading(loadingText, '扫描目录');

        try {
            const response = await fetch('/api/auto-heatmap/scan-pipeline-root', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ base_path: basePath })
            });
            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.message || '扫描失败。');
            }

            this.scanData = data;
            const pipelines = Array.isArray(data.pipelines) ? data.pipelines : [];
            const resultCard = document.getElementById('pcResultCard');
            if (resultCard) resultCard.style.display = 'none';
            this.renderPipelineCards(pipelines);
            this.applyPipelineOverrides();

            const visiblePipelineNames = this.getPipelineCards()
                .map((card) => this.getCardPipelineName(card))
                .filter(Boolean);

            if (visiblePipelineNames.length === 0) {
                const msg = '扫描完成，但未找到包含兼容文件的 pipeline。';
                this.setScanSummary(msg, true);
                this.log(msg);
            } else {
                const hiddenCount = Math.max(0, pipelines.length - visiblePipelineNames.length);
                const msg = hiddenCount > 0
                    ? `扫描完成：共 ${pipelines.length} 个目录，显示 ${visiblePipelineNames.length} 个可配置 pipeline，隐藏 ${hiddenCount} 个无兼容文件目录。`
                    : `扫描完成：识别到 ${visiblePipelineNames.length} 个可配置 pipeline。`;
                this.setScanSummary(msg);
                this.log(msg);
            }
            this.saveConfig(false);
        } catch (error) {
            this.setScanSummary(error.message || '扫描失败。', true);
            this.log(`扫描失败: ${error.message}`);
            throw error;
        } finally {
            this.hideLoading();
            this.setScanRunning(false);
        }
    },

    async scanRootFolder() {
        if (this.isScanning || this.isRunning) return;

        if (this.dataSourceMode === 'remote') {
            await this.syncRemoteAndScan();
            return;
        }

        const basePath = this.normalizePath(document.getElementById('pcBasePath')?.value || '');
        if (!basePath) {
            this.showError('请输入根目录路径。');
            return;
        }

        try {
            await this.scanLocalFolder(basePath);
        } catch (error) {
            this.showError(error.message || '扫描失败。');
        }
    },

    renderResult(data) {
        const resultCard = document.getElementById('pcResultCard');
        document.getElementById('pcResultJobId').textContent = data.job_id || '-';
        document.getElementById('pcResultOutputBase').textContent = data.output_base || '-';
        document.getElementById('pcResultReportPath').textContent = data.report_path || '-';

        const reportBtn = document.getElementById('pcOpenReportBtn');
        if (data.report_url) {
            reportBtn.href = data.report_url;
            reportBtn.style.display = '';
        } else {
            reportBtn.removeAttribute('href');
            reportBtn.style.display = 'none';
        }

        const metadataBtn = document.getElementById('pcOpenMetadataBtn');
        if (data.metadata_url) {
            metadataBtn.href = data.metadata_url;
            metadataBtn.style.display = '';
        } else {
            metadataBtn.removeAttribute('href');
            metadataBtn.style.display = 'none';
        }

        const summary = document.getElementById('pcResultSummary');
        const meta = data.metadata || {};
        const pipelines = Array.isArray(meta.pipelines) ? meta.pipelines.join(', ') : '-';
        const samples = Array.isArray(meta.samples) ? meta.samples.join(', ') : '-';
        const chains = Array.isArray(meta.chains) ? meta.chains.join(', ') : '-';
        summary.textContent = `Pipeline: ${pipelines} | 样本: ${samples} | 链: ${chains}`;

        resultCard.style.display = '';
    },

    async generate() {
        if (this.isRunning) return;

        let payload;
        try {
            payload = this.collectPayload();
        } catch (error) {
            this.showError(error.message || '参数校验失败。');
            return;
        }

        this.setRunning(true);
        this.log(`开始运行，base_path=${payload.base_path}`);
        this.showLoading('正在生成 pipeline comparison 报告...', '执行分析');

        try {
            this.saveConfig(false);
            const response = await fetch('/api/auto-heatmap/generate-pipeline-report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.message || '生成失败。');
            }

            this.log(`运行完成。job_id=${data.job_id}`);
            if (data.report_url) this.log(`报告链接: ${data.report_url}`);

            await this.registerProjectResult({
                job_id: data.job_id,
                output_base: data.output_base,
                report_path: data.report_path,
                report_url: data.report_url,
                metadata_url: data.metadata_url,
                metadata: data.metadata
            });

            this.renderResult(data);
            if (data.report_url) window.open(data.report_url, '_blank', 'noopener');
        } catch (error) {
            this.log(`运行失败: ${error.message}`);
            this.showError(error.message || '生成失败。');
        } finally {
            this.hideLoading();
            this.setRunning(false);
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
        this.stopSyncPolling();
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
            .map((item) => String(item).toLowerCase());
        if (haystacks.some((item) => item.includes(this.remoteTreeFilter))) return true;

        return (node.childrenPaths || []).some((childPath) => this.remoteTreeNodeMatchesFilter(childPath));
    },

    getRemoteRootLabel(rootPath, source) {
        return source?.name ? `${source.name} · ${rootPath || '/'}` : (rootPath || '/');
    },

    getRemoteNodeLabel(path, fallback = '') {
        const safePath = String(path || '');
        if (!safePath) return fallback || '/';
        const parts = safePath.split('/').filter(Boolean);
        return parts.length ? parts[parts.length - 1] : (fallback || safePath || '/');
    },

    upsertRemoteTreeNode(nextNode) {
        const current = this.remoteTreeNodes[nextNode.path] || {};
        const merged = { ...current, ...nextNode };
        if (Array.isArray(nextNode.childrenPaths)) {
            merged.childrenPaths = [...nextNode.childrenPaths];
        }
        this.remoteTreeNodes[nextNode.path] = merged;
        return merged;
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
            this.remoteSources.forEach((source) => {
                const option = document.createElement('option');
                option.value = source.id;
                option.textContent = `${source.name} (${source.username}@${source.host}:${source.port})`;
                remoteSourceSelect.appendChild(option);
            });

            const preferredSource = this.remoteSources.some((source) => source.id === this.remoteSourceId)
                ? this.remoteSourceId
                : this.remoteSources[0].id;
            this.remoteSourceId = preferredSource;
            remoteSourceSelect.value = preferredSource;
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
        this.saveConfig(false);

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
        if (!node || !this.remoteTreeNodeMatchesFilter(node.path)) return null;

        const branch = document.createElement('div');
        branch.className = 'remote-tree-branch';

        const row = document.createElement('div');
        row.className = 'remote-tree-node';
        row.style.setProperty('--tree-depth', String(depth));
        if (this.remoteBrowsePath === node.path) row.classList.add('active');
        if (this.remoteSelectedPath === node.path) row.classList.add('selected');

        const toggleBtn = document.createElement('button');
        toggleBtn.type = 'button';
        toggleBtn.className = 'remote-tree-toggle';
        const hasKnownChildren = !node.childrenLoaded || (node.childrenPaths || []).length > 0;
        if (!hasKnownChildren && depth > 0) {
            toggleBtn.disabled = true;
            toggleBtn.innerHTML = '<i class="bi bi-dot"></i>';
        } else {
            toggleBtn.innerHTML = `<i class="bi ${node.expanded ? 'bi-chevron-down' : 'bi-chevron-right'}"></i>`;
            toggleBtn.addEventListener('click', async (event) => {
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
        if (node.fileCount > 0) metaParts.push(`${node.fileCount} file(s)`);
        if (this.remoteSelectedPath === node.path) metaParts.push('selected');
        else if (this.remoteBrowsePath === node.path) metaParts.push('current');
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
                node.childrenPaths.forEach((childPath) => {
                    const childElement = this.renderRemoteTreeNode(this.remoteTreeNodes[childPath], depth + 1);
                    if (childElement) children.appendChild(childElement);
                });
                if (children.childElementCount > 0) branch.appendChild(children);
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
        if (this.isBrowsingRemote) return;
        this.isBrowsingRemote = true;

        if (!skipLoading) this.showLoading('Loading remote folders...', '远程浏览');

        try {
            const response = await fetch('/api/remote-sources/browse', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_id: this.remoteSourceId, path })
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || 'Failed to load remote directory');

            const rootPath = data.root_path || data.current_path || '/';
            const currentPath = data.current_path || rootPath;
            const currentEntries = Array.isArray(data.entries) ? data.entries : [];
            const childDirs = currentEntries.filter((entry) => entry && entry.is_dir);
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
            childDirs.forEach((entry) => {
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

        this.showLoading('Testing SSH connection...', '测试连接');
        try {
            const response = await fetch('/api/remote-sources/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_id: this.remoteSourceId })
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

    async syncRemoteAndScan() {
        if (!this.remoteSourceId) {
            this.showError('Please select an SSH data source first');
            return;
        }
        if (!this.remoteSelectedPath) {
            this.showError('Please select a remote folder to sync');
            return;
        }

        this.showLoading('Syncing remote folder...', '远程同步');
        this.log(`开始同步远程目录: ${this.remoteSelectedPath}`);

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
            if (!data.success) throw new Error(data.message || 'Failed to sync remote folder');

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
            if (!data.success) throw new Error(data.message || 'Failed to read sync task status');

            this.updateLoadingProgress(data.progress, data.stage, data.detail, data.history || []);

            if (data.status === 'completed') {
                this.stopSyncPolling();
                const localCachePath = data.result?.local_cache_path || '';
                document.getElementById('pcBasePath').value = localCachePath;
                this.setScanSummary(`远程目录 ${data.result?.remote_path || this.remoteSelectedPath} 已同步，开始扫描本地缓存。`);
                this.log(`远程同步完成，本地缓存: ${localCachePath}`);
                await this.scanLocalFolder(localCachePath, '正在扫描同步后的目录...');
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
    }
};

document.addEventListener('DOMContentLoaded', () => {
    PipelineComparisonPage.init();
});
