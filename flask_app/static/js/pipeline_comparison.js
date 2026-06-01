const PipelineComparisonPage = {
    storageKey: 'pipeline_comparison_page_config_v2',
    isRunning: false,
    isScanning: false,
    scanData: null,
    pendingOverrides: [],
    projectContext: null,

    init() {
        this.bindEvents();
        this.loadConfig();
        this.initializeFromProjectContext();
        this.log('Pipeline Comparison 页面已就绪。');
    },

    onBrowserSelect(path, type) {
        document.getElementById('pcBasePath').value = path;
    },

    bindEvents() {
        document.getElementById('pcGenerateBtn')?.addEventListener('click', () => this.generate());
        document.getElementById('pcSaveConfigBtn')?.addEventListener('click', () => this.saveConfig(true));
        document.getElementById('pcClearLogBtn')?.addEventListener('click', () => this.clearLog());
        document.getElementById('pcScanBtn')?.addEventListener('click', () => this.scanRootFolder());
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
    }
};

document.addEventListener('DOMContentLoaded', () => {
    PipelineComparisonPage.init();
});
window.PipelineComparisonPage = PipelineComparisonPage;
