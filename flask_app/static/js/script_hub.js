const ScriptHubPage = {
    projectContext: null,
    inspectData: null,
    result: null,
    activeTaskId: null,
    taskPollTimer: null,
    activeModule: 'db-alignment',
    uiState: 'idle',
    touchedFields: new Set(),
    lastInspectedBasePath: '',
    isApplyingAutoValues: false,
    stageUnlocked: { project: true, data: false, module: false, config: false },
    selectedPepPaths: [],
    selectedDatapointPaths: [],
    customPepPaths: [],
    selectedDatapointPath: '',
    selectedCachedAssetId: '',
    moduleAvailability: {},
    highlightedSource: null,
    dataSelection: {
        pepPaths: [],
        profilePath: '',
        profileType: '',
        validation: null,
    },
    chartScanResult: null,
    chartSamples: [],
    chartSelectedChains: [],
    chartSelectedSampleKeys: new Set(),
    chartSelectedFilePath: '',
    chartFileColumns: [],
    chartFieldMapping: {
        cdr3_column: '',
        copy_column: '',
        v_column: '',
        j_column: '',
    },
    chartFieldHints: {
        cdr3_column: ['cdr3(pep)', 'cdr3_pep', 'cdr3aa', 'cdr3_aa', 'cdr3'],
        copy_column: ['copy', 'copies', 'count', 'reads', 'umis', 'umi'],
        v_column: ['v', 'v_gene', 'vgene', 'bestvgene', 'v_call'],
        j_column: ['j', 'j_gene', 'jgene', 'bestjgene', 'j_call'],
    },

    CONFIG_FIELD_IDS: [
        'scriptHubOutputName',
        'scriptHubCdr3Column',
        'scriptHubCopyColumn',
        'scriptHubProfilePath',
        'scriptHubCategories',
        'scriptHubPathologyFilter',
        'scriptHubPathologyValues',
        'scriptHubBoxplotGroupToggle',
        'scriptHubBoxplotGroupChips',
        'scriptHubTcSameDirToggle',
        'scriptHubPepProfilePath',
        'scriptHubPepGroupFields',
        'scriptHubPepPvalueThreshold',
        'scriptHubPepMinSample',
    ],

    init() {
        this.bindEvents();
        this.projectContext = this.getProjectContext();
        this.loadProjects();
        this.initializeProjectContext();
        this.syncStageUI();
    },

    bindEvents() {
        document.getElementById('scriptHubProjectSelect')?.addEventListener('change', (event) => {
            this.onProjectChange(event.target.value || '');
        });
        document.getElementById('scriptHubDataConfirmBtn')?.addEventListener('click', () => this.confirmDataSelection());
        document.getElementById('scriptHubAddPepBtn')?.addEventListener('click', () => this.addHighlightedPep());
        document.getElementById('scriptHubSetProfileBtn')?.addEventListener('click', () => this.setHighlightedProfile());
        document.getElementById('scriptHubPepConfirmBtn')?.addEventListener('click', () => this.confirmPep());
        document.getElementById('scriptHubProfileConfirmBtn')?.addEventListener('click', () => this.confirmProfile());
        document.getElementById('scriptHubRunBtn')?.addEventListener('click', () => this.runDbAlignment());
        document.getElementById('scriptHubOpenViewerBtn')?.addEventListener('click', () => this.openResultUrl('viewer_url'));
        document.getElementById('scriptHubOpenZipBtn')?.addEventListener('click', () => this.openResultUrl('zip_url'));
        document.getElementById('scriptHubOpenMetadataBtn')?.addEventListener('click', () => this.openResultUrl('metadata_url'));
        document.getElementById('scriptHubOpenChartViewerBtn')?.addEventListener('click', () => this.openResultUrl('viewer_url'));
        document.getElementById('scriptHubOpenChartMetadataBtn')?.addEventListener('click', () => this.openResultUrl('metadata_url'));
        document.getElementById('scriptHubOpenBpMetadataBtn')?.addEventListener('click', () => this.openResultUrl('metadata_url'));
        document.getElementById('scriptHubDatapointPath')?.addEventListener('change', () => {
            if (this.activeModule === 'boxplot') this.onDatapointFileChange();
        });
        document.getElementById('scriptHubBoxplotGroupToggle')?.addEventListener('change', (event) => {
            const container = document.getElementById('scriptHubBoxplotGroupContainer');
            if (container) container.style.display = event.target.checked ? '' : 'none';
        });
        document.getElementById('scriptHubBoxplotGroupChips')?.addEventListener('click', (event) => {
            const chip = event.target.closest('.sh-chip-selectable');
            if (!chip) return;
            chip.classList.toggle('sh-chip-selected');
            this._selectedGroupFields = this._getSelectedGroupFields();
            this.detectGroupValuesForAll();
        });
        document.getElementById('scriptHubBoxPlotGroupSelect')?.addEventListener('change', (event) => {
            this.onGroupTypeChange(event.target.value);
        });
        document.getElementById('scriptHubBoxPlotParamSelect')?.addEventListener('change', (event) => {
            this.showBoxPlotImage(event.target.value);
        });
        document.getElementById('scriptHubPepProfilePath')?.addEventListener('change', () => {
            this.onPepProfileChange();
        });
        document.getElementById('scriptHubPepGroupSelect')?.addEventListener('change', (event) => {
            this.onPepGroupSelectChange(event.target.value);
        });
        document.getElementById('scriptHubPepChainSelect')?.addEventListener('change', (event) => {
            this.onPepChainSelectChange(event.target.value);
        });
        document.getElementById('scriptHubPepResultType')?.addEventListener('change', (event) => {
            this.onPepResultTypeChange(event.target.value);
        });
        document.getElementById('scriptHubOpenPepZipBtn')?.addEventListener('click', () => this.openResultUrl('zip_url'));
        document.getElementById('scriptHubTcSameDirToggle')?.addEventListener('change', (event) => {
            const container = document.getElementById('scriptHubTcDatapointContainer');
            if (container) container.style.display = event.target.checked ? 'none' : '';
        });
        document.getElementById('scriptHubOpenPepMetadataBtn')?.addEventListener('click', () => this.openResultUrl('metadata_url'));
        this.bindChartEvents();

        this.CONFIG_FIELD_IDS.forEach((fieldId) => {
            const element = document.getElementById(fieldId);
            if (!element) return;
            const eventName = element.tagName === 'SELECT' || element.type === 'checkbox' ? 'change' : 'input';
            element.addEventListener(eventName, () => this.markFieldTouched(fieldId));
        });
    },

    bindChartEvents() {
        document.getElementById('scriptHubChartChainList')?.addEventListener('click', (event) => {
            const item = event.target.closest('[data-chart-chain]');
            if (item) this.toggleChartChain(item.dataset.chartChain || '');
        });
        document.getElementById('scriptHubChartSampleList')?.addEventListener('click', (event) => {
            const item = event.target.closest('[data-chart-sample-key]');
            if (item) this.toggleChartSample(item.dataset.chartSampleKey || '');
        });
        document.getElementById('scriptHubChartSelectAllChains')?.addEventListener('click', () => this.selectAllChartChains());
        document.getElementById('scriptHubChartInvertChains')?.addEventListener('click', () => this.invertChartChains());
        document.getElementById('scriptHubChartClearChains')?.addEventListener('click', () => this.clearChartChains());
        document.getElementById('scriptHubChartSelectAllSamples')?.addEventListener('click', () => this.selectAllChartSamples());
        document.getElementById('scriptHubChartInvertSamples')?.addEventListener('click', () => this.invertChartSamples());
        document.getElementById('scriptHubChartClearSamples')?.addEventListener('click', () => this.clearChartSamples());
        document.getElementById('scriptHubChartConfirmSamples')?.addEventListener('click', () => this.confirmChartSamples());
        document.getElementById('scriptHubChartEditSamples')?.addEventListener('click', () => this.reopenChartSampleSelection());
        document.getElementById('scriptHubChartConfirmFields')?.addEventListener('click', () => this.confirmChartFields());
        document.getElementById('scriptHubChartSelectAllModules')?.addEventListener('click', () => this.setChartModuleSelection(['heatmap', 'treemap', 'chord']));
        document.getElementById('scriptHubChartClearModules')?.addEventListener('click', () => this.setChartModuleSelection([]));
        ['scriptHubChartHeatmap', 'scriptHubChartTreemap', 'scriptHubChartChord'].forEach((id) => {
            document.getElementById(id)?.addEventListener('change', () => this.updateChartModuleCards());
        });
        this.updateChartModuleCards();
    },

    getProjectContext() {
        const params = new URLSearchParams(window.location.search);
        const parseJsonList = (name) => {
            const raw = params.get(name) || '';
            if (!raw) return [];
            try {
                const parsed = JSON.parse(raw);
                return Array.isArray(parsed) ? parsed.map(item => String(item || '')).filter(Boolean) : [];
            } catch (error) {
                return raw.split(',').map(item => item.trim()).filter(Boolean);
            }
        };
        return {
            projectId: params.get('project_id') || '',
            projectName: params.get('project_name') || '',
            basePath: params.get('base_path') || '',
            autoScan: params.get('auto_scan') === '1',
            analysisType: params.get('analysis_type') || 'script-hub',
            activeModule: params.get('active_module') || '',
            chartModule: params.get('chart_module') || '',
        };
    },

    initializeProjectContext() {
        const context = this.projectContext || this.getProjectContext();
        if (context.activeModule) {
            this.activeModule = context.activeModule;
        }
        this._pendingActiveModule = context.activeModule || '';
        this._pendingChartModule = context.chartModule || '';
        const effectiveLocalPath = context.basePath;

        if (effectiveLocalPath) {
            const basePathInput = document.getElementById('scriptHubBasePath');
            if (basePathInput && !basePathInput.value) {
                basePathInput.value = effectiveLocalPath;
            }
        }

        // Auto-select module based on analysis_type param (deferred until data confirmed)
        this._pendingAnalysisType = (context.analysisType && context.analysisType !== 'script-hub') ? context.analysisType : null;

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

        if (context.autoScan && effectiveLocalPath && !this._autoInspectTriggered) {
            this._autoInspectTriggered = true;
            const sourceBrowser = window._sourceBrowser || window._pepBrowser;
            if (sourceBrowser) sourceBrowser.goTo(effectiveLocalPath);
        }
    },

    async loadProjects() {
        const select = document.getElementById('scriptHubProjectSelect');
        if (!select) return;

        try {
            const response = await fetch('/api/projects');
            const data = await response.json();
            const projects = Array.isArray(data.projects) ? data.projects : [];

            select.innerHTML = '<option value="">-- Select a project (optional) --</option>';
            projects.forEach((p) => {
                const option = document.createElement('option');
                option.value = p.id;
                option.textContent = p.name || p.id;
                select.appendChild(option);
            });

            const context = this.projectContext || this.getProjectContext();
            if (context.projectId) {
                select.value = context.projectId;
                await this.onProjectChange(context.projectId);
            }
        } catch (error) {
            console.warn('Failed to load projects:', error);
        }
    },

    async onProjectChange(projectId) {
        const assetsDiv = document.getElementById('scriptHubProjectAssets');
        if (!projectId) {
            if (assetsDiv) assetsDiv.innerHTML = '<span class="text-muted small">请选择项目以查看可用资产和数据。</span>';
            this.activeProject = null;
            this.projectAssets = null;
            this.stageUnlocked.data = false;
            this.stageUnlocked.module = false;
            this.stageUnlocked.config = false;
            this.syncStageUI();
            return;
        }

        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}`);
            const project = await response.json();
            this.activeProject = project;
            this.projectAssets = project.assets || [];
            this.renderProjectAssetSummary(project);

            const cachedResponse = await fetch(`/api/projects/${encodeURIComponent(projectId)}/cached-assets?asset_type=cached_usage`);
            const cachedData = await cachedResponse.json();
            const cachedAssets = cachedData.success ? (cachedData.assets || []) : [];
            this.renderCachedUsageInStage02(cachedAssets);
            this._cachedUsageAssets = cachedAssets;

            // Auto-fill base path from first local PEP asset
            const pepAssets = this.projectAssets.filter(a => a.asset_type === 'pep');
            const dpAssets = this.projectAssets.filter(a => a.asset_type === 'datapoint');
            const basePathInput = document.getElementById('scriptHubBasePath');
            const localPepAssets = pepAssets.filter(a => !(a.metadata || {}).remote_source_id);

            if (localPepAssets.length > 0) {
                const pepDir = localPepAssets[0].storage_path;
                if (basePathInput) basePathInput.value = pepDir;
            } else if (basePathInput) {
                basePathInput.value = '';
            }

            // Auto-fill profile from registered datapoint
            if (dpAssets.length > 0) {
                const dpPath = dpAssets[0].storage_path;
                const dpInput = document.getElementById('scriptHubDatapointPath');
                if (dpInput) dpInput.value = dpPath;
            }

            this.selectedPepPaths = [...new Set([
                ...this.selectedPepPaths,
                ...pepAssets.map(a => a.storage_path).filter(Boolean)
            ])];
            this.dataSelection.pepPaths = this.selectedPepPaths.map((path) => ({
                path,
                type: 'directory',
                source: 'project',
            }));

            // Navigate browsers to project paths
            if (localPepAssets.length > 0) {
                const pepDir = localPepAssets[0].storage_path;
                const sourceBrowser = window._sourceBrowser || window._pepBrowser;
                if (sourceBrowser && pepDir) sourceBrowser.goTo(pepDir);
            }
            if (dpAssets.length > 0) {
                const dpPath = dpAssets[0].storage_path;
                this.dataSelection.profilePath = dpPath;
                this.dataSelection.profileType = 'file';
                this.selectedDatapointPaths = [dpPath];
                this.selectedDatapointPath = dpPath;
            }
            this.syncDataSelectionState();

            this.stageUnlocked.data = true;
            this.syncStageUI();
        } catch (error) {
            console.warn('Failed to load project details:', error);
            if (assetsDiv) assetsDiv.innerHTML = '<span class="text-danger small">加载项目资产失败。</span>';
        }
    },

    renderProjectAssetSummary(project) {
        const assetsDiv = document.getElementById('scriptHubProjectAssets');
        if (!assetsDiv) return;

        const assets = project.assets || [];
        const pepCount = assets.filter(a => a.asset_type === 'pep').length;
        const dpCount = assets.filter(a => a.asset_type === 'datapoint').length;
        const cachedCount = assets.filter(a => a.asset_type === 'cached_usage').length;
        const resultCount = assets.filter(a => a.asset_type === 'processed_result').length;

        assetsDiv.innerHTML = `
            <span class="sh-project-asset-pill">Pep Files <span class="sh-asset-count ms-1">${pepCount}</span></span>
            <span class="sh-project-asset-pill">Profile <span class="sh-asset-count ms-1">${dpCount}</span></span>
            <span class="sh-project-asset-pill">Cached Data <span class="sh-asset-count ms-1">${cachedCount}</span></span>
            <span class="sh-project-asset-pill">Results <span class="sh-asset-count ms-1">${resultCount}</span></span>
        `;
    },

    async deleteProjectAsset(assetId) {
        const projectId = document.getElementById('scriptHubProjectSelect')?.value || '';
        if (!projectId || !assetId) return;
        try {
            await fetch(`/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}`, {
                method: 'DELETE',
            });
            await this.onProjectChange(projectId);
        } catch (e) {
            console.warn('Failed to delete asset:', e);
        }
    },

    renderCachedUsageInStage02(cachedAssets) {
        const panel = document.getElementById('scriptHubCachedUsagePanel');
        const cardsDiv = document.getElementById('scriptHubCachedSourceCards');
        if (!panel || !cardsDiv) return;
        if (!cachedAssets || !cachedAssets.length) {
            panel.style.display = 'none';
            return;
        }
        panel.style.display = '';
        cardsDiv.innerHTML = cachedAssets.map((asset, idx) => {
            const meta = asset.metadata_json || {};
            const chains = (meta.chains || []).join(', ');
            const groups = (meta.group_fields || []).join(', ');
            return `<div class="sh-cached-source-card" data-cached-id="${this.escapeHtml(asset.id)}" data-index="${idx}">
                <div class="fw-semibold">${this.escapeHtml(asset.original_name || asset.id)}</div>
                <div class="small text-muted">Chains: ${this.escapeHtml(chains || '-')} | Groups: ${this.escapeHtml(groups || '-')}</div>
            </div>`;
        }).join('');
        cardsDiv.querySelectorAll('.sh-cached-source-card').forEach((card) => {
            card.addEventListener('click', () => {
                cardsDiv.querySelectorAll('.sh-cached-source-card').forEach(c => c.classList.remove('is-selected'));
                card.classList.add('is-selected');
                this.selectedCachedAssetId = card.dataset.cachedId;
            });
        });
    },

    async confirmDataSelection() {
        this.syncDataSelectionState();

        if (this.selectedPepPaths.length === 0 && this.selectedDatapointPaths.length === 0 && !this.selectedCachedAssetId) {
            alert('请先在目录树中加入 PEP 路径或设置 Profile 文件。');
            return;
        }

        const allPepPaths = this.selectedPepPaths;
        const allDpPaths = this.selectedDatapointPaths;

        try {
            await this.inspectDataSelection();
            await this.saveDataSelectionToProject();
        } catch (error) {
            this.showSourceFeedback(error.message || '数据选择检测失败。', 'danger');
            this.showError(error.message || '数据选择检测失败');
            return;
        }

        this.evaluateAvailableModules(allPepPaths, allDpPaths);
        this.stageUnlocked.module = true;
        this.syncStageUI();
        this.renderModuleChips();
        this.renderDataSummary(allPepPaths, allDpPaths);
        this.showSourceFeedback('数据已确认。请从下方选择一个分析模块。', 'success');
        window.setTimeout(() => { document.getElementById('scriptHubModuleStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 80);
    },

    evaluateAvailableModules(pepPaths, dpPaths) {
        const hasPep = pepPaths.length > 0 || !!this.selectedCachedAssetId;
        const hasDatapoint = dpPaths.length > 0;
        this.moduleAvailability = {
            'charts': hasPep,
            'db-alignment': hasPep,
            'boxplot': hasDatapoint,
            'pep-analysis': hasPep || !!this.selectedCachedAssetId,
            'topclone': hasPep,
            'umap': hasDatapoint,
            'volcano': hasDatapoint,
            'umapin': hasDatapoint,
        };
    },

    async renderModuleChips() {
        const container = document.getElementById('scriptHubModuleChips');
        if (!container) return;
        try {
            const response = await fetch('/api/script-hub/modules');
            const data = await response.json();
            const modules = Array.isArray(data.modules) ? data.modules : [];

            container.innerHTML = modules.map(m => {
                const available = this.moduleAvailability[m.key] !== false;
                return `<span class="sh-chip sh-chip-selectable${available ? '' : ''}"
                    data-module-key="${this.escapeHtml(m.key)}"
                    style="${available ? '' : 'opacity:0.4;cursor:not-allowed;'}"
                    title="${available ? this.escapeHtml(m.description || m.label) : '当前数据不支持此模块'}">
                    ${this.escapeHtml(m.label)}</span>`;
            }).join('');
            container.querySelectorAll('.sh-chip-selectable').forEach(chip => {
                chip.addEventListener('click', () => {
                    const moduleKey = chip.dataset.moduleKey;
                    if (!this.moduleAvailability[moduleKey]) return;
                    this.selectModule(moduleKey, chip);
                });
            });
            const available = container.querySelectorAll('.sh-chip-selectable:not([style*="opacity:0.4"])');
            const pendingModule = this._pendingActiveModule || this._pendingAnalysisType || '';
            const pendingChip = pendingModule
                ? container.querySelector(`.sh-chip-selectable[data-module-key="${pendingModule}"]`)
                : null;
            if (pendingChip && this.moduleAvailability[pendingModule] !== false) {
                this.selectModule(pendingModule, pendingChip);
            } else if (available.length === 1) {
                const autoKey = available[0].dataset.moduleKey;
                this.selectModule(autoKey, available[0]);
            }
        } catch (error) {
            container.innerHTML = '<span class="text-danger small">加载模块列表失败。</span>';
        }
    },

    selectModule(moduleKey, chipEl) {
        this.activeModule = moduleKey;
        document.querySelectorAll('#scriptHubModuleChips .sh-chip-selectable').forEach(c => c.classList.remove('sh-chip-selected'));
        if (chipEl) chipEl.classList.add('sh-chip-selected');
        this.resetDownstreamState();
        this.syncModuleUI();
        this.stageUnlocked.config = true;
        this.syncStageUI();
        if (moduleKey === 'charts') {
            this.showSourceFeedback('已选择综合图表报告。将在 Script Hub 内完成链、样本、字段映射和图表生成。', 'info');
            this.prepareChartWorkflow();
        } else {
            this.inspectBasePath();
        }
        window.setTimeout(() => { document.getElementById('scriptHubConfigStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 80);
    },

    renderDataSummary(pepPaths, dpPaths) {
        const panel = document.getElementById('scriptHubDataSummaryPanel');
        const summary = document.getElementById('scriptHubDataSummary');
        if (!panel || !summary) return;
        panel.style.display = '';
        const parts = [];
        if (pepPaths.length > 0) parts.push(`<div class="sh-data-summary-item"><strong>PEP 路径 (${pepPaths.length})：</strong> ${pepPaths.map(p => this.escapeHtml(p)).join('；')}</div>`);
        if (dpPaths && dpPaths.length > 0) parts.push(`<div class="sh-data-summary-item"><strong>Profile：</strong> ${dpPaths.map(p => this.escapeHtml(p)).join('；')}</div>`);
        else if (this.selectedDatapointPath) parts.push(`<div class="sh-data-summary-item"><strong>Profile：</strong> ${this.escapeHtml(this.selectedDatapointPath)}</div>`);
        if (this.dataSelection.validation) {
            const validation = this.dataSelection.validation;
            parts.push(`<div class="sh-data-summary-item"><strong>检测：</strong> ${this.escapeHtml(String(validation.sample_count || 0))} 样本，${this.escapeHtml(String(validation.pep_file_count || 0))} 个 PEP 文件，链：${this.escapeHtml((validation.chains || []).join(', ') || '-')}</div>`);
        }
        if (this.selectedCachedAssetId) parts.push(`<div class="sh-data-summary-item"><strong>缓存数据源：</strong> ${this.escapeHtml(this.selectedCachedAssetId)}</div>`);
        summary.innerHTML = parts.length ? parts.join('') : '<span class="text-muted">未选择数据。</span>';
    },

    renderCachedDataSources(cachedAssets) {
        const configStage = document.getElementById('scriptHubConfigStage');
        if (!configStage) return;

        let container = document.getElementById('scriptHubCachedSourcesList');
        if (!container) {
            const body = configStage.querySelector('.sh-stage-body');
            if (!body) return;
            container = document.createElement('div');
            container.id = 'scriptHubCachedSourcesList';
            container.className = 'sh-data-source-section sh-hidden';
            container.setAttribute('data-module', 'pep-analysis umap topclone');
            container.innerHTML = `
                <div class="fw-semibold mb-2">Cached Pep Data Sources</div>
                <p class="text-muted small mb-2">Select a cached Pep analysis result as data source for this module.</p>
                <div id="scriptHubCachedSourceCards" class="d-flex flex-wrap gap-2"></div>
            `;
            const runBtn = body.querySelector('.d-grid');
            if (runBtn) {
                body.insertBefore(container, runBtn);
            } else {
                body.appendChild(container);
            }
        }

        if (!cachedAssets.length) {
            container.classList.add('sh-hidden');
            return;
        }
        container.classList.remove('sh-hidden');

        const cardsDiv = container.querySelector('#scriptHubCachedSourceCards');
        if (!cardsDiv) return;

        cardsDiv.innerHTML = cachedAssets.map((asset, idx) => {
            const meta = asset.metadata_json || {};
            const chains = (meta.chains || []).join(', ');
            const groups = (meta.group_fields || []).join(', ');
            const jobId = meta.source_job_id || asset.original_name || '';
            return `
                <div class="sh-cached-source-card" data-cached-id="${this.escapeHtml(asset.id)}" data-index="${idx}">
                    <div class="fw-semibold">Pep Analysis ${this.escapeHtml(jobId.slice(-12))}</div>
                    <div class="small text-muted">Chains: ${this.escapeHtml(chains || '-')} | Groups: ${this.escapeHtml(groups || '-')}</div>
                </div>
            `;
        }).join('');

        cardsDiv.querySelectorAll('.sh-cached-source-card').forEach((card) => {
            card.addEventListener('click', () => {
                cardsDiv.querySelectorAll('.sh-cached-source-card').forEach(c => c.classList.remove('is-selected'));
                card.classList.add('is-selected');
                this._selectedCachedAssetId = card.dataset.cachedId;
                const asset = cachedAssets[parseInt(card.dataset.index)];
                if (asset) this._applyCachedSourceToModule(asset);
            });
        });
    },

    _applyCachedSourceToModule(asset) {
        const meta = asset.metadata_json || {};
        const usageTypes = meta.usage_types || {};

        if (meta.pep_data_dir) {
            const pepDirInput = document.getElementById('scriptHubPepDataDir');
            if (pepDirInput) pepDirInput.value = meta.pep_data_dir;
        }
        if (meta.profile_path) {
            const profileSelect = document.getElementById('scriptHubPepProfilePath');
            if (profileSelect) {
                const option = Array.from(profileSelect.options).find(o => o.value === meta.profile_path);
                if (!option) {
                    const newOpt = document.createElement('option');
                    newOpt.value = meta.profile_path;
                    newOpt.textContent = meta.profile_path.split('/').pop() || meta.profile_path;
                    profileSelect.appendChild(newOpt);
                }
                profileSelect.value = meta.profile_path;
            }
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
        const isTopClone = module === 'topclone';
        const isUmap = module === 'umap';

        document.querySelectorAll('[data-module]').forEach((el) => {
            const allowed = (el.getAttribute('data-module') || '').split(/\s+/);
            if (allowed.includes(module)) {
                el.style.display = '';
            } else {
                el.style.display = 'none';
            }
        });

        if (module === 'charts') {
            document.getElementById('scriptHubRunBtnLabel').textContent = '运行综合图表';
            document.getElementById('scriptHubConfigHint').textContent = '使用上游已确认的 PEP 数据，在 Script Hub 内完成 Heatmap / Treemap / Chord 图表报告。';
            document.getElementById('scriptHubResultSummary').textContent = '综合图表生成完成。';
            document.getElementById('scriptHubResultMeta').textContent = '任务完成后可打开总览页、单模块 viewer 或下载 ZIP。';
        } else if (isBoxPlot) {
            document.getElementById('scriptHubRunBtnLabel').textContent = '运行箱线图分析';
            document.getElementById('scriptHubConfigHint').textContent = '启用分组可按组绘制箱线图并做 Mann-Whitney U 检验，取消则所有样本作为未分组箱体。';
            document.getElementById('scriptHubResultSummary').textContent = '箱线图分析完成。';
            document.getElementById('scriptHubResultMeta').textContent = '任务完成后查看箱线图 PNG 和 p-value CSV。';
        } else if (module === 'pep-analysis') {
            document.getElementById('scriptHubRunBtnLabel').textContent = '运行 CDR3 共享分析';
            document.getElementById('scriptHubConfigHint').textContent = '选择 pep 数据目录、链类型、Profile 文件和分组字段，运行完整的 CDR3 共享分析。';
            document.getElementById('scriptHubResultSummary').textContent = 'CDR3 共享分析完成。';
            document.getElementById('scriptHubResultMeta').textContent = '查看共享矩阵、usage 表、热图和分类结果。';
        } else if (isTopClone) {
            document.getElementById('scriptHubRunBtnLabel').textContent = '运行 TopClone 分析';
            document.getElementById('scriptHubConfigHint').textContent = 'Trace 模式：从 pep_data + Profile_All.csv 生成 topclone.csv 再做 BoxPlot。Per-sample 模式：每个样本单独提取 top clone。';
            document.getElementById('scriptHubResultSummary').textContent = 'TopClone 分析完成。';
            document.getElementById('scriptHubResultMeta').textContent = '任务完成后查看 topclone.csv 和箱线图。';
            const tcDatapointContainer = document.getElementById('scriptHubTcDatapointContainer');
            const tcSameDirToggle = document.getElementById('scriptHubTcSameDirToggle');
            if (tcDatapointContainer && tcSameDirToggle) {
                tcDatapointContainer.style.display = tcSameDirToggle.checked ? 'none' : '';
            }
        } else if (isUmap) {
            document.getElementById('scriptHubRunBtnLabel').textContent = '运行 UMAP 分析';
            document.getElementById('scriptHubConfigHint').textContent = '基于 Mann-Whitney U 显著性过滤后做 UMAP 降维投影。';
            document.getElementById('scriptHubResultSummary').textContent = 'UMAP 分析完成。';
            document.getElementById('scriptHubResultMeta').textContent = '下载 ZIP 压缩包查看所有 UMAP 图和坐标数据。';
        } else if (module === 'volcano') {
            document.getElementById('scriptHubRunBtnLabel').textContent = '运行火山图分析';
            document.getElementById('scriptHubConfigHint').textContent = '对 VJ usage 数据做两组间差异比较，生成火山图。';
            document.getElementById('scriptHubResultSummary').textContent = '火山图分析完成。';
            document.getElementById('scriptHubResultMeta').textContent = '查看火山图 PNG 和差异结果 CSV。';
        } else if (module === 'umapin') {
            document.getElementById('scriptHubRunBtnLabel').textContent = '运行 UMAPin 降维';
            document.getElementById('scriptHubConfigHint').textContent = '基于 VJ usage 拼接数据做 UMAP 降维，可选 FDR 校正。';
            document.getElementById('scriptHubResultSummary').textContent = 'UMAPin 降维完成。';
            document.getElementById('scriptHubResultMeta').textContent = '查看 UMAP 散点图和坐标 CSV。';
        } else {
            document.getElementById('scriptHubRunBtnLabel').textContent = '运行数据库比对';
            document.getElementById('scriptHubConfigHint').textContent = '字段与 Profile 设置基于检测结果自动填充，之后可手动调整。';
        }

        const inspectBtn = document.getElementById('scriptHubInspectBtn');
        if (inspectBtn) {
            inspectBtn.querySelector('i').className = (isBoxPlot || isTopClone || isUmap || module === 'pep-analysis') ? 'bi bi-table me-1' : 'bi bi-search me-1';
            const btnLabel = document.getElementById('scriptHubInspectBtnLabel');
            if (btnLabel) btnLabel.textContent = (isBoxPlot || isTopClone || isUmap || module === 'pep-analysis' || module === 'volcano') ? '检测数据文件' : '检测数据';
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
        const unlocked = this.stageUnlocked;

        this.toggleStage('scriptHubProjectStage', true);
        this.toggleStage('scriptHubDataStage', unlocked.data);
        this.toggleStage('scriptHubModuleStage', unlocked.module);
        this.toggleStage('scriptHubAssetsStage', unlocked.config && this.activeModule !== 'charts');
        this.toggleStage('scriptHubConfigStage', unlocked.config);
        this.toggleStage('scriptHubResultStage', this.uiState === 'completed');

        this.setStageStatus('scriptHubProjectState',
            unlocked.data ? { text: '已选择', tone: 'success' } : { text: '选择项目', tone: 'active' });

        this.setStageStatus('scriptHubDataState',
            unlocked.module ? { text: '已确认', tone: 'success' }
            : unlocked.data ? { text: '选择中', tone: 'active' } : { text: '未激活', tone: 'default' });

        this.setStageStatus('scriptHubModuleState',
            unlocked.config ? { text: '已选择', tone: 'success' }
            : unlocked.module ? { text: '选择中', tone: 'active' } : { text: '等待数据', tone: 'default' });

        this.setStageStatus('scriptHubAssetsState',
            unlocked.config ? { text: '已检测', tone: 'success' } : { text: '未激活', tone: 'default' });

        this.setStageStatus('scriptHubConfigState',
            this.uiState === 'running' ? { text: '运行中', tone: 'warning' }
            : this.uiState === 'completed' ? { text: '已完成', tone: 'success' }
            : unlocked.config ? { text: '可编辑', tone: 'active' } : { text: '已锁定', tone: 'default' });

        this.setStageStatus('scriptHubResultState',
            this.uiState === 'completed' ? { text: '就绪', tone: 'success' }
            : this.uiState === 'running' ? { text: '等待中', tone: 'warning' } : { text: '等待中', tone: 'default' });
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
        }
        document.getElementById('scriptHubLoadingStage').textContent = stage || '处理中...';
        document.getElementById('scriptHubLoadingText').textContent = detail || '';

        const logEl = document.getElementById('scriptHubLoadingLog');
        if (!logEl) return;
        logEl.innerHTML = Array.isArray(history) && history.length
            ? history.slice().reverse().map((item) => {
                const pct = Math.round(item.progress || 0);
                return `<div style="padding:.25rem 0;border-bottom:1px solid #eef2f5;font-size:.82rem;">
                    <span style="color:var(--sh-accent);font-weight:600;">${pct}%</span>
                    <span style="margin-left:.5rem;">${this.escapeHtml(item.stage || '处理中')}</span>
                    ${item.detail ? `<span style="margin-left:.35rem;color:var(--sh-muted);">— ${this.escapeHtml(item.detail)}</span>` : ''}
                </div>`;
            }).join('')
            : '<span style="color:var(--sh-muted);">等待任务开始。</span>';
    },

    setInspectSummary(message, tone = 'info') {
        const summary = document.getElementById('scriptHubInspectSummary');
        if (!summary) return;
        summary.className = `alert alert-${tone} mb-3`;
        summary.textContent = message || '';
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
        const isBp = this.activeModule === 'boxplot';
        document.getElementById('scriptHubResultSummary').textContent = isBp ? '箱线图分析完成。' : '数据库比对完成。';
        document.getElementById('scriptHubResultMeta').textContent = isBp
            ? '任务完成后在这里查看箱线图结果。'
            : '任务完成后在这里查看输出、下载结果。';
        document.getElementById('scriptHubPreviewFileMeta').textContent = '等待检测文件。';
        this.renderPreviewTable([], []);
        const dpSelect = document.getElementById('scriptHubDatapointPath');
        if (dpSelect) {
            const savedDpValue = dpSelect.value;
            dpSelect.innerHTML = '<option value="">-- Select a datapoint file --</option>';
            if (savedDpValue) {
                const opt = document.createElement('option');
                opt.value = savedDpValue;
                opt.textContent = (savedDpValue.replace(/\\/g, '/').split('/').pop()) || savedDpValue;
                opt.selected = true;
                dpSelect.appendChild(opt);
            }
        }
        document.getElementById('scriptHubParamBegin').innerHTML = '<option value="">Select column</option>';
        document.getElementById('scriptHubParamOver').innerHTML = '<option value="">Select column</option>';

        document.getElementById('scriptHubColumnChips').innerHTML = '<span class="sh-chip">No columns detected</span>';
        document.getElementById('scriptHubBpParamSuggestion').textContent = '-';
        document.getElementById('scriptHubBpSuggestions')?.classList.add('sh-hidden');

        const paramSelect = document.getElementById('scriptHubBoxPlotParamSelect');
        if (paramSelect) paramSelect.innerHTML = '<option value="">-- Select a parameter --</option>';
        document.getElementById('scriptHubBoxPlotSingleImage').innerHTML = '<p class="text-muted small">Select a parameter above to view its boxplot.</p>';
        const groupSelect = document.getElementById('scriptHubBoxPlotGroupSelect');
        if (groupSelect) groupSelect.innerHTML = '';
        const zipBtn = document.getElementById('scriptHubOpenBpZipBtn');
        if (zipBtn) zipBtn.style.display = 'none';
        this._bpGroupedMap = null;
        this._bpPngMap = {};
        this._pepResult = null;
        this._pepSelectedChains = [];
        this._pepAvailableChains = [];
        this._pepActiveGroup = null;
        this._pepActiveChain = null;
        this._pepActiveResultType = null;
        if (this.activeModule === 'charts') {
            this.resetChartWorkflow();
        }
        const pepLinks = document.getElementById('scriptHubPepResultLinks');
        if (pepLinks) pepLinks.innerHTML = '';
        const pepImage = document.getElementById('scriptHubPepResultImage');
        if (pepImage) pepImage.innerHTML = '<p class="text-muted small">Select result type and chain above to view.</p>';
        const pepGroupSelect = document.getElementById('scriptHubPepGroupSelect');
        if (pepGroupSelect) pepGroupSelect.innerHTML = '<option value="">-- Select --</option>';
        const pepChainSelect = document.getElementById('scriptHubPepChainSelect');
        if (pepChainSelect) pepChainSelect.innerHTML = '<option value="">-- Select --</option>';
        this.setUiState('idle');
        this.syncModuleUI();
    },

    resetChartWorkflow() {
        this.chartScanResult = null;
        this.chartSamples = [];
        this.chartSelectedChains = [];
        this.chartSelectedSampleKeys = new Set();
        this.chartSelectedFilePath = '';
        this.chartFileColumns = [];
        this.chartFieldMapping = { cdr3_column: '', copy_column: '', v_column: '', j_column: '' };
        this.renderChartChainList();
        this.renderChartSampleList();
        this.renderChartPreviewTable([], []);
        const summary = document.getElementById('scriptHubChartSummary');
        if (summary) {
            const basePath = this.getPrimaryPepPath();
            summary.className = 'alert alert-info mb-0';
            summary.textContent = basePath
                ? `综合图表将使用第一个 PEP 路径：${basePath}`
                : '请先在数据选择中加入 PEP 路径。';
        }
        const fieldStep = document.getElementById('scriptHubChartFieldStep');
        const runStep = document.getElementById('scriptHubChartRunStep');
        if (fieldStep) fieldStep.style.display = 'none';
        if (runStep) runStep.style.display = 'none';
        const results = document.getElementById('scriptHubChartResults');
        if (results) results.innerHTML = '';
        const flow = document.getElementById('scriptHubChartFlow');
        if (flow) flow.classList.remove('has-confirmed-samples');
        this.updateChartModuleCards();
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

    getPrimaryPepPath() {
        return (this.selectedPepPaths && this.selectedPepPaths[0])
            || document.getElementById('scriptHubBasePath')?.value?.trim()
            || '';
    },

    async prepareChartWorkflow() {
        const basePath = this.getPrimaryPepPath();
        this.resetChartWorkflow();
        if (!basePath) {
            this.showSourceFeedback('请先加入 PEP 路径后再选择综合图表。', 'warning');
            return;
        }
        if (this.selectedPepPaths.length > 1) {
            this.showSourceFeedback(`综合图表当前使用第一个 PEP 路径：${basePath}`, 'info');
        }
        await this.scanChartFolder(basePath);
    },

    async scanChartFolder(basePath) {
        this.showLoading('正在扫描综合图表数据...', '扫描图表数据');
        try {
            const response = await fetch('/api/auto-heatmap/scan-folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ base_path: basePath }),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '扫描目录失败');
            if (!data.has_chain_suffix) {
                throw new Error('综合图表需要带链后缀的 repertoire 文件，例如 SAMPLE__IGH.csv 或 SAMPLE__TRB.csv。');
            }

            this.chartScanResult = data;
            this.chartSamples = Array.isArray(data.samples) ? data.samples : [];
            this.chartSelectedChains = Array.isArray(data.all_chains) ? [...data.all_chains] : [];
            this.chartSelectedSampleKeys = new Set(this.chartSamples.map(sample => this.getChartSampleKey(sample)));
            this.chartSelectedFilePath = '';
            this.chartFileColumns = [];
            this.chartFieldMapping = { cdr3_column: '', copy_column: '', v_column: '', j_column: '' };
            this.renderChartChainList();
            this.renderChartSampleList();

            const summary = document.getElementById('scriptHubChartSummary');
            if (summary) {
                summary.className = 'alert alert-success mb-0';
                summary.textContent = data.summary || `已扫描 ${this.chartSamples.length} 个样本，${this.chartSelectedChains.length} 条链。`;
            }
        } catch (error) {
            const summary = document.getElementById('scriptHubChartSummary');
            if (summary) {
                summary.className = 'alert alert-danger mb-0';
                summary.textContent = error.message || '综合图表扫描失败';
            }
            this.showSourceFeedback(error.message || '综合图表扫描失败', 'danger');
        } finally {
            this.hideLoading();
        }
    },

    filenameMatchesChartChain(filename, chain) {
        const nameWithoutExt = String(filename || '').replace(/\.(csv|tsv|txt)(\.gz)?$/i, '');
        const normalizedName = nameWithoutExt.toUpperCase();
        const normalizedChain = String(chain || '').toUpperCase();
        return normalizedName.endsWith(`__${normalizedChain}`) || normalizedName.endsWith(`_${normalizedChain}`);
    },

    getChartSampleKey(sample) {
        return `${sample.original_name || ''}::${sample.folder_path || ''}`;
    },

    getChartSampleAvailableChains(sample) {
        const available = new Set();
        (sample.data_files || []).forEach((fileInfo) => {
            this.chartSelectedChains.forEach((chain) => {
                if (this.filenameMatchesChartChain(fileInfo.filename, chain)) {
                    available.add(chain);
                }
            });
        });
        return Array.from(available);
    },

    getVisibleChartSamples() {
        if (!this.chartSelectedChains.length) return [];
        return this.chartSamples
            .map(sample => ({ sample, chains: this.getChartSampleAvailableChains(sample) }))
            .filter(item => item.chains.length > 0);
    },

    getSelectedChartSamplesPayload() {
        const visibleKeys = new Set(this.getVisibleChartSamples().map(item => this.getChartSampleKey(item.sample)));
        return this.chartSamples
            .filter(sample => visibleKeys.has(this.getChartSampleKey(sample)) && this.chartSelectedSampleKeys.has(this.getChartSampleKey(sample)))
            .map(sample => ({
                original_name: sample.original_name,
                display_name: sample.display_name,
                folder_path: sample.folder_path,
                data_files: (sample.data_files || []).map(fileInfo => ({
                    filename: fileInfo.filename,
                    filepath: fileInfo.filepath,
                    size: fileInfo.size,
                    rows: fileInfo.rows,
                    columns: fileInfo.columns,
                })),
            }));
    },

    renderChartChainList() {
        const list = document.getElementById('scriptHubChartChainList');
        const summary = document.getElementById('scriptHubChartChainSummary');
        if (!list) return;
        const allChains = Array.isArray(this.chartScanResult?.all_chains) ? this.chartScanResult.all_chains : [];
        if (!allChains.length) {
            list.innerHTML = '<div class="sh-selection-empty">等待扫描 PEP 路径。</div>';
            if (summary) summary.textContent = '尚未扫描到链。';
            return;
        }
        list.innerHTML = allChains.map((chain) => {
            const sampleCount = this.chartSamples.filter(sample =>
                (sample.data_files || []).some(fileInfo => this.filenameMatchesChartChain(fileInfo.filename, chain))
            ).length;
            const selected = this.chartSelectedChains.includes(chain);
            return `<button class="sh-chart-item${selected ? ' is-selected' : ''}" type="button" data-chart-chain="${this.escapeHtml(chain)}" aria-pressed="${selected ? 'true' : 'false'}">
                <strong>${this.escapeHtml(chain)}</strong>
                <span>${sampleCount} 个样本可用</span>
                <span class="sh-chart-check" aria-hidden="true">✓</span>
            </button>`;
        }).join('');
        if (summary) summary.textContent = `已选 ${this.chartSelectedChains.length} / ${allChains.length} 条链`;
    },

    toggleChartChain(chain) {
        if (!chain) return;
        if (this.chartSelectedChains.includes(chain)) {
            this.chartSelectedChains = this.chartSelectedChains.filter(item => item !== chain);
        } else {
            this.chartSelectedChains.push(chain);
        }
        this.renderChartChainList();
        this.renderChartSampleList();
        this.hideChartFieldAndRunSteps();
    },

    selectAllChartChains() {
        this.chartSelectedChains = Array.isArray(this.chartScanResult?.all_chains) ? [...this.chartScanResult.all_chains] : [];
        this.renderChartChainList();
        this.renderChartSampleList();
        this.hideChartFieldAndRunSteps();
    },

    invertChartChains() {
        const allChains = Array.isArray(this.chartScanResult?.all_chains) ? this.chartScanResult.all_chains : [];
        this.chartSelectedChains = allChains.filter(chain => !this.chartSelectedChains.includes(chain));
        this.renderChartChainList();
        this.renderChartSampleList();
        this.hideChartFieldAndRunSteps();
    },

    clearChartChains() {
        this.chartSelectedChains = [];
        this.renderChartChainList();
        this.renderChartSampleList();
        this.hideChartFieldAndRunSteps();
    },

    renderChartSampleList() {
        const list = document.getElementById('scriptHubChartSampleList');
        const summary = document.getElementById('scriptHubChartSampleSummary');
        if (!list || !summary) return;
        const visibleSamples = this.getVisibleChartSamples();
        if (!this.chartSelectedChains.length) {
            list.innerHTML = '<div class="sh-selection-empty">请先选择至少 1 条链。</div>';
            summary.textContent = '尚未选择链。';
            return;
        }
        if (!visibleSamples.length) {
            list.innerHTML = '<div class="sh-selection-empty">当前所选链下没有可用样本。</div>';
            summary.textContent = '0 个可选样本。';
            return;
        }
        list.innerHTML = visibleSamples.map(({ sample, chains }) => {
            const sampleKey = this.getChartSampleKey(sample);
            const selected = this.chartSelectedSampleKeys.has(sampleKey);
            const fileCount = Array.isArray(sample.data_files) ? sample.data_files.length : 0;
            const name = sample.display_name || sample.original_name || sampleKey;
            return `<button class="sh-chart-item${selected ? ' is-selected' : ''}" type="button" data-chart-sample-key="${this.escapeHtml(sampleKey)}" title="${this.escapeHtml(name)}" aria-pressed="${selected ? 'true' : 'false'}">
                <strong>${this.escapeHtml(name)}</strong>
                <span>${chains.join(', ')} · ${fileCount} 个文件</span>
                <span class="sh-chart-check" aria-hidden="true">✓</span>
            </button>`;
        }).join('');
        const selectedCount = visibleSamples.filter(({ sample }) => this.chartSelectedSampleKeys.has(this.getChartSampleKey(sample))).length;
        summary.textContent = `已选 ${selectedCount} / ${visibleSamples.length} 个样本`;
    },

    toggleChartSample(sampleKey) {
        if (!sampleKey) return;
        if (this.chartSelectedSampleKeys.has(sampleKey)) this.chartSelectedSampleKeys.delete(sampleKey);
        else this.chartSelectedSampleKeys.add(sampleKey);
        this.renderChartSampleList();
        this.hideChartFieldAndRunSteps();
    },

    selectAllChartSamples() {
        const nextSelected = new Set(this.chartSelectedSampleKeys);
        this.getVisibleChartSamples().forEach(item => nextSelected.add(this.getChartSampleKey(item.sample)));
        this.chartSelectedSampleKeys = nextSelected;
        this.renderChartSampleList();
        this.hideChartFieldAndRunSteps();
    },

    invertChartSamples() {
        const visibleKeys = new Set(this.getVisibleChartSamples().map(item => this.getChartSampleKey(item.sample)));
        const nextSelected = new Set(Array.from(this.chartSelectedSampleKeys).filter(key => !visibleKeys.has(key)));
        this.getVisibleChartSamples().forEach(({ sample }) => {
            const key = this.getChartSampleKey(sample);
            if (!this.chartSelectedSampleKeys.has(key)) nextSelected.add(key);
        });
        this.chartSelectedSampleKeys = nextSelected;
        this.renderChartSampleList();
        this.hideChartFieldAndRunSteps();
    },

    clearChartSamples() {
        const visibleKeys = new Set(this.getVisibleChartSamples().map(item => this.getChartSampleKey(item.sample)));
        this.chartSelectedSampleKeys = new Set(Array.from(this.chartSelectedSampleKeys).filter(key => !visibleKeys.has(key)));
        this.renderChartSampleList();
        this.hideChartFieldAndRunSteps();
    },

    getChartPreviewFilePath() {
        const selectedSamples = this.getSelectedChartSamplesPayload();
        for (const sample of selectedSamples) {
            for (const chain of this.chartSelectedChains) {
                const fileInfo = (sample.data_files || []).find(item => this.filenameMatchesChartChain(item.filename, chain));
                if (fileInfo?.filepath) return fileInfo.filepath;
            }
        }
        return '';
    },

    async confirmChartSamples() {
        if (!this.chartSelectedChains.length) {
            this.showError('请至少选择 1 条链');
            return;
        }
        if (this.getSelectedChartSamplesPayload().length < 2) {
            this.showError('请至少选择 2 个样本');
            return;
        }
        const previewPath = this.getChartPreviewFilePath();
        if (!previewPath) {
            this.showError('没有找到可用于字段映射的文件');
            return;
        }
        this.chartSelectedFilePath = previewPath;
        await this.loadChartFileColumns(previewPath);
    },

    async loadChartFileColumns(filepath) {
        this.showLoading('正在读取综合图表字段...', '读取字段');
        try {
            const response = await fetch('/api/auto-heatmap/get-file-columns', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath }),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '读取字段失败');
            this.chartFileColumns = Array.isArray(data.columns) ? data.columns : [];
            this.populateChartFieldSelect('scriptHubChartCdr3Column', 'cdr3_column', data.suggested_cdr3);
            this.populateChartFieldSelect('scriptHubChartCopyColumn', 'copy_column', data.suggested_copy);
            this.populateChartFieldSelect('scriptHubChartVColumn', 'v_column', null);
            this.populateChartFieldSelect('scriptHubChartJColumn', 'j_column', null);
            this.renderChartPreviewTable(this.chartFileColumns, data.sample_data || []);
            document.getElementById('scriptHubChartFieldStep').style.display = '';
            document.getElementById('scriptHubChartRunStep').style.display = 'none';
            this.updateChartConfirmedSummary();
            document.getElementById('scriptHubChartFlow')?.classList.add('has-confirmed-samples');
        } catch (error) {
            this.showError(error.message || '读取字段失败');
        } finally {
            this.hideLoading();
        }
    },

    populateChartFieldSelect(selectId, mappingKey, suggested) {
        const select = document.getElementById(selectId);
        if (!select) return;
        const columns = this.chartFileColumns || [];
        select.innerHTML = ['<option value="">-- 请选择 --</option>']
            .concat(columns.map(column => `<option value="${this.escapeHtml(column)}">${this.escapeHtml(column)}</option>`))
            .join('');
        const hints = (this.chartFieldHints[mappingKey] || []).map(item => item.toLowerCase());
        let selected = suggested && columns.includes(suggested) ? suggested : '';
        if (!selected) {
            selected = columns.find(column => hints.includes(String(column).toLowerCase())) || '';
        }
        if (selected) {
            select.value = selected;
            this.chartFieldMapping[mappingKey] = selected;
        }
        select.onchange = () => {
            this.chartFieldMapping[mappingKey] = select.value || '';
        };
    },

    renderChartPreviewTable(columns, rows) {
        const table = document.getElementById('scriptHubChartPreviewTable');
        if (!table) return;
        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');
        const safeColumns = Array.isArray(columns) ? columns : [];
        if (!safeColumns.length) {
            thead.innerHTML = '';
            tbody.innerHTML = '<tr><td class="text-muted">No preview data</td></tr>';
            return;
        }
        thead.innerHTML = `<tr>${safeColumns.map(column => `<th>${this.escapeHtml(column)}</th>`).join('')}</tr>`;
        tbody.innerHTML = (rows || []).length
            ? rows.map(row => `<tr>${safeColumns.map((_, index) => `<td>${this.escapeHtml(row[index] ?? '')}</td>`).join('')}</tr>`).join('')
            : '<tr><td class="text-muted" colspan="99">No preview rows</td></tr>';
    },

    confirmChartFields() {
        this.chartFieldMapping = {
            cdr3_column: document.getElementById('scriptHubChartCdr3Column')?.value || '',
            copy_column: document.getElementById('scriptHubChartCopyColumn')?.value || '',
            v_column: document.getElementById('scriptHubChartVColumn')?.value || '',
            j_column: document.getElementById('scriptHubChartJColumn')?.value || '',
        };
        if (Object.values(this.chartFieldMapping).some(value => !value)) {
            this.showError('请完成 CDR3、copy、V、J 字段映射');
            return;
        }
        document.getElementById('scriptHubChartRunStep').style.display = '';
    },

    hideChartFieldAndRunSteps() {
        const fieldStep = document.getElementById('scriptHubChartFieldStep');
        const runStep = document.getElementById('scriptHubChartRunStep');
        if (fieldStep) fieldStep.style.display = 'none';
        if (runStep) runStep.style.display = 'none';
        document.getElementById('scriptHubChartFlow')?.classList.remove('has-confirmed-samples');
    },

    reopenChartSampleSelection() {
        document.getElementById('scriptHubChartFlow')?.classList.remove('has-confirmed-samples');
        this.hideChartFieldAndRunSteps();
        this.renderChartChainList();
        this.renderChartSampleList();
    },

    updateChartConfirmedSummary() {
        const summary = document.getElementById('scriptHubChartConfirmedSummary');
        if (!summary) return;
        const samples = this.getSelectedChartSamplesPayload();
        const chains = this.chartSelectedChains || [];
        const sampleNames = samples
            .map(sample => sample.display_name || sample.original_name || '')
            .filter(Boolean);
        summary.textContent = `${chains.length} 条链：${chains.join(', ') || '-'}；${samples.length} 个样本：${sampleNames.slice(0, 5).join(', ')}${sampleNames.length > 5 ? ` 等 ${sampleNames.length} 个` : ''}`;
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
            `检测完成。从 ${data.base_path || '所选目录'} 检测到 ${data.sample_count || 0} 个样本。`,
            'success'
        );
        this.setInspectSummary(data.summary || `检测到 ${data.sample_count || 0} 个样本，可用于数据库比对。`, 'success');

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

    onSourceHighlight(path, type) {
        this.highlightedSource = { path, type };
        const name = this.getPathName(path);
        const addPepBtn = document.getElementById('scriptHubAddPepBtn');
        const profileBtn = document.getElementById('scriptHubSetProfileBtn');
        const hint = document.getElementById('scriptHubSourceHint');
        const isFile = type === 'file';
        const canUseProfile = isFile && this.isTabularFile(path);

        if (addPepBtn) addPepBtn.disabled = false;
        if (profileBtn) {
            profileBtn.disabled = !canUseProfile;
            profileBtn.title = canUseProfile ? '' : 'Profile 需要选择 CSV/TSV 文件';
        }
        if (hint) {
            hint.textContent = canUseProfile
                ? `已选择文件: ${name}`
                : `已选择${isFile ? '文件' : '目录'}: ${name}`;
        }
    },

    addHighlightedPep() {
        const selection = this.highlightedSource;
        if (!selection?.path) return;
        const path = selection.path;
        const exists = this.dataSelection.pepPaths.some(item => item.path === path);
        if (!exists) {
            this.dataSelection.pepPaths.push({
                path,
                type: selection.type || 'directory',
                source: 'tree',
            });
        }
        this.dataSelection.validation = null;
        this.syncDataSelectionState();
        this.showSourceFeedback(`已加入 PEP 路径：${path}`, 'success');
    },

    setHighlightedProfile() {
        const selection = this.highlightedSource;
        if (!selection?.path) return;
        if (selection.type !== 'file' || !this.isTabularFile(selection.path)) {
            this.showSourceFeedback('Profile 需要选择 CSV/TSV 文件。', 'warning');
            return;
        }
        this.dataSelection.profilePath = selection.path;
        this.dataSelection.profileType = selection.type || 'file';
        this.dataSelection.validation = null;
        this.syncDataSelectionState();
        this.showSourceFeedback(`已设置 Profile 文件：${selection.path}`, 'success');
    },

    removeSelectedPep(path) {
        this.dataSelection.pepPaths = this.dataSelection.pepPaths.filter(item => item.path !== path);
        this.dataSelection.validation = null;
        this.syncDataSelectionState();
    },

    clearSelectedProfile() {
        this.dataSelection.profilePath = '';
        this.dataSelection.profileType = '';
        this.dataSelection.validation = null;
        this.syncDataSelectionState();
    },

    syncDataSelectionState() {
        const pepPaths = this.dataSelection.pepPaths
            .map(item => typeof item === 'string' ? { path: item, type: 'directory', source: 'legacy' } : item)
            .filter(item => item && item.path);
        const deduped = [];
        const seen = new Set();
        pepPaths.forEach((item) => {
            if (seen.has(item.path)) return;
            seen.add(item.path);
            deduped.push(item);
        });
        this.dataSelection.pepPaths = deduped;
        this.selectedPepPaths = deduped.map(item => item.path);
        this.selectedDatapointPath = this.dataSelection.profilePath || '';
        this.selectedDatapointPaths = this.selectedDatapointPath ? [this.selectedDatapointPath] : [];

        const baseInput = document.getElementById('scriptHubBasePath');
        const profileInput = document.getElementById('scriptHubDatapointPath');
        const dbProfileInput = document.getElementById('scriptHubProfilePath');
        if (baseInput) baseInput.value = this.selectedPepPaths[0] || '';
        if (profileInput) profileInput.value = this.selectedDatapointPath;
        if (dbProfileInput && this.selectedDatapointPath && !dbProfileInput.value) {
            dbProfileInput.value = this.selectedDatapointPath;
        }

        this.renderDataSelectionBasket();
        this._checkBothConfirmed();
    },

    renderDataSelectionBasket() {
        const pepList = document.getElementById('scriptHubPepSelectionList');
        const profileList = document.getElementById('scriptHubProfileSelectionList');
        if (pepList) {
            pepList.innerHTML = this.dataSelection.pepPaths.length
                ? this.dataSelection.pepPaths.map((item, index) => `
                    <div class="sh-selected-row">
                        <div title="${this.escapeHtml(item.path)}">
                            <strong>${this.escapeHtml(this.getPathName(item.path) || item.path)}</strong>
                            <span>${this.escapeHtml(item.path)}</span>
                        </div>
                        <div class="sh-selected-row-actions">
                            <button class="btn btn-sm btn-outline-secondary" type="button" data-locate-path="${this.escapeHtml(item.path)}" data-locate-type="${this.escapeHtml(item.type || 'directory')}" title="在左侧文件树定位">
                                <i class="bi bi-crosshair"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger" type="button" data-remove-pep="${this.escapeHtml(item.path)}" title="移除 PEP 路径">
                                <i class="bi bi-x-lg"></i>
                            </button>
                        </div>
                    </div>
                `).join('')
                : '<div class="sh-selection-empty">尚未选择 PEP 路径</div>';
            pepList.querySelectorAll('[data-locate-path]').forEach((button) => {
                button.addEventListener('click', () => this.locatePathInSourceTree(button.dataset.locatePath || '', button.dataset.locateType || 'directory'));
            });
            pepList.querySelectorAll('[data-remove-pep]').forEach((button) => {
                button.addEventListener('click', () => this.removeSelectedPep(button.dataset.removePep || ''));
            });
        }

        if (profileList) {
            const profilePath = this.dataSelection.profilePath;
            profileList.innerHTML = profilePath
                ? `<div class="sh-selected-row">
                    <div title="${this.escapeHtml(profilePath)}">
                        <strong>${this.escapeHtml(this.getPathName(profilePath) || profilePath)}</strong>
                        <span>${this.escapeHtml(profilePath)}</span>
                    </div>
                    <div class="sh-selected-row-actions">
                        <button class="btn btn-sm btn-outline-secondary" type="button" id="scriptHubLocateProfileBtn" title="在左侧文件树定位">
                            <i class="bi bi-crosshair"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" type="button" id="scriptHubClearProfileBtn" title="清除 Profile">
                            <i class="bi bi-x-lg"></i>
                        </button>
                    </div>
                </div>`
                : '<div class="sh-selection-empty">尚未设置 Profile 文件</div>';
            document.getElementById('scriptHubLocateProfileBtn')?.addEventListener('click', () => this.locatePathInSourceTree(profilePath, 'file'));
            document.getElementById('scriptHubClearProfileBtn')?.addEventListener('click', () => this.clearSelectedProfile());
        }
    },

    async locatePathInSourceTree(path, type = 'directory') {
        if (!path) return;
        const browser = window._sourceBrowser || window._pepBrowser;
        if (!browser) return;
        const targetType = type || 'directory';
        const normalized = String(path).replace(/\\/g, '/');
        const parentPath = targetType === 'file'
            ? normalized.split('/').slice(0, -1).join('/') || normalized
            : normalized;
        await browser.goTo(parentPath);
        browser.setSelected(path, targetType);
        this.highlightedSource = { path, type: targetType };
    },

    async inspectDataSelection() {
        const projectId = document.getElementById('scriptHubProjectSelect')?.value || '';
        const body = {
            project_id: projectId || null,
            pep_paths: this.selectedPepPaths,
            profile_path: this.selectedDatapointPath || null,
        };
        const response = await fetch('/api/script-hub/data-selection/inspect', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.message || '数据选择检测失败');
        }
        this.dataSelection.validation = data;
        const profileInput = document.getElementById('scriptHubProfilePath');
        if (profileInput && data.profile_path) {
            profileInput.value = data.profile_path;
        }
        this.showSourceFeedback(
            `数据检测完成：${data.sample_count || 0} 个样本，${data.pep_file_count || 0} 个 PEP 文件，${(data.chains || []).join(', ') || '未识别链'}。`,
            (data.warnings || []).length ? 'warning' : 'success'
        );
        return data;
    },

    async saveDataSelectionToProject() {
        const projectId = document.getElementById('scriptHubProjectSelect')?.value || '';
        if (!projectId) return;

        const tasks = [];
        this.selectedPepPaths.forEach((path, index) => {
            tasks.push(this._registerPathToProject('pep', path, {
                source: 'script-hub',
                role: 'pep',
                selection_index: index,
                registered_from: 'data-selection',
            }));
        });
        if (this.selectedDatapointPath) {
            tasks.push(this._registerPathToProject('datapoint', this.selectedDatapointPath, {
                source: 'script-hub',
                role: 'profile',
                registered_from: 'data-selection',
            }));
        }
        if (!tasks.length) return;
        await Promise.all(tasks);
        this.showSourceFeedback('数据路径已保存到项目。下次选择该项目会自动带入这些路径。', 'success');
    },

    getPathName(path) {
        return String(path || '').replace(/\\/g, '/').split('/').filter(Boolean).pop() || String(path || '');
    },

    isTabularFile(path) {
        return /\.(csv|tsv|csv\.gz)$/i.test(String(path || ''));
    },

    onPepHighlight(path, type) {
        this.onSourceHighlight(path, type);
        const btn = document.getElementById('scriptHubPepConfirmBtn');
        const hint = document.getElementById('scriptHubPepConfirmHint');
        if (btn) btn.disabled = false;
        if (hint) hint.textContent = `已高亮: ${path.split('/').filter(Boolean).pop() || path}`;
    },

    onProfileHighlight(path, type) {
        const btn = document.getElementById('scriptHubProfileConfirmBtn');
        const hint = document.getElementById('scriptHubProfileConfirmHint');
        if (btn) btn.disabled = false;
        if (hint) hint.textContent = `已高亮: ${path.split('/').filter(Boolean).pop() || path}`;
    },

    confirmPep() {
        const browser = window._pepBrowser || window._sourceBrowser;
        if (!browser) return;
        const sel = browser.getSelected();
        if (!sel.path) return;
        this.highlightedSource = sel;
        this.addHighlightedPep();
        document.getElementById('scriptHubBasePath').value = sel.path;
        const confirmedPep = document.getElementById('scriptHubConfirmedPep');
        if (confirmedPep) confirmedPep.textContent = sel.path;
        document.getElementById('scriptHubConfirmedPanel')?.classList.remove('d-none');
        const btn = document.getElementById('scriptHubPepConfirmBtn');
        if (btn) {
            btn.disabled = true;
            btn.className = 'btn btn-primary btn-sm';
            btn.innerHTML = '<i class="bi bi-check-circle-fill"></i> PEP 已确认';
        }
        this._checkBothConfirmed();
    },

    confirmProfile() {
        const browser = window._profileBrowser || window._sourceBrowser;
        if (!browser) return;
        const sel = browser.getSelected();
        if (!sel.path) return;
        this.highlightedSource = sel;
        this.setHighlightedProfile();
        document.getElementById('scriptHubDatapointPath').value = sel.path;
        const confirmedProfile = document.getElementById('scriptHubConfirmedProfile');
        if (confirmedProfile) confirmedProfile.textContent = sel.path;
        document.getElementById('scriptHubConfirmedPanel')?.classList.remove('d-none');
        const btn = document.getElementById('scriptHubProfileConfirmBtn');
        if (btn) {
            btn.disabled = true;
            btn.className = 'btn btn-success btn-sm';
            btn.innerHTML = '<i class="bi bi-check-circle-fill"></i> Profile 已确认';
        }
        this._checkBothConfirmed();
    },

    _checkBothConfirmed() {
        const pep = this.selectedPepPaths[0] || document.getElementById('scriptHubBasePath')?.value?.trim() || '';
        const dp = this.selectedDatapointPath || document.getElementById('scriptHubDatapointPath')?.value?.trim() || '';
        const both = !!(pep && dp);
        const any = !!(pep || dp);

        // Enable the main confirm button if at least one is confirmed
        const mainBtn = document.getElementById('scriptHubDataConfirmBtn');
        if (mainBtn) mainBtn.disabled = !any;

        this.selectedDatapointPaths = dp ? [dp] : [];
        this.selectedDatapointPath = dp || '';

        if (any) {
            this.evaluateAvailableModules(this.selectedPepPaths, this.selectedDatapointPaths);
            this.showSourceFeedback(
                both ? 'PEP 和 Profile 均已确认。点击下方按钮进入下一步。' : (pep ? 'PEP 已确认，还需确认 Profile。' : 'Profile 已确认，还需确认 PEP。'),
                both ? 'success' : 'info'
            );
        }
    },


    async inspectBasePath(explicitBasePath = '', loadingText = 'Scanning asset directory...') {
        const module = this.activeModule || 'db-alignment';

        if (module === 'boxplot') {
            return this.inspectBoxPlot(explicitBasePath, loadingText);
        }
        if (module === 'pep-analysis') {
            return this.inspectPepAnalysis(explicitBasePath, loadingText);
        }
        if (module === 'topclone') {
            return this.inspectTopClone(loadingText);
        }
        if (module === 'umap') {
            return this.inspectUmap(loadingText);
        }
        if (module === 'volcano') {
            return this.inspectVolcano(explicitBasePath, loadingText);
        }
        if (module === 'umapin') {
            return this.inspectUmapin(explicitBasePath, loadingText);
        }

        const basePath = explicitBasePath
            || (this.selectedPepPaths.length ? this.selectedPepPaths[0] : '')
            || document.getElementById('scriptHubBasePath')?.value?.trim() || '';

        if (!basePath) {
            this.showSourceFeedback('请先提供基础目录。', 'warning');
            this.showError('请先提供基础目录');
            return;
        }

        this.setUiState('inspecting');
        this.showSourceFeedback(`Inspecting ${basePath}...`, 'secondary');
        this.showLoading(loadingText, 'Inspect assets');
        try {
            const body = {
                base_path: basePath,
                profile_path: this.selectedDatapointPath || document.getElementById('scriptHubProfilePath')?.value?.trim() || null,
                field_mapping: {
                    cdr3_column: document.getElementById('scriptHubCdr3Column')?.value || '',
                    copy_column: document.getElementById('scriptHubCopyColumn')?.value || '',
                },
            };
            const response = await fetch('/api/script-hub/db-alignment/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to inspect DB alignment assets');
            }

            document.getElementById('scriptHubBasePath').value = data.base_path || basePath;
            if (data.profile_path) {
                this.dataSelection.profilePath = data.profile_path;
                this.syncDataSelectionState();
            }
            this.renderInspection(data);
            this._registerPathToProject('pep', data.base_path);
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
        const basePath = explicitBasePath || '';
        const datapointPath = this.selectedDatapointPath
            || document.getElementById('scriptHubDatapointPath')?.value
            || document.getElementById('scriptHubBpDatapointPath')?.value
            || '';

        if (!datapointPath) {
            this.showSourceFeedback('请先选择一个 Profile 文件。', 'warning');
            this.showError('请先选择一个 Profile 文件');
            return;
        }

        this.setUiState('inspecting');
        this.showSourceFeedback(`Inspecting Profile file...`, 'secondary');
        this.showLoading(loadingText || 'Scanning Profile file...', 'Inspect Profile');
        try {
            const body = {
                base_path: datapointPath,
                datapoint_path: datapointPath || null,
            };

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

            const fileSelects = [
                document.getElementById('scriptHubDatapointPath'),
                document.getElementById('scriptHubBpDatapointPath'),
            ].filter(Boolean);
            const candidates = Array.isArray(data.file_candidates) ? data.file_candidates : [];
            fileSelects.forEach(fileSelect => {
                fileSelect.innerHTML = candidates.length
                    ? candidates.map((f) => {
                        const parts = f.replace(/\\/g, '/').split('/');
                        const basename = parts[parts.length - 1] || f;
                        return `<option value="${this.escapeHtml(f)}">${this.escapeHtml(basename)}</option>`;
                    }).join('')
                    : '<option value="">No CSV/TSV files found</option>';
                if (data.datapoint_path) {
                    fileSelect.value = data.datapoint_path;
                }
            });

            this.showSourceFeedback(
                `箱线图检测完成。在 ${data.datapoint_path || '数据文件'} 中检测到 ${data.column_count || 0} 列。`,
                'success'
            );
            this.setInspectSummary(`数据文件：${data.datapoint_path} — ${data.column_count} 列`, 'success');
            this._registerPathToProject('datapoint', data.datapoint_path);

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

            const paramBegin = document.getElementById('scriptHubParamBegin');
            const paramOver = document.getElementById('scriptHubParamOver');

            [paramBegin, paramOver].forEach((select) => {
                select.innerHTML = columns.map((col) => `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`).join('');
            });

            if (paramBegin && columns.length) paramBegin.value = data.suggested_param_begin || columns[0];
            if (paramOver && columns.length) paramOver.value = data.suggested_param_over || (columns.length > 1 ? columns[columns.length - 1] : columns[0]);

            const bpChips = document.getElementById('scriptHubBoxplotGroupChips');
            if (bpChips) {
                bpChips.innerHTML = columns.map((col) =>
                    `<span class="sh-chip sh-chip-selectable" data-value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</span>`
                ).join('');
                // Auto-select first column chip
                const firstChip = bpChips.querySelector('.sh-chip-selectable');
                if (firstChip) firstChip.classList.add('sh-chip-selected');
                this._selectedGroupFields = this._getSelectedGroupFields();
                this.detectGroupValuesForAll();
            }

            document.getElementById('scriptHubDatapointPath').value = data.datapoint_path || '';
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

    _getSelectedGroupFields() {
        const chips = document.querySelectorAll('#scriptHubBoxplotGroupChips .sh-chip-selected');
        return Array.from(chips).map(c => c.dataset.value || '').filter(Boolean);
    },

    async detectGroupValuesForAll() {
        const fields = this._getSelectedGroupFields();
        const filePath = document.getElementById('scriptHubDatapointPath')?.value?.trim();
        const container = document.getElementById('scriptHubBoxplotFieldOrderGroups');
        if (!container) return;
        if (!filePath || fields.length === 0) {
            container.innerHTML = '<span class="small text-muted">Select group fields to configure ordering.</span>';
            return;
        }

        let html = '';

        for (const field of fields) {
            try {
                const body = { file_path: filePath, column: field };
                const response = await fetch('/api/script-hub/boxplot/group-values', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await response.json();
                const values = Array.isArray(data.values) ? data.values : [];
                if (values.length === 0) continue;

                html += `<div class="sh-field-order-group">
                    <div class="sh-field-order-label">${this.escapeHtml(field)}</div>
                    <div class="sh-sortable-chips" data-field="${this.escapeHtml(field)}">`;
                html += values.map((v, i) =>
                    `<span class="sh-sortable-chip" draggable="true" data-value="${this.escapeHtml(v)}" data-index="${i}">
                        <span class="sh-drag-handle">⋮⋮</span>${this.escapeHtml(v)}
                    </span>`
                ).join('');
                html += `</div></div>`;
            } catch (error) {
                console.warn('detectGroupValuesForAll failed for', field, error);
            }
        }

        container.innerHTML = html || '<span class="small text-muted">No groups detected.</span>';
        container.querySelectorAll('.sh-sortable-chips').forEach((sc) => {
            this._bindSortableChipEvents(sc);
        });
    },

    _bindSortableChipEvents(container) {
        let dragged = null;
        container.querySelectorAll('.sh-sortable-chip').forEach((chip) => {
            chip.addEventListener('dragstart', (e) => {
                dragged = chip;
                chip.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', chip.dataset.value || '');
            });
            chip.addEventListener('dragend', () => {
                chip.classList.remove('dragging');
                container.querySelectorAll('.sh-sortable-chip').forEach(c => c.classList.remove('drag-over'));
                dragged = null;
            });
            chip.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                if (chip !== dragged) chip.classList.add('drag-over');
            });
            chip.addEventListener('dragleave', () => {
                chip.classList.remove('drag-over');
            });
            chip.addEventListener('drop', (e) => {
                e.preventDefault();
                chip.classList.remove('drag-over');
                if (dragged && dragged !== chip) {
                    const rect = chip.getBoundingClientRect();
                    if (e.clientX < rect.left + rect.width / 2) {
                        container.insertBefore(dragged, chip);
                    } else {
                        container.insertBefore(dragged, chip.nextSibling);
                    }
                }
            });
        });
    },

    _getGroupOrderFromChips() {
        const result = {};
        document.querySelectorAll('#scriptHubBoxplotFieldOrderGroups .sh-sortable-chips').forEach((sc) => {
            const field = sc.dataset.field || '';
            const values = Array.from(sc.querySelectorAll('.sh-sortable-chip')).map(c => c.dataset.value || '');
            if (field && values.length > 0) result[field] = values.join(', ');
        });
        return Object.keys(result).length > 0 ? JSON.stringify(result) : '';
    },

    _resolveTcDatapointPath() {
        const toggle = document.getElementById('scriptHubTcSameDirToggle');
        if (toggle && toggle.checked) {
            return document.getElementById('scriptHubTcPepDataPath')?.value?.trim() || '';
        }
        return document.getElementById('scriptHubTcDatapointPath')?.value?.trim() || '';
    },

    async inspectTopClone(loadingText = 'Scanning pep_data...') {
        let pepDataPath = document.getElementById('scriptHubTcPepDataPath')?.value?.trim() || '';
        let datapointPath = this._resolveTcDatapointPath();

        if (!pepDataPath) {
            pepDataPath = (this.selectedPepPaths.length ? this.selectedPepPaths[0] : '')
                || document.getElementById('scriptHubBasePath')?.value?.trim()
                || '';
            if (pepDataPath) {
                document.getElementById('scriptHubTcPepDataPath').value = pepDataPath;
            }
        }
        if (!datapointPath) {
            datapointPath = this.selectedDatapointPath
                || document.getElementById('scriptHubDatapointPath')?.value?.trim()
                || '';
            if (datapointPath) {
                document.getElementById('scriptHubTcDatapointPath').value = datapointPath;
            }
        }

        if (!pepDataPath) {
            this.showSourceFeedback('Please provide a pep_data path.', 'warning');
            this.showError('Please provide a pep_data path');
            return;
        }

        this.setUiState('inspecting');
        this.showSourceFeedback('Inspecting TopClone assets...', 'secondary');
        this.showLoading(loadingText || 'Scanning pep_data...', 'Inspect TopClone');
        try {
            const body = { pep_data_path: pepDataPath, datapoint_path: datapointPath };
            const response = await fetch('/api/script-hub/topclone/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to inspect TopClone assets');
            }

            this.inspectData = data;
            this.result = null;
            this.setUiState('inspected');

            document.getElementById('scriptHubColumnCount').textContent = data.chain_count || 0;
            document.getElementById('scriptHubColumnChips').innerHTML = (Array.isArray(data.chains) ? data.chains : [])
                .map((c) => `<span class="sh-chip">${this.escapeHtml(c)}</span>`).join('');

            const groupField = document.getElementById('scriptHubTcGroupField');
            if (groupField && Array.isArray(data.category_cols)) {
                groupField.innerHTML = '<option value="">-- Select group field --</option>' +
                    data.category_cols.map((c) => `<option value="${this.escapeHtml(c)}">${this.escapeHtml(c)}</option>`).join('');
            }

            this.showSourceFeedback(
                `TopClone 检测完成。发现 ${data.chain_count} 条链，${data.sample_count} 个样本。`,
                'success'
            );
            this.setInspectSummary(`链：${(data.chains || []).join(', ')} — ${data.sample_count} 个样本`, 'success');
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.setInspectSummary(error.message || 'TopClone inspection failed', 'danger');
            this.showSourceFeedback(error.message || 'TopClone inspection failed.', 'danger');
            this.showError(error.message || 'TopClone inspection failed');
        } finally {
            this.hideLoading();
        }
    },

    async onDatapointFileChange() {
        const filePath = document.getElementById('scriptHubDatapointPath')?.value?.trim();
        if (!filePath) return;

        try {
            const body = { file_path: filePath };

            const response = await fetch('/api/script-hub/boxplot/columns', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to read columns');
            }

            const columns = Array.isArray(data.columns) ? data.columns : [];
            const paramBegin = document.getElementById('scriptHubParamBegin');
            const paramOver = document.getElementById('scriptHubParamOver');

            [paramBegin, paramOver].forEach((select) => {
                if (select) {
                    select.innerHTML = columns.map((col) =>
                        `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`
                    ).join('');
                }
            });

            if (paramBegin && columns.length) paramBegin.value = data.suggested_param_begin || columns[0];
            if (paramOver && columns.length) paramOver.value = data.suggested_param_over || (columns.length > 1 ? columns[columns.length - 1] : columns[0]);

            const bpChips = document.getElementById('scriptHubBoxplotGroupChips');
            if (bpChips) {
                bpChips.innerHTML = columns.map((col) =>
                    `<span class="sh-chip sh-chip-selectable" data-value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</span>`
                ).join('');
                const firstChip = bpChips.querySelector('.sh-chip-selectable');
                if (firstChip) firstChip.classList.add('sh-chip-selected');
                this._selectedGroupFields = this._getSelectedGroupFields();
                this.detectGroupValuesForAll();
            }

            document.getElementById('scriptHubColumnCount').textContent = columns.length;
            document.getElementById('scriptHubColumnChips').innerHTML = columns.length
                ? columns.map((col) => `<span class="sh-chip">${this.escapeHtml(col)}</span>`).join('')
                : '<span class="sh-chip">No columns detected</span>';
            document.getElementById('scriptHubBpParamSuggestion').textContent =
                `${data.suggested_param_begin || '-'} → ${data.suggested_param_over || '-'}`;
            this.setInspectSummary(`Datapoint: ${filePath} — ${columns.length} columns`, 'success');
            this.showSourceFeedback(`Loaded ${columns.length} columns from the selected file.`, 'success');
        } catch (error) {
            this.showError(error.message || 'Failed to read file columns');
            this.showSourceFeedback(error.message || 'Failed to read columns.', 'danger');
        }
    },

    async inspectProfile(explicitBasePath = '', loadingText = 'Scanning for Profile files...') {
        const basePath = explicitBasePath || document.getElementById('scriptHubBasePath')?.value?.trim() || '';

        if (!basePath) {
            this.showSourceFeedback('Please provide a base path.', 'warning');
            this.showError('Please provide a base path');
            return;
        }

        this.setUiState('inspecting');
        this.showSourceFeedback('Inspecting for Profile datapoint...', 'secondary');
        this.showLoading(loadingText || 'Scanning for Profile files...', 'Inspect Profile assets');
        try {
            const body = { base_path: basePath };

            const response = await fetch('/api/script-hub/profile/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to inspect Profile assets');
            }

            this.inspectData = data;
            this.result = null;
            this.lastInspectedBasePath = basePath;
            this.setUiState('inspected');

            const fileSelect = document.getElementById('scriptHubDatapointPath');
            const candidates = Array.isArray(data.file_candidates) ? data.file_candidates : [];
            if (fileSelect) {
                fileSelect.innerHTML = candidates.length
                    ? candidates.map((f) => {
                        const parts = f.replace(/\\/g, '/').split('/');
                        const basename = parts[parts.length - 1] || f;
                        return `<option value="${this.escapeHtml(f)}">${this.escapeHtml(basename)}</option>`;
                    }).join('')
                    : '<option value="">No CSV/TSV files found</option>';
                if (data.datapoint_path) fileSelect.value = data.datapoint_path;
            }

            this.showSourceFeedback(
                `Profile inspection completed. Detected ${data.column_count || 0} columns.`,
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

            const groupBegin = document.getElementById('scriptHubProfileGroupBegin');
            const groupOver = document.getElementById('scriptHubProfileGroupOver');
            const paramBegin = document.getElementById('scriptHubParamBegin');
            const paramOver = document.getElementById('scriptHubParamOver');

            [groupBegin, groupOver, paramBegin, paramOver].forEach((select) => {
                if (select) {
                    select.innerHTML = columns.map((col) =>
                        `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`
                    ).join('');
                }
            });

            if (groupBegin && columns.length) groupBegin.value = data.suggested_grouping_begin || columns[0];
            if (groupOver && columns.length) groupOver.value = data.suggested_grouping_over || columns[0];
            if (paramBegin && columns.length) paramBegin.value = data.suggested_param_begin || columns[0];
            if (paramOver && columns.length) paramOver.value = data.suggested_param_over || (columns.length > 1 ? columns[columns.length - 1] : columns[0]);

            document.getElementById('scriptHubProfileGroupSuggestion').textContent =
                `${data.suggested_grouping_begin || '-'} → ${data.suggested_grouping_over || '-'}`;
            document.getElementById('scriptHubProfileParamSuggestion').textContent =
                `${data.suggested_param_begin || '-'} → ${data.suggested_param_over || '-'}`;
            document.getElementById('scriptHubProfileSuggestions')?.classList.remove('sh-hidden');

            document.getElementById('scriptHubResultLog').textContent = '等待结果。';
            document.getElementById('scriptHubResultSummary').textContent = 'Profile analysis completed.';
            document.getElementById('scriptHubResultMeta').textContent = '任务完成后在这里查看 Profile 结果、PNGs 和 p-value CSVs。';

            window.setTimeout(() => {
                document.getElementById('scriptHubAssetsStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 80);
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.setInspectSummary(error.message || 'Profile inspection failed', 'danger');
            this.showSourceFeedback(error.message || 'Profile inspection failed.', 'danger');
            this.showError(error.message || 'Profile inspection failed');
        } finally {
            this.hideLoading();
        }
    },

    async onProfileFileChange() {
        const filePath = document.getElementById('scriptHubDatapointPath')?.value?.trim();
        if (!filePath) return;

        try {
            const body = { file_path: filePath };

            const response = await fetch('/api/script-hub/profile/columns', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to read columns');
            }

            const columns = Array.isArray(data.columns) ? data.columns : [];
            const groupBegin = document.getElementById('scriptHubProfileGroupBegin');
            const groupOver = document.getElementById('scriptHubProfileGroupOver');
            const paramBegin = document.getElementById('scriptHubParamBegin');
            const paramOver = document.getElementById('scriptHubParamOver');

            [groupBegin, groupOver, paramBegin, paramOver].forEach((select) => {
                if (select) {
                    select.innerHTML = columns.map((col) =>
                        `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`
                    ).join('');
                }
            });

            if (groupBegin && columns.length) groupBegin.value = data.suggested_grouping_begin || columns[0];
            if (groupOver && columns.length) groupOver.value = data.suggested_grouping_over || columns[0];
            if (paramBegin && columns.length) paramBegin.value = data.suggested_param_begin || columns[0];
            if (paramOver && columns.length) paramOver.value = data.suggested_param_over || (columns.length > 1 ? columns[columns.length - 1] : columns[0]);

            document.getElementById('scriptHubColumnCount').textContent = columns.length;
            document.getElementById('scriptHubColumnChips').innerHTML = columns.length
                ? columns.map((col) => `<span class="sh-chip">${this.escapeHtml(col)}</span>`).join('')
                : '<span class="sh-chip">No columns detected</span>';
            document.getElementById('scriptHubProfileGroupSuggestion').textContent =
                `${data.suggested_grouping_begin || '-'} → ${data.suggested_grouping_over || '-'}`;
            document.getElementById('scriptHubProfileParamSuggestion').textContent =
                `${data.suggested_param_begin || '-'} → ${data.suggested_param_over || '-'}`;
            this.setInspectSummary(`Datapoint: ${filePath} — ${columns.length} columns`, 'success');
            this.showSourceFeedback(`Loaded ${columns.length} columns from the selected file.`, 'success');
            this.detectGroupValues();
        } catch (error) {
            this.showError(error.message || 'Failed to read file columns');
            this.showSourceFeedback(error.message || 'Failed to read columns.', 'danger');
        }
    },

    collectRunPayload() {
        if (this.activeModule === 'boxplot') {
            const datapointPath = document.getElementById('scriptHubDatapointPath')?.value?.trim() || '';
            if (!datapointPath || !this.inspectData) {
                throw new Error('Please inspect a datapoint file before running BoxPlot');
            }
            const groupToggle = document.getElementById('scriptHubBoxplotGroupToggle');
            const useGrouping = groupToggle ? groupToggle.checked : true;
            const selectedGroupFields = useGrouping ? this._getSelectedGroupFields() : [];
            const groupOrder = useGrouping ? this._getGroupOrderFromChips() : '';
            return {
                module: 'boxplot',
                datapoint_path: datapointPath,
                grouptype_fields: selectedGroupFields,
                classification_begin: '',
                classification_over: '',
                group_order: useGrouping ? groupOrder : '',
                param_begin: document.getElementById('scriptHubParamBegin')?.value || '',
                param_over: document.getElementById('scriptHubParamOver')?.value || '',
                pvalue_threshold: parseFloat(document.getElementById('scriptHubPvalueThreshold')?.value || '0.05'),
                output_name: document.getElementById('scriptHubOutputName')?.value?.trim() || null,
            };
        }

        if (this.activeModule === 'volcano') {
            const dataDir = document.getElementById('scriptHubVolcanoDataDir')?.value?.trim() || '';
            if (!dataDir) throw new Error('请先检测数据目录');
            return {
                module: 'volcano',
                data_dir: dataDir,
                pvalue_threshold: parseFloat(document.getElementById('scriptHubVolcanoPvalueThreshold')?.value || '0.05'),
            };
        }

        if (this.activeModule === 'umapin') {
            const dataPath = document.getElementById('scriptHubUmapinDataPath')?.value?.trim() || '';
            if (!dataPath || !this.inspectData) throw new Error('请先检测数据文件');
            return {
                module: 'umapin',
                data_path: dataPath,
                param_begin: document.getElementById('scriptHubParamBegin')?.value || '',
                param_over: document.getElementById('scriptHubParamOver')?.value || '',
                category_col: document.getElementById('scriptHubUmapinCategoryCol')?.value || 'Category',
                n_neighbors: parseInt(document.getElementById('scriptHubUmapinNNeighbors')?.value || '6'),
                min_dist: parseFloat(document.getElementById('scriptHubUmapinMinDist')?.value || '0.01'),
                do_fdr: document.getElementById('scriptHubUmapinFdrToggle')?.checked || false,
            };
        }

        if (this.activeModule === 'umap') {
            const datapointPath = document.getElementById('scriptHubDatapointPath')?.value?.trim() || '';
            if (!datapointPath || !this.inspectData) {
                throw new Error('Please inspect a datapoint file before running UMAP');
            }
            return {
                module: 'umap',
                datapoint_path: datapointPath,
                classification_begin: document.getElementById('scriptHubParamBegin')?.value || '',
                classification_over: document.getElementById('scriptHubParamOver')?.value || '',
                param_begin: document.getElementById('scriptHubParamBegin')?.value || '',
                param_over: document.getElementById('scriptHubParamOver')?.value || '',
                pvalue_threshold: parseFloat(document.getElementById('scriptHubPvalueThreshold')?.value || '0.05'),
                n_neighbors: parseInt(document.getElementById('scriptHubUmapNNeighbors')?.value || '6', 10),
                min_dist: parseFloat(document.getElementById('scriptHubUmapMinDist')?.value || '0.01'),
                output_name: document.getElementById('scriptHubOutputName')?.value?.trim() || null,
            };
        }

        if (this.activeModule === 'topclone') {
            const pepDataPath = document.getElementById('scriptHubTcPepDataPath')?.value?.trim() || '';
            const datapointPath = this._resolveTcDatapointPath();
            if (!pepDataPath) {
                throw new Error('Please provide a pep_data path');
            }
            const modeToggle = document.getElementById('scriptHubTcModeToggle');
            const mode = modeToggle?.checked ? 'per_sample' : 'trace';
            return {
                module: 'topclone',
                pep_data_path: pepDataPath,
                datapoint_path: datapointPath,
                mode: mode,
                top_n: parseInt(document.getElementById('scriptHubTcTopN')?.value || '10', 10),
                group_field: document.getElementById('scriptHubTcGroupField')?.value || null,
                group_order: this._getGroupOrderFromChips() || null,
                pvalue_threshold: parseFloat(document.getElementById('scriptHubPvalueThreshold')?.value || '0.05'),
                output_name: document.getElementById('scriptHubOutputName')?.value?.trim() || null,
            };
        }

        if (this.activeModule === 'charts') {
            return this.collectChartRunPayload();
        }

        if (this.activeModule === 'pep-analysis') {
            const pepDir = document.getElementById('scriptHubPepDataDir')?.value?.trim()
                || (this.selectedPepPaths.length ? this.selectedPepPaths[0] : '');
            if (!pepDir || !this.inspectData) {
                throw new Error('Please inspect a base directory before running CDR3 sharing analysis');
            }
            const profilePath = document.getElementById('scriptHubPepProfilePath')?.value
                || this.selectedDatapointPath
                || '';
            if (!profilePath) throw new Error('Please select a Profile file');
            const chains = this._pepSelectedChains || [];
            if (!chains.length) throw new Error('Please select at least one chain');
            const groupFieldsSelect = document.getElementById('scriptHubPepGroupFields');
            const groupFields = Array.from(groupFieldsSelect?.selectedOptions || []).map(o => o.value).filter(Boolean);
            if (!groupFields.length) throw new Error('Please select at least one group field');
            const projectId = document.getElementById('scriptHubProjectSelect')?.value || '';
            return {
                module: 'pep-analysis',
                pep_data_dir: pepDir,
                profile_path: profilePath,
                group_fields: groupFields,
                selected_chains: chains,
                pvalue_threshold: parseFloat(document.getElementById('scriptHubPepPvalueThreshold')?.value || '0.05'),
                min_sample_threshold: parseInt(document.getElementById('scriptHubPepMinSample')?.value || '3'),
                output_name: document.getElementById('scriptHubOutputName')?.value?.trim() || null,
                project_id: projectId || null,
            };
        }

        const allPepPaths = [...new Set([...this.selectedPepPaths, ...this.customPepPaths])];
        const basePath = allPepPaths[0] || document.getElementById('scriptHubBasePath')?.value?.trim() || '';
        const allDpPaths = this.selectedDatapointPaths;
        const datapointPath = allDpPaths[0] || document.getElementById('scriptHubDatapointPath')?.value?.trim() || '';

        if (!basePath && allPepPaths.length === 0) {
            throw new Error('请先选择数据');
        }
        return {
            module: 'db-alignment',
            base_path: basePath || null,
            output_name: document.getElementById('scriptHubOutputName')?.value?.trim() || null,
            profile_path: this.selectedDatapointPath || document.getElementById('scriptHubProfilePath')?.value?.trim() || null,
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
            pep_paths: allPepPaths.length > 0 ? allPepPaths : null,
            datapoint_paths: allDpPaths.length > 0 ? allDpPaths : null,
        };
    },

    async runDbAlignment() {
        try {
            const payload = this.collectRunPayload();
            const module = this.activeModule || 'db-alignment';
            if (module === 'charts') {
                await this.runChartAnalysis(payload);
                return;
            }
            const isBoxPlot = module === 'boxplot';
            const isTopClone = module === 'topclone';
            const isPep = module === 'pep-analysis';
            const isUmap = module === 'umap';
            const isVolcano = module === 'volcano';
            const isUmapinModule = module === 'umapin';
            const endpoint = isUmapinModule ? '/api/script-hub/umapin/run'
                : (isVolcano ? '/api/script-hub/volcano/run'
                : (isUmap ? '/api/script-hub/umap/run'
                : (isTopClone ? '/api/script-hub/topclone/run'
                : (isPep ? '/api/script-hub/pep-analysis/run'
                : (isBoxPlot ? '/api/script-hub/boxplot/run'
                : '/api/script-hub/db-alignment/run')))));
            const label = isUmapinModule ? 'UMAPin' : (isVolcano ? '火山图' : (isUmap ? 'UMAP' : (isTopClone ? 'TopClone' : (isPep ? 'CDR3共享' : (isBoxPlot ? '箱线图' : '数据库比对')))));

            this.setUiState('running');
            this.showSourceFeedback(`配置已锁定，正在提交${label}任务...`, 'info');
            this.showLoading(`正在提交${label}任务...`, '排队中');

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

    getSelectedChartModules() {
        return [
            ['heatmap', 'scriptHubChartHeatmap'],
            ['treemap', 'scriptHubChartTreemap'],
            ['chord', 'scriptHubChartChord'],
        ]
            .filter(([, id]) => document.getElementById(id)?.checked)
            .map(([key]) => key);
    },

    setChartModuleSelection(moduleKeys) {
        const selected = new Set(moduleKeys || []);
        [
            ['heatmap', 'scriptHubChartHeatmap'],
            ['treemap', 'scriptHubChartTreemap'],
            ['chord', 'scriptHubChartChord'],
        ].forEach(([key, id]) => {
            const input = document.getElementById(id);
            if (input) input.checked = selected.has(key);
        });
        this.updateChartModuleCards();
    },

    updateChartModuleCards() {
        const modules = [
            ['heatmap', 'scriptHubChartHeatmap'],
            ['treemap', 'scriptHubChartTreemap'],
            ['chord', 'scriptHubChartChord'],
        ];
        let selectedCount = 0;
        modules.forEach(([, id]) => {
            const input = document.getElementById(id);
            if (!input) return;
            const card = input.closest('.module-option');
            const isSelected = Boolean(input.checked);
            if (isSelected) selectedCount += 1;
            card?.classList.toggle('is-selected', isSelected);
        });
        const summary = document.getElementById('scriptHubChartModuleSummary');
        if (summary) {
            summary.textContent = selectedCount
                ? `已选 ${selectedCount} / ${modules.length} 个图表模块`
                : '未选择图表模块，运行前至少选择 1 个';
            summary.classList.toggle('text-danger', selectedCount === 0);
            summary.classList.toggle('text-muted', selectedCount > 0);
        }
    },

    collectChartRunPayload() {
        const samples = this.getSelectedChartSamplesPayload();
        const chartModules = this.getSelectedChartModules();
        const basePath = this.getPrimaryPepPath();
        this.chartFieldMapping = {
            cdr3_column: document.getElementById('scriptHubChartCdr3Column')?.value || '',
            copy_column: document.getElementById('scriptHubChartCopyColumn')?.value || '',
            v_column: document.getElementById('scriptHubChartVColumn')?.value || '',
            j_column: document.getElementById('scriptHubChartJColumn')?.value || '',
        };
        if (!basePath) throw new Error('请先确认 PEP 数据路径。');
        if (!this.chartSelectedChains.length) throw new Error('请至少选择 1 条链。');
        if (samples.length < 2) throw new Error('请至少选择 2 个样本。');
        if (Object.values(this.chartFieldMapping).some(value => !value)) {
            throw new Error('请完成 CDR3、copy、V、J 字段映射。');
        }
        if (!chartModules.length) {
            throw new Error('请至少选择一个图表报告内容。');
        }
        return {
            module: 'charts',
            samples,
            selected_chains: this.chartSelectedChains,
            selected_modules: chartModules,
            field_mapping: this.chartFieldMapping,
            config: {
                base_path: basePath,
                output_name: document.getElementById('scriptHubOutputName')?.value?.trim() || null,
                heatmap_color_scheme: document.getElementById('scriptHubChartHeatmapColorScheme')?.value || 'viridis',
                heatmap_annotation: document.getElementById('scriptHubChartHeatmapAnnotation')?.checked ?? true,
                treemap_min_copy_default: Number(document.getElementById('scriptHubChartTreemapMinCopyDefault')?.value || 30),
                treemap_top_n: Number(document.getElementById('scriptHubChartTreemapTopN')?.value || 100),
                treemap_layout_mode: document.getElementById('scriptHubChartTreemapLayoutMode')?.value || 'tetris',
                treemap_canvas_shape: document.getElementById('scriptHubChartTreemapCanvasShape')?.value || 'square',
                treemap_topclone_only: document.getElementById('scriptHubChartTreemapTopcloneOnly')?.checked ?? false,
            },
        };
    },

    async runChartAnalysis(payload) {
        this.setUiState('running');
        this.showSourceFeedback('配置已锁定，正在提交综合图表任务...', 'info');
        this.showLoading('正在提交综合图表任务...', '排队中');
        try {
            const response = await fetch('/api/combined-analysis/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    samples: payload.samples,
                    selected_chains: payload.selected_chains,
                    selected_modules: payload.selected_modules,
                    field_mapping: payload.field_mapping,
                    config: payload.config,
                }),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '创建综合图表任务失败');
            this.activeTaskId = data.task_id;
            this.stopTaskPolling();
            this.pollChartTaskStatus(data.task_id);
        } catch (error) {
            this.hideLoading();
            this.setUiState('inspected');
            this.showSourceFeedback(error.message || '创建综合图表任务失败', 'danger');
            this.showError(error.message || '创建综合图表任务失败');
        }
    },

    stopTaskPolling() {
        if (this.taskPollTimer) {
            clearTimeout(this.taskPollTimer);
            this.taskPollTimer = null;
        }
    },

    async pollChartTaskStatus(taskId) {
        try {
            const response = await fetch(`/api/combined-analysis/task/${encodeURIComponent(taskId)}`);
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '读取综合图表任务状态失败');

            this.updateLoadingProgress(data.progress, data.stage, data.detail, data.history || []);

            if (data.status === 'completed') {
                this.stopTaskPolling();
                this.hideLoading();
                this.result = data.result || null;
                this.renderChartResult(this.result);
                await this.registerProjectResult(this.result);
                return;
            }

            if (data.status === 'failed') {
                this.stopTaskPolling();
                this.hideLoading();
                throw new Error(data.detail || data.error || '综合图表任务失败');
            }

            this.taskPollTimer = setTimeout(() => this.pollChartTaskStatus(taskId), 1500);
        } catch (error) {
            this.stopTaskPolling();
            this.hideLoading();
            this.setUiState('inspected');
            this.showSourceFeedback(error.message || '读取综合图表任务状态失败', 'danger');
            this.showError(error.message || '读取综合图表任务状态失败');
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

        if ((result.module || '') === 'charts' || result.selected_modules || result.modules) {
            this.renderChartResult(result);
            return;
        }

        const isBoxPlot = (result.module || '') === 'boxplot';
        const isPep = (result.module || '') === 'pep-analysis';
        const isTopClone = (result.module || '') === 'topclone';
        const isUmap = (result.module || '') === 'umap';
        const isVolcano = (result.module || '') === 'volcano';
        const isUmapin = (result.module || '') === 'umapin';
        this.setUiState('completed');

        if (isVolcano) {
            this.renderVolcanoResult(result);
            return;
        }
        if (isUmapin) {
            this.renderUmapinResult(result);
            return;
        }
        if (isBoxPlot) {
            this.renderBoxPlotResult(result);
            return;
        }
        if (isPep) {
            this.renderPepAnalysisResult(result);
            return;
        }

        if (isTopClone) {
            this.renderTopCloneResult(result);
            return;
        }
        if (isUmap) {
            this.renderUmapResult(result);
            return;
        }

        this.showSourceFeedback(`数据库比对完成，共 ${result.sample_count || 0} 个样本。`, 'success');
        document.getElementById('scriptHubResultSummary').textContent =
            `数据库比对完成，共 ${result.sample_count || 0} 个样本。`;
        document.getElementById('scriptHubResultMeta').textContent =
            `链：${(result.selected_chains || []).join(', ') || '-'} | Profile：${result.profile_path || '未合并'}`;
        document.getElementById('scriptHubResultLog').textContent =
            JSON.stringify(result.metadata || {}, null, 2);

        const context = this.projectContext || this.getProjectContext();
        const saveBtn = document.getElementById('scriptHubSaveDbResultBtn');
        if (saveBtn && context.projectId) {
            saveBtn.style.display = '';
            saveBtn.onclick = () => this.registerProjectResult(result);
        }

        window.setTimeout(() => {
            document.getElementById('scriptHubResultStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 80);
    },

    renderChartResult(result) {
        if (!result) return;
        this.setUiState('completed');
        this.result = result;
        const failedCount = Array.isArray(result.failed_modules) ? result.failed_modules.length : 0;
        const summary = result.summary || '综合图表结果已生成。';
        this.showSourceFeedback(summary, failedCount ? 'warning' : 'success');
        document.getElementById('scriptHubResultSummary').textContent = summary;
        document.getElementById('scriptHubResultMeta').textContent =
            `模块：${(result.selected_modules || []).join(', ') || '-'} | 失败：${(result.failed_modules || []).join(', ') || '无'}`;
        document.getElementById('scriptHubResultLog').textContent =
            JSON.stringify({
                job_id: result.job_id,
                output_base: result.output_base,
                selected_modules: result.selected_modules || [],
                failed_modules: result.failed_modules || [],
            }, null, 2);

        const container = document.getElementById('scriptHubChartResults');
        if (container) {
            const modules = result.modules || {};
            const order = (result.selected_modules && result.selected_modules.length)
                ? result.selected_modules
                : ['heatmap', 'treemap', 'chord'];
            container.innerHTML = order.map((key) => {
                const moduleInfo = modules[key] || {};
                const status = moduleInfo.status || 'failed';
                const label = moduleInfo.label || this.getChartModuleLabel(key);
                const message = moduleInfo.message || (
                    status === 'completed'
                        ? (moduleInfo.topclone_only ? '结果已生成，本次仅导出 TopClone CSV。' : '结果已生成，可打开查看器或下载 ZIP。')
                        : '该模块本次未成功生成。'
                );
                const warnings = Array.isArray(moduleInfo.warnings) ? moduleInfo.warnings.filter(Boolean) : [];
                const warningHtml = warnings.length
                    ? `<div class="small text-warning-emphasis mb-3">${this.escapeHtml(warnings.slice(0, 2).join('；'))}${warnings.length > 2 ? `；另有 ${warnings.length - 2} 条 warning` : ''}</div>`
                    : '';
                const buttons = [];
                if (moduleInfo.viewer_url) {
                    buttons.push(`<button class="btn btn-sm btn-primary" type="button" onclick="window.open('${this.escapeHtml(moduleInfo.viewer_url)}', '_blank', 'noopener')">打开查看器</button>`);
                }
                if (moduleInfo.zip_url) {
                    buttons.push(`<button class="btn btn-sm btn-outline-primary" type="button" onclick="window.open('${this.escapeHtml(moduleInfo.zip_url)}', '_blank', 'noopener')">下载 ZIP</button>`);
                }
                if (moduleInfo.metadata_url) {
                    buttons.push(`<button class="btn btn-sm btn-outline-secondary" type="button" onclick="window.open('${this.escapeHtml(moduleInfo.metadata_url)}', '_blank', 'noopener')">Metadata</button>`);
                }
                return `<div class="sh-chart-result-card ${status === 'completed' ? 'is-success' : 'is-failed'}">
                    <div class="d-flex justify-content-between align-items-center gap-2 mb-2">
                        <strong>${this.escapeHtml(label)}</strong>
                        <span class="small fw-semibold ${status === 'completed' ? 'text-success' : 'text-danger'}">${status === 'completed' ? '已生成' : '失败'}</span>
                    </div>
                    <div class="text-muted small mb-3">${this.escapeHtml(message)}</div>
                    ${warningHtml}
                    <div class="d-flex flex-wrap gap-2">${buttons.length ? buttons.join('') : '<span class="text-muted small">无可用输出</span>'}</div>
                </div>`;
            }).join('');
        }

        window.setTimeout(() => {
            document.getElementById('scriptHubResultStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 80);
    },

    getChartModuleLabel(key) {
        return {
            heatmap: 'Heatmap',
            treemap: 'Treemap',
            chord: 'Chord',
        }[key] || key;
    },

    renderUmapResult(result) {
        this.showSourceFeedback(`UMAP 分析完成。${result.png_urls?.length || 0} 张图。`, 'success');
        document.getElementById('scriptHubResultSummary').textContent =
            `UMAP 分析完成。生成了 ${result.png_urls?.length || 0} 张图。`;
        document.getElementById('scriptHubResultMeta').textContent =
            `n_neighbors: ${result.metadata?.n_neighbors || 6} | min_dist: ${result.metadata?.min_dist || 0.01}`;

        const zipBtn = document.getElementById('scriptHubOpenUmapZipBtn');
        if (zipBtn && result.zip_url) {
            zipBtn.style.display = '';
            zipBtn.onclick = () => {
                const a = document.createElement('a');
                a.href = result.zip_url;
                a.download = '';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            };
        }

        // Show first few UMAP images
        const imgDiv = document.getElementById('scriptHubUmapImages');
        if (imgDiv && result.png_urls) {
            const urls = result.png_urls.slice(0, 12);
            imgDiv.innerHTML = urls.map((url) => `
                <div class="sh-boxplot-img-card d-inline-block m-1">
                    <a href="${this.escapeHtml(url)}" target="_blank" rel="noopener">
                        <img src="${this.escapeHtml(url)}" alt="UMAP" class="sh-boxplot-thumb" loading="lazy" style="max-width:200px;">
                    </a>
                </div>
            `).join('');
        }

        window.setTimeout(() => {
            document.getElementById('scriptHubResultStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 80);
    },

    renderTopCloneResult(result) {
        const feedbackMsg = `TopClone 分析完成。${result.per_sample_count || 0} 个逐样本文件，${result.png_urls?.length || 0} 张箱线图。`;
        this.showSourceFeedback(feedbackMsg, 'success');
        document.getElementById('scriptHubResultSummary').textContent = feedbackMsg;
        document.getElementById('scriptHubResultMeta').textContent =
            `模式：${result.metadata?.mode || 'trace'} | 链：${(result.metadata?.chains || []).join(', ')}`;

        // Show topclone.csv download link
        const tcCsvDiv = document.getElementById('scriptHubTcTopcloneCsv');
        if (tcCsvDiv && result.topclone_csv_url) {
            tcCsvDiv.innerHTML = `<a href="${this.escapeHtml(result.topclone_csv_url)}" class="btn btn-sm btn-outline-primary" download>
                <i class="bi bi-download me-1"></i>topclone.csv</a>`;
        } else if (tcCsvDiv) {
            tcCsvDiv.innerHTML = '';
        }

        const perSampleDiv = document.getElementById('scriptHubTcPerSampleCount');
        if (perSampleDiv && result.per_sample_count > 0) {
            perSampleDiv.textContent = `${result.per_sample_count} per-sample file(s) generated.`;
        }

        // Also render boxplot results if any
        if (result.png_urls && result.png_urls.length > 0) {
            this.renderBoxPlotResult(result);
        }
    },

    renderBoxPlotResult(result) {
        const skipped = result.metadata?.skipped_insufficient_data || 0;
        let feedbackMsg = `箱线图分析完成。生成了 ${result.png_urls?.length || 0} 张图。`;
        if (skipped > 0) {
            feedbackMsg += ` ${skipped} 组比较被跳过（组内需 ≥2 个数据点）。`;
        }
        const tone = skipped > 0 ? 'warning' : 'success';
        this.showSourceFeedback(feedbackMsg, tone);
        document.getElementById('scriptHubResultSummary').textContent = feedbackMsg;
        document.getElementById('scriptHubResultMeta').textContent =
            `P值阈值：${result.metadata?.pvalue_threshold || 0.05} | 参数范围：${result.metadata?.param_begin || '-'} → ${result.metadata?.param_over || '-'}`;
        document.getElementById('scriptHubResultLog').textContent =
            JSON.stringify(result.metadata || {}, null, 2);

        // Build two-level map: groupType -> paramName -> url
        this._bpGroupedMap = {};
        this._bpPngMap = {};
        const pngUrls = Array.isArray(result.png_urls) ? result.png_urls : [];
        pngUrls.forEach((url) => {
            const cleanUrl = url.replace(/\/+$/, '');
            const parts = cleanUrl.split('/');
            const filename = parts.pop() || '';
            const paramName = filename.replace(/\.png$/i, '');
            const groupType = parts.pop() || 'ungrouped';
            if (!this._bpGroupedMap[groupType]) {
                this._bpGroupedMap[groupType] = {};
            }
            this._bpGroupedMap[groupType][paramName] = url;
            this._bpPngMap[paramName] = url;
        });

        // Populate group type dropdown
        const groupTypes = Object.keys(this._bpGroupedMap).sort();
        const groupSelect = document.getElementById('scriptHubBoxPlotGroupSelect');
        if (groupSelect) {
            groupSelect.innerHTML = [
                '<option value="">-- Select a group type --</option>',
                ...groupTypes.map((g) => `<option value="${this.escapeHtml(g)}">${this.escapeHtml(g)}</option>`),
            ].join('');
        }

        // Reset parameter dropdown (fills when group type selected)
        const paramSelect = document.getElementById('scriptHubBoxPlotParamSelect');
        if (paramSelect) {
            paramSelect.innerHTML = '<option value="">-- Select a parameter --</option>';
        }
        document.getElementById('scriptHubBoxPlotSingleImage').innerHTML =
            '<p class="text-muted small">Select a group type above, then a parameter to view its boxplot.</p>';

        // Show ZIP download button
        const zipBtn = document.getElementById('scriptHubOpenBpZipBtn');
        if (zipBtn && result.zip_url) {
            zipBtn.style.display = '';
            zipBtn.onclick = () => {
                const a = document.createElement('a');
                a.href = result.zip_url;
                a.download = '';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            };
        } else if (zipBtn) {
            zipBtn.style.display = 'none';
        }

        window.setTimeout(() => {
            document.getElementById('scriptHubResultStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 80);
    },

    async inspectUmap(loadingText = 'Scanning datapoint...') {
        const filePath = document.getElementById('scriptHubDatapointPath')?.value?.trim()
            || this.selectedDatapointPath
            || '';
        if (!filePath) {
            this.showSourceFeedback('Please provide a datapoint path.', 'warning');
            this.showError('Please provide a datapoint path');
            return;
        }
        this.setUiState('inspecting');
        this.showSourceFeedback('Inspecting UMAP datapoint...', 'secondary');
        this.showLoading(loadingText || 'Scanning datapoint...', 'Inspect UMAP');
        try {
            const body = { datapoint_path: filePath };
            const response = await fetch('/api/script-hub/umap/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || 'Failed to inspect UMAP inputs');
            this.inspectData = data;
            this.result = null;
            this.setUiState('inspected');

            document.getElementById('scriptHubColumnCount').textContent = data.column_count || 0;
            const columns = Array.isArray(data.columns) ? data.columns : [];
            document.getElementById('scriptHubColumnChips').innerHTML = columns.length
                ? columns.map((col) => `<span class="sh-chip">${this.escapeHtml(col)}</span>`).join('')
                : '<span class="sh-chip">No columns detected</span>';

            const paramBegin = document.getElementById('scriptHubParamBegin');
            const paramOver = document.getElementById('scriptHubParamOver');
            [paramBegin, paramOver].forEach((select) => {
                if (select) select.innerHTML = columns.map((col) => `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`).join('');
            });
            if (paramBegin && columns.length) paramBegin.value = data.suggested_param_begin || columns[0];
            if (paramOver && columns.length) paramOver.value = data.suggested_param_over || (columns.length > 1 ? columns[columns.length - 1] : columns[0]);

            this.showSourceFeedback(`UMAP inspection completed. ${data.column_count} columns detected.`, 'success');
            this.setInspectSummary(`Datapoint: ${filePath} — ${data.column_count} columns`, 'success');
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.showError(error.message || 'UMAP inspection failed');
        } finally {
            this.hideLoading();
        }
    },

    // ---- Volcano ----

    async inspectVolcano(explicitBasePath = '', loadingText = '扫描 VJ usage 数据...') {
        const basePath = explicitBasePath || document.getElementById('scriptHubBasePath')?.value?.trim() || '';
        if (!basePath) {
            this.showSourceFeedback('请先提供基础目录。', 'warning');
            this.showError('请先提供基础目录');
            return;
        }

        this.setUiState('inspecting');
        this.showSourceFeedback('正在检测 VJ usage 数据...', 'secondary');
        this.showLoading(loadingText || '扫描 VJ usage 数据...', '检测火山图数据');
        try {
            const body = { base_path: basePath };
            const response = await fetch('/api/script-hub/volcano/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '检测失败');

            this.inspectData = data;
            this.result = null;
            this.lastInspectedBasePath = basePath;
            this.setUiState('inspected');
            document.getElementById('scriptHubVolcanoDataDir').value = data.data_dir || '';

            const summaryGrid = document.getElementById('scriptHubSummaryGrid');
            if (summaryGrid) {
                summaryGrid.innerHTML = `
                    <div class="sh-metric">
                        <span class="sh-metric-label">数据目录</span>
                        <div class="sh-metric-value sh-path-block">${this.escapeHtml(data.data_dir || '-')}</div>
                    </div>
                    <div class="sh-metric">
                        <span class="sh-metric-label">文件数</span>
                        <div class="sh-metric-value">${this.escapeHtml(String(data.file_count || 0))}</div>
                    </div>
                `;
            }
            this.showSourceFeedback(`火山图检测完成。发现 ${data.file_count || 0} 个 CSV 文件。`, 'success');
            this.setInspectSummary(`数据目录：${data.data_dir} — ${data.file_count} 个文件`, 'success');
            this._registerPathToProject('datapoint', data.data_dir);
            document.getElementById('scriptHubResultLog').textContent = '等待结果。';
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.showError(error.message || '检测失败');
        } finally {
            this.hideLoading();
        }
    },

    renderVolcanoResult(result) {
        this.showSourceFeedback(`火山图分析完成，生成 ${result.png_urls?.length || 0} 张图。`, 'success');
        document.getElementById('scriptHubResultSummary').textContent = `火山图分析完成。${result.png_urls?.length || 0} 张图。`;
        document.getElementById('scriptHubResultMeta').textContent = `数据文件数：${result.metadata?.file_count || 0}`;

        const gallery = document.getElementById('scriptHubVolcanoGallery');
        const csvLinks = document.getElementById('scriptHubVolcanoCsvLinks');
        if (gallery && result.png_urls) {
            gallery.innerHTML = result.png_urls.map((url, i) => `
                <div class="col-md-6 mb-2">
                    <div class="sh-boxplot-img-card">
                        <a href="${this.escapeHtml(url)}" target="_blank" rel="noopener">
                            <img src="${this.escapeHtml(url)}" class="sh-boxplot-thumb" loading="lazy" style="max-height:350px">
                        </a>
                    </div>
                </div>
            `).join('');
        }
        if (csvLinks && result.csv_urls) {
            csvLinks.innerHTML = result.csv_urls.map((url) => `
                <a href="${this.escapeHtml(url)}" class="btn btn-sm btn-outline-secondary" target="_blank" download>
                    ${this.escapeHtml(url.split('/').pop())}
                </a>
            `).join('');
        }
        window.setTimeout(() => {
            document.getElementById('scriptHubResultStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 80);
    },

    // ---- UMAPin ----

    async inspectUmapin(explicitBasePath = '', loadingText = '扫描数据文件...') {
        const basePath = explicitBasePath || document.getElementById('scriptHubBasePath')?.value?.trim() || '';
        if (!basePath) {
            this.showSourceFeedback('请先提供基础目录或数据文件路径。', 'warning');
            this.showError('请先提供基础目录或数据文件路径');
            return;
        }

        this.setUiState('inspecting');
        this.showSourceFeedback('正在检测数据文件...', 'secondary');
        this.showLoading(loadingText || '扫描数据文件...', '检测 UMAPin 数据');
        try {
            const body = { base_path: basePath };
            const response = await fetch('/api/script-hub/umapin/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '检测失败');

            this.inspectData = data;
            this.result = null;
            this.lastInspectedBasePath = basePath;
            this.setUiState('inspected');

            document.getElementById('scriptHubUmapinDataPath').value = data.data_path || '';
            document.getElementById('scriptHubUmapinCategoryCol').value = data.category_col || 'Category';

            const columns = Array.isArray(data.columns) ? data.columns : [];
            const paramBegin = document.getElementById('scriptHubParamBegin');
            const paramOver = document.getElementById('scriptHubParamOver');
            [paramBegin, paramOver].forEach((select) => {
                if (select) select.innerHTML = columns.map((col) =>
                    `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`
                ).join('');
            });
            if (paramBegin && columns.length) paramBegin.value = data.suggested_param_begin || columns[0];
            if (paramOver && columns.length) paramOver.value = data.suggested_param_over || (columns.length > 1 ? columns[columns.length - 1] : columns[0]);

            document.getElementById('scriptHubColumnCount').textContent = data.column_count || 0;
            document.getElementById('scriptHubColumnChips').innerHTML = columns.length
                ? columns.map((col) => `<span class="sh-chip">${this.escapeHtml(col)}</span>`).join('')
                : '<span class="sh-chip">无列数据</span>';

            const summaryGrid = document.getElementById('scriptHubSummaryGrid');
            if (summaryGrid) {
                summaryGrid.innerHTML = `
                    <div class="sh-metric">
                        <span class="sh-metric-label">数据文件</span>
                        <div class="sh-metric-value sh-path-block">${this.escapeHtml((data.data_path || '').split('/').pop() || '-')}</div>
                    </div>
                    <div class="sh-metric">
                        <span class="sh-metric-label">列数</span>
                        <div class="sh-metric-value">${this.escapeHtml(String(data.column_count || 0))}</div>
                    </div>
                    <div class="sh-metric">
                        <span class="sh-metric-label">分类列</span>
                        <div class="sh-metric-value">${this.escapeHtml(data.category_col || '-')}</div>
                    </div>
                `;
            }
            this.showSourceFeedback(`UMAPin 检测完成。${data.column_count || 0} 列。`, 'success');
            this.setInspectSummary(`数据文件：${data.data_path} — ${data.column_count} 列`, 'success');
            this._registerPathToProject('datapoint', data.data_path);
            document.getElementById('scriptHubResultLog').textContent = '等待结果。';
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.showError(error.message || '检测失败');
        } finally {
            this.hideLoading();
        }
    },

    renderUmapinResult(result) {
        this.showSourceFeedback(`UMAPin 降维完成。`, 'success');
        document.getElementById('scriptHubResultSummary').textContent = `UMAPin 降维完成。${result.png_urls?.length || 0} 张图。`;
        document.getElementById('scriptHubResultMeta').textContent = `特征数：${result.metadata?.feature_count || 0} | 分组：${(result.metadata?.unique_groups || []).join(', ')}`;

        const imagesDiv = document.getElementById('scriptHubUmapinImages');
        if (imagesDiv && result.png_urls) {
            imagesDiv.innerHTML = result.png_urls.map((url) => `
                <div class="col-md-6 mb-2">
                    <div class="sh-boxplot-img-card">
                        <a href="${this.escapeHtml(url)}" target="_blank" rel="noopener">
                            <img src="${this.escapeHtml(url)}" class="sh-boxplot-thumb" loading="lazy">
                        </a>
                    </div>
                </div>
            `).join('');
        }
        const csvLinks = document.getElementById('scriptHubUmapinCsvLinks');
        if (csvLinks && result.csv_urls) {
            csvLinks.innerHTML = result.csv_urls.map((url) => `
                <a href="${this.escapeHtml(url)}" class="btn btn-sm btn-outline-secondary" target="_blank" download>
                    ${this.escapeHtml(url.split('/').pop())}
                </a>
            `).join('');
        }
        window.setTimeout(() => {
            document.getElementById('scriptHubResultStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 80);
    },

    async inspectPepAnalysis(explicitBasePath = '', loadingText = 'Scanning for pep files...') {
        const basePath = explicitBasePath
            || (this.selectedPepPaths.length ? this.selectedPepPaths[0] : '')
            || document.getElementById('scriptHubBasePath')?.value?.trim() || '';

        if (!basePath) {
            this.showSourceFeedback('请先提供 PEP 目录路径。', 'warning');
            this.showError('请先提供 PEP 目录路径');
            return;
        }

        this.setUiState('inspecting');
        this.showSourceFeedback('Inspecting for pep files...', 'secondary');
        this.showLoading(loadingText || 'Scanning for pep files...', 'Inspect CDR3 Sharing assets');
        try {
            const body = {
                base_path: basePath,
                pep_paths: this.selectedPepPaths,
                profile_path: this.selectedDatapointPath || null,
            };
            const response = await fetch('/api/script-hub/pep-analysis/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.message || 'Failed to inspect Pep analysis assets');
            }

            this.inspectData = data;
            this.result = null;
            this.lastInspectedBasePath = basePath;
            this.setUiState('inspected');

            document.getElementById('scriptHubPepDataDir').value = data.base_path || '';

            // Render chain chips
            const chains = Array.isArray(data.chains) ? data.chains : [];
            this._pepAvailableChains = chains;
            this._pepSelectedChains = [...chains];
            const chainContainer = document.getElementById('scriptHubPepChains');
            if (chainContainer) {
                chainContainer.innerHTML = chains.map((ch) => {
                    return `<span class="sh-chip sh-chip-chain" data-chain="${this.escapeHtml(ch)}" style="cursor:pointer;background:var(--bs-primary-bg-subtle,#cfe2ff);border-color:var(--bs-primary,#0d6efd);">${this.escapeHtml(ch)}</span>`;
                }).join('');
                chainContainer.querySelectorAll('.sh-chip-chain').forEach((chip) => {
                    chip.addEventListener('click', () => this._togglePepChain(chip));
                });
            }

            // Profile candidates
            const profileSelect = document.getElementById('scriptHubPepProfilePath');
            const selectedProfile = this.selectedDatapointPath || '';
            const profileCandidates = [...new Set([
                ...(selectedProfile ? [selectedProfile] : []),
                ...(Array.isArray(data.profile_candidates) ? data.profile_candidates : []),
            ])];
            if (profileSelect) {
                profileSelect.innerHTML = '<option value="">-- Select a Profile CSV --</option>' +
                    profileCandidates.map((p) => {
                        const parts = p.replace(/\\/g, '/').split('/');
                        const basename = parts[parts.length - 1] || p;
                        return `<option value="${this.escapeHtml(p)}">${this.escapeHtml(basename)}</option>`;
                    }).join('');
                if (profileCandidates.length > 0) {
                    profileSelect.value = selectedProfile || profileCandidates[0];
                }
            }

            // Profile columns as group field options
            const profileColumns = Array.isArray(data.profile_columns) ? data.profile_columns : [];
            const groupFieldsSelect = document.getElementById('scriptHubPepGroupFields');
            if (groupFieldsSelect) {
                groupFieldsSelect.innerHTML = profileColumns
                    .filter(c => c.toLowerCase() !== 'sample')
                    .map((col) => `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`)
                    .join('');
            }

            // Summary
            const summaryGrid = document.getElementById('scriptHubSummaryGrid');
            if (summaryGrid) {
                summaryGrid.innerHTML = `
                    <div class="sh-metric">
                        <span class="sh-metric-label">Samples</span>
                        <div class="sh-metric-value">${this.escapeHtml(String(data.sample_count || 0))}</div>
                    </div>
                    <div class="sh-metric">
                        <span class="sh-metric-label">Chains</span>
                        <div class="sh-metric-value">${this.escapeHtml(chains.join(', ') || '-')}</div>
                    </div>
                    <div class="sh-metric">
                        <span class="sh-metric-label">Pep Files</span>
                        <div class="sh-metric-value">${this.escapeHtml(String(data.pep_file_count || 0))}</div>
                    </div>
                    <div class="sh-metric">
                        <span class="sh-metric-label">Profile</span>
                        <div class="sh-metric-value">${this.escapeHtml((profileCandidates[0] || '').split('/').pop() || 'Auto not found')}</div>
                    </div>
                `;
            }

            document.getElementById('scriptHubColumnChips').innerHTML = chains.map((ch) =>
                `<span class="sh-chip">${this.escapeHtml(ch)}</span>`
            ).join('');
            document.getElementById('scriptHubColumnCount').textContent = data.pep_file_count || 0;

            this.showSourceFeedback(
                `CDR3 共享检测完成。检测到 ${data.sample_count || 0} 个样本，${chains.length} 条链，${data.pep_file_count || 0} 个 pep 文件。`,
                'success'
            );
            this.setInspectSummary(`${data.sample_count} 样本 — ${chains.length} 链 — ${data.pep_file_count} 文件`, 'success');
            this._registerPathToProject('pep', data.base_path);

            document.getElementById('scriptHubResultLog').textContent = 'Waiting for results.';
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.setInspectSummary(error.message || 'Pep analysis inspection failed', 'danger');
            this.showSourceFeedback(error.message || 'Pep analysis inspection failed.', 'danger');
            this.showError(error.message || 'Pep analysis inspection failed');
        } finally {
            this.hideLoading();
        }
    },

    _togglePepChain(chip) {
        const chain = chip.getAttribute('data-chain');
        if (!chain) return;
        if (this._pepSelectedChains.includes(chain)) {
            this._pepSelectedChains = this._pepSelectedChains.filter(c => c !== chain);
            chip.style.background = '';
            chip.style.borderColor = '';
        } else {
            this._pepSelectedChains.push(chain);
            chip.style.background = 'var(--bs-primary-bg-subtle, #cfe2ff)';
            chip.style.borderColor = 'var(--bs-primary, #0d6efd)';
        }
    },

    async onPepProfileChange() {
        const profilePath = document.getElementById('scriptHubPepProfilePath')?.value || '';
        if (!profilePath) return;
        try {
            const response = await fetch('/api/script-hub/boxplot/columns', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: profilePath }),
            });
            const data = await response.json();
            if (data.success) {
                const columns = Array.isArray(data.columns) ? data.columns : [];
                const groupFieldsSelect = document.getElementById('scriptHubPepGroupFields');
                if (groupFieldsSelect) {
                    groupFieldsSelect.innerHTML = columns
                        .filter(c => c.toLowerCase() !== 'sample')
                        .map((col) => `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`)
                        .join('');
                }
            }
        } catch (error) {
            console.warn('onPepProfileChange failed:', error);
        }
    },

    renderPepAnalysisResult(result) {
        const chains = result.metadata?.selected_chains || [];
        const groupFields = result.metadata?.group_fields || [];
        const feedbackMsg = `CDR3 共享分析完成。${chains.length} 条链，${groupFields.length} 个分组字段。`;
        this.showSourceFeedback(feedbackMsg, 'success');
        document.getElementById('scriptHubResultSummary').textContent = feedbackMsg;
        document.getElementById('scriptHubResultMeta').textContent =
            `链：${chains.join(', ')} | 分组：${groupFields.join(', ')} | P值阈值：${result.metadata?.pvalue_threshold || 0.05}`;
        document.getElementById('scriptHubResultLog').textContent =
            JSON.stringify(result.metadata || {}, null, 2);

        const context = this.projectContext || this.getProjectContext();
        const saveBtn = document.getElementById('scriptHubSaveToProjectBtn');
        if (saveBtn && context.projectId) {
            saveBtn.style.display = '';
            saveBtn.onclick = () => this.registerProjectResult(result);
        }

        this._pepResult = result;

        // Populate group field dropdown
        const groupSelect = document.getElementById('scriptHubPepGroupSelect');
        if (groupSelect) {
            groupSelect.innerHTML = '<option value="">-- Select a group field --</option>' +
                groupFields.map(g => `<option value="${this.escapeHtml(g)}">${this.escapeHtml(g)}</option>`).join('');
        }

        // Populate chain dropdown
        const chainSelect = document.getElementById('scriptHubPepChainSelect');
        if (chainSelect) {
            chainSelect.innerHTML = '<option value="">-- Select a chain --</option>' +
                chains.map(c => `<option value="${this.escapeHtml(c)}">${this.escapeHtml(c)}</option>`).join('');
        }

        document.getElementById('scriptHubPepResultLinks').innerHTML = '';
        document.getElementById('scriptHubPepResultImage').innerHTML =
            '<p class="text-muted small">Select group field, chain and result type to view.</p>';

        window.setTimeout(() => {
            document.getElementById('scriptHubResultStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 80);
    },

    onPepGroupSelectChange(groupField) {
        this._pepActiveGroup = groupField;
        this._refreshPepResultView();
    },

    onPepChainSelectChange(chain) {
        this._pepActiveChain = chain;
        this._refreshPepResultView();
    },

    onPepResultTypeChange(resultType) {
        this._pepActiveResultType = resultType;
        this._refreshPepResultView();
    },

    _refreshPepResultView() {
        const groupField = this._pepActiveGroup || document.getElementById('scriptHubPepGroupSelect')?.value;
        const chain = this._pepActiveChain || document.getElementById('scriptHubPepChainSelect')?.value;
        const resultType = this._pepActiveResultType || document.getElementById('scriptHubPepResultType')?.value;
        const result = this._pepResult;
        if (!result) return;

        const linksContainer = document.getElementById('scriptHubPepResultLinks');
        const imageContainer = document.getElementById('scriptHubPepResultImage');
        if (!linksContainer || !imageContainer) return;

        if (!resultType) {
            linksContainer.innerHTML = '';
            imageContainer.innerHTML = '<p class="text-muted small">Select a result type above.</p>';
            return;
        }

        const hasGroup = groupField && groupField !== '';
        const hasChain = chain && chain !== '';

        if (resultType === 'shared') {
            const urls = (Array.isArray(result.shared_matrix_urls) ? result.shared_matrix_urls : [])
                .filter(u => !hasChain || u.includes(`/${chain}.csv`));
            this._renderPepDownloadLinks(linksContainer, urls);
            imageContainer.innerHTML = '';
        } else if (resultType === 'usage') {
            const urls = (Array.isArray(result.usage_urls) ? result.usage_urls : [])
                .filter(u => !hasChain || u.includes(`/${chain}.csv`));
            this._renderPepDownloadLinks(linksContainer, urls);
            imageContainer.innerHTML = '';
        } else if (resultType === 'heatmap') {
            const imgUrls = (Array.isArray(result.heatmap_image_urls) ? result.heatmap_image_urls : [])
                .filter(u => (!hasGroup || u.includes(`/${groupField}/`)) && (!hasChain || u.includes(`/${chain}/`)));
            const csvUrls = (Array.isArray(result.heatmap_csv_urls) ? result.heatmap_csv_urls : [])
                .filter(u => (!hasGroup || u.includes(`/${groupField}/`)) && (!hasChain || u.includes(`/${chain}/`)));
            this._renderPepDownloadLinks(linksContainer, csvUrls);
            if (imgUrls.length > 0 && hasChain) {
                imageContainer.innerHTML = imgUrls.map(u =>
                    `<div class="sh-boxplot-img-card mb-2"><a href="${this.escapeHtml(u)}" target="_blank" rel="noopener"><img src="${this.escapeHtml(u)}" class="sh-boxplot-thumb" loading="lazy" style="max-height:400px"></a><div class="small text-muted mt-1">${this.escapeHtml(u.split('/').pop() || '')}</div></div>`
                ).join('');
            } else {
                imageContainer.innerHTML = '<p class="text-muted small">Select a chain to view heatmap images.</p>';
            }
        } else if (resultType === 'classification') {
            const urls = (Array.isArray(result.classification_urls) ? result.classification_urls : [])
                .filter(u => (!hasGroup || u.includes(`/${groupField}/`)) && (!hasChain || u.includes(`/${chain}.csv`)));
            const propUrls = (Array.isArray(result.proportion_urls) ? result.proportion_urls : [])
                .filter(u => (!hasGroup || u.includes(`/${groupField}/`)) && (!hasChain || u.includes(`/${chain}.csv`)));
            this._renderPepDownloadLinks(linksContainer, urls.concat(propUrls));
            imageContainer.innerHTML = '';
        } else if (resultType === 'arrange') {
            const urls = (Array.isArray(result.arrange_heatmap_urls) ? result.arrange_heatmap_urls : [])
                .filter(u => (!hasGroup || u.includes(`/${groupField}/`)) && (!hasChain || u.includes(`/${chain}.png`)));
            if (urls.length > 0 && hasChain) {
                imageContainer.innerHTML = urls.map(u =>
                    `<div class="sh-boxplot-img-card mb-2"><a href="${this.escapeHtml(u)}" target="_blank" rel="noopener"><img src="${this.escapeHtml(u)}" class="sh-boxplot-thumb" loading="lazy"></a><div class="small text-muted mt-1">${this.escapeHtml(u.split('/').pop() || '')}</div></div>`
                ).join('');
                linksContainer.innerHTML = '';
            } else {
                linksContainer.innerHTML = '';
                imageContainer.innerHTML = '<p class="text-muted small">Select a chain to view arrange heatmap.</p>';
            }
        }
    },

    _renderPepDownloadLinks(container, urls) {
        if (!container) return;
        container.innerHTML = urls.length
            ? urls.map((url) => `
                <a href="${this.escapeHtml(url)}" class="btn btn-sm btn-outline-secondary" target="_blank" rel="noopener" download>
                    <i class="bi bi-download me-1"></i>${this.escapeHtml(url.split('/').pop() || 'file')}
                </a>
            `).join('')
            : '<span class="text-muted small">No files available.</span>';
    },

    showBoxPlotImage(paramName) {
        const container = document.getElementById('scriptHubBoxPlotSingleImage');
        if (!container) return;
        if (!paramName) {
            container.innerHTML = '<p class="text-muted small">Select a parameter above to view its boxplot.</p>';
            return;
        }
        const groupType = document.getElementById('scriptHubBoxPlotGroupSelect')?.value;
        let url = null;
        if (groupType && this._bpGroupedMap && this._bpGroupedMap[groupType]) {
            url = this._bpGroupedMap[groupType][paramName];
        }
        if (!url) {
            url = this._bpPngMap?.[paramName];
        }
        if (!url) {
            container.innerHTML = '<p class="text-muted small">No image available for this selection.</p>';
            return;
        }
        container.innerHTML = `
            <div class="sh-boxplot-img-card">
                <a href="${this.escapeHtml(url)}" target="_blank" rel="noopener">
                    <img src="${this.escapeHtml(url)}" alt="${this.escapeHtml(paramName)}" class="sh-boxplot-thumb" loading="lazy">
                </a>
                <div class="small text-muted mt-1 sh-path-block">${this.escapeHtml(paramName)}</div>
            </div>`;
    },

    onGroupTypeChange(groupType) {
        const paramSelect = document.getElementById('scriptHubBoxPlotParamSelect');
        if (!paramSelect) return;

        if (!groupType || !this._bpGroupedMap || !this._bpGroupedMap[groupType]) {
            paramSelect.innerHTML = '<option value="">-- Select a parameter --</option>';
            document.getElementById('scriptHubBoxPlotSingleImage').innerHTML =
                '<p class="text-muted small">Select a group type above first.</p>';
            return;
        }

        const paramNames = Object.keys(this._bpGroupedMap[groupType]).sort();
        paramSelect.innerHTML = [
            '<option value="">-- Select a parameter --</option>',
            ...paramNames.map((n) => `<option value="${this.escapeHtml(n)}">${this.escapeHtml(n)}</option>`),
        ].join('');

        document.getElementById('scriptHubBoxPlotSingleImage').innerHTML =
            '<p class="text-muted small">Select a parameter above to view its boxplot.</p>';
    },

    openResultUrl(key) {
        const targetUrl = this.result?.[key];
        if (!targetUrl) {
            this.showError('No result file is available for this action');
            return;
        }
        window.open(targetUrl, '_blank', 'noopener');
    },

    // ---- Quick project creation ----

    showCreateProjectModal() {
        const modalEl = document.getElementById('scriptHubCreateProjectModal');
        if (!modalEl) return;
        const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
        const nameInput = document.getElementById('scriptHubNewProjectName');
        const errorEl = document.getElementById('scriptHubCreateProjectError');
        if (nameInput) nameInput.value = '';
        if (errorEl) errorEl.classList.add('d-none');
        modal.show();
    },

    async createProject() {
        const nameInput = document.getElementById('scriptHubNewProjectName');
        const errorEl = document.getElementById('scriptHubCreateProjectError');
        const submitBtn = document.getElementById('scriptHubSubmitCreateProjectBtn');
        const name = (nameInput?.value || '').trim();

        if (!name) {
            if (errorEl) {
                errorEl.textContent = '项目名称不能为空';
                errorEl.classList.remove('d-none');
            }
            return;
        }

        if (submitBtn) submitBtn.disabled = true;
        try {
            const response = await fetch('/api/projects', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name }),
            });
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.message || '创建项目失败');
            }
            const modalEl = document.getElementById('scriptHubCreateProjectModal');
            if (modalEl) bootstrap.Modal.getInstance(modalEl)?.hide();
            await this.loadProjects();
            const select = document.getElementById('scriptHubProjectSelect');
            if (select && data.id) {
                select.value = data.id;
                await this.onProjectChange(data.id);
            }
        } catch (error) {
            if (errorEl) {
                errorEl.textContent = error.message || '创建项目失败';
                errorEl.classList.remove('d-none');
            }
        } finally {
            if (submitBtn) submitBtn.disabled = false;
        }
    },

    // ---- Auto-register working paths to selected project ----

    async _registerPathToProject(assetType, storagePath, extraMeta = null) {
        const projectId = document.getElementById('scriptHubProjectSelect')?.value || '';
        if (!projectId || !storagePath) return;
        try {
            const body = {
                asset_type: assetType,
                storage_path: storagePath,
                original_name: this.getPathName(storagePath) || storagePath,
            };
            if (extraMeta && Object.keys(extraMeta).length) {
                body.metadata_json = extraMeta;
            }
            await fetch(`/api/projects/${encodeURIComponent(projectId)}/assets/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
        } catch (error) {
            console.warn('Failed to register path to project:', error);
        }
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
window.ScriptHubPage = ScriptHubPage;
