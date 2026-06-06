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
        profileSheet: null,
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
    mlUsageFeatureCandidates: [],

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
        'scriptHubPgenProfilePath',
        'scriptHubPgenSampleCol',
        'scriptHubPgenSpecies',
        'scriptHubMlMode',
        'scriptHubMlProfilePath',
        'scriptHubMlUsagePath',
        'scriptHubMlSampleCol',
        'scriptHubMlLabelCol',
        'scriptHubMlFilterCol',
        'scriptHubMlFilterValue',
        'scriptHubMlParamBegin',
        'scriptHubMlParamOver',
        'scriptHubMlThreshold',
        'scriptHubMlCvSplits',
        'scriptHubMlRocCvSplits',
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
        document.getElementById('scriptHubInspectBtn')?.addEventListener('click', () => this.inspectBasePath());
        document.getElementById('scriptHubDatapointPath')?.addEventListener('change', () => {
            if (this.activeModule === 'profile') this.onProfileFileChange();
            if (this.activeModule === 'boxplot') this.onDatapointFileChange();
        });
        document.getElementById('scriptHubBpDatapointPath')?.addEventListener('change', (event) => {
            const hidden = document.getElementById('scriptHubDatapointPath');
            if (hidden) hidden.value = event.target.value || '';
            if (this.activeModule === 'profile') this.onProfileFileChange();
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
        document.getElementById('scriptHubProfileGroupFields')?.addEventListener('change', () => {
            this._selectedGroupFields = this._getSelectedGroupFields();
            this.detectGroupValuesForAll();
        });
        document.getElementById('scriptHubPepProfilePath')?.addEventListener('change', () => {
            this.onPepProfileChange();
        });
        document.getElementById('scriptHubPepGroupSelect')?.addEventListener('change', (event) => {
            this.onPepGroupSelectChange(event.target.value);
        });
        document.getElementById('scriptHubPepGroupFieldList')?.addEventListener('click', (event) => {
            const fieldBtn = event.target.closest('[data-pep-group-field]');
            if (fieldBtn) this.togglePepGroupField(fieldBtn.dataset.pepGroupField || '');
        });
        document.getElementById('scriptHubPgenChains')?.addEventListener('click', (event) => {
            const chip = event.target.closest('[data-pgen-chain]');
            if (!chip || chip.classList.contains('is-disabled')) return;
            chip.classList.toggle('sh-chip-selected');
            this._pgenSelectedChains = this._getSelectedPgenChains();
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
        document.getElementById('scriptHubRefreshCachedUsageBtn')?.addEventListener('click', () => this.fetchAndRenderCachedUsageConfig());
        document.getElementById('scriptHubMlMode')?.addEventListener('change', () => {
            this.syncModuleUI();
            this.syncMlFeatureMode();
            if (this.activeModule === 'ml-analysis') this.fetchAndRenderCachedUsageConfig();
        });
        this.bindPepPipelineEvents();

        this.CONFIG_FIELD_IDS.forEach((fieldId) => {
            const element = document.getElementById(fieldId);
            if (!element) return;
            const eventName = element.tagName === 'SELECT' || element.type === 'checkbox' ? 'change' : 'input';
            element.addEventListener(eventName, () => this.markFieldTouched(fieldId));
        });
    },

    bindPepPipelineEvents() {
        document.getElementById('scriptHubPepSelectAllOptional')?.addEventListener('click', () => {
            ['scriptHubPepStep5', 'scriptHubPepStep6', 'scriptHubPepStep7', 'scriptHubPepStep8'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.checked = true;
            });
            this.updatePepPipelineCards();
        });
        document.getElementById('scriptHubPepClearOptional')?.addEventListener('click', () => {
            ['scriptHubPepStep5', 'scriptHubPepStep6', 'scriptHubPepStep7', 'scriptHubPepStep8'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.checked = false;
            });
            this.updatePepPipelineCards();
        });
        ['scriptHubPepStep5', 'scriptHubPepStep6', 'scriptHubPepStep7', 'scriptHubPepStep8'].forEach(id => {
            document.getElementById(id)?.addEventListener('change', () => this.updatePepPipelineCards());
        });
        this.updatePepPipelineCards();
    },

    updatePepPipelineCards() {
        document.querySelectorAll('.sh-pipeline-step-optional').forEach(step => {
            const stepNum = step.dataset.pipelineStep;
            const checkbox = document.getElementById('scriptHubPepStep' + stepNum);
            step.classList.toggle('is-deselected', checkbox ? !checkbox.checked : false);
        });
    },

    getSelectedPepOptionalSteps() {
        return [5, 6, 7, 8].filter(n => {
            const el = document.getElementById('scriptHubPepStep' + n);
            return el ? el.checked : true;
        });
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

            const pepAssets = this.projectAssets.filter(a => a.asset_type === 'pep');
            const profileAssets = this.getProjectProfileAssets(this.projectAssets);
            const basePathInput = document.getElementById('scriptHubBasePath');
            const localPepAssets = pepAssets.filter(a => !(a.metadata || {}).remote_source_id);
            const projectPepPaths = [...new Set(pepAssets.map(a => a.storage_path).filter(Boolean))];

            if (localPepAssets.length > 0) {
                const pepDir = localPepAssets[0].storage_path;
                if (basePathInput) basePathInput.value = pepDir;
            } else if (basePathInput) {
                basePathInput.value = '';
            }

            if (profileAssets.length > 0) {
                const dpPath = profileAssets[0].storage_path;
                const dpInput = document.getElementById('scriptHubDatapointPath');
                if (dpInput) dpInput.value = dpPath;
            }

            this.selectedPepPaths = projectPepPaths;
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
            if (profileAssets.length > 0) {
                const dpPath = profileAssets[0].storage_path;
                this.dataSelection.profilePath = dpPath;
                this.dataSelection.profileType = 'file';
                this.selectedDatapointPaths = [dpPath];
                this.selectedDatapointPath = dpPath;
            } else {
                this.dataSelection.profilePath = '';
                this.dataSelection.profileType = '';
                this.selectedDatapointPaths = [];
                this.selectedDatapointPath = '';
            }
            this.syncDataSelectionState();

            this.stageUnlocked.data = true;
            this.evaluateAvailableModules(this.selectedPepPaths, this.selectedDatapointPaths);
            this.stageUnlocked.module = this.selectedPepPaths.length > 0 || this.selectedDatapointPaths.length > 0;
            this.syncStageUI();
            this.renderModuleChips();
            this.renderDataSummary(this.selectedPepPaths, this.selectedDatapointPaths);
            if (this.stageUnlocked.module) {
                try {
                    const inspectResult = await this.inspectDataSelection();
                    await this.previewDetectedAssets(inspectResult);
                    this.renderDataSummary(this.selectedPepPaths, this.selectedDatapointPaths);
                    this.showSourceFeedback(
                        `已直接使用项目注册资产：PEP ${this.selectedPepPaths.length} 个，Profile ${this.selectedDatapointPaths.length ? this.getPathName(this.selectedDatapointPath) : '未注册'}。`,
                        inspectResult?.warnings?.length ? 'warning' : 'success'
                    );
                } catch (inspectError) {
                    console.warn('Project asset auto inspection failed:', inspectError);
                    this.showSourceFeedback(
                        `已载入项目注册资产，但自动读取摘要失败：${inspectError.message || '未知错误'}。仍可进入模块配置。`,
                        'warning'
                    );
                }
            }
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
        const profileCount = this.getProjectProfileAssets(assets).length;
        const cachedCount = assets.filter(a => a.asset_type === 'cached_usage').length;
        const resultCount = assets.filter(a => a.asset_type === 'processed_result').length;

        assetsDiv.innerHTML = `
            <span class="sh-project-asset-pill">Pep Files <span class="sh-asset-count ms-1">${pepCount}</span></span>
            <span class="sh-project-asset-pill">Profile <span class="sh-asset-count ms-1">${profileCount}</span></span>
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

    async fetchAndRenderCachedUsageConfig() {
        const projectId = document.getElementById('scriptHubProjectSelect')?.value || '';
        const section = document.getElementById('scriptHubCachedUsageConfigSection');
        const cardsDiv = document.getElementById('scriptHubCachedUsageConfigCards');
        if (!section || !cardsDiv) return;

        section.style.display = '';
        cardsDiv.innerHTML = '<span class="text-muted small">正在加载缓存数据...</span>';

        try {
            if (!projectId) {
                cardsDiv.innerHTML = '<span class="text-muted small">未选择项目，无法加载缓存数据。</span>';
                return;
            }

            const resp = await fetch(`/api/projects/${encodeURIComponent(projectId)}/cached-assets?asset_type=cached_usage`);
            const cachedData = await resp.json();
            const assets = cachedData.success ? (cachedData.assets || []) : [];

            if (!assets.length) {
                cardsDiv.innerHTML = '<div class="alert alert-warning mb-0 small">'
                    + '<strong>暂无 VJ usage 缓存数据。</strong><br>'
                    + '火山图 / UMAPin 依赖 <b>PEP共享分析</b> 步骤 2-4 产生的 V/J/VJ usage 矩阵。'
                    + '<br>请先选择 <b>PEP共享分析</b> 模块并运行，数据将自动缓存到项目中。</div>';
                return;
            }

            cardsDiv.innerHTML = assets.map((asset, idx) => {
                const meta = asset.metadata || asset.metadata_json || {};
                const chains = (meta.chains || []).join(', ');
                const groups = (meta.group_fields || []).join(', ');
                const usageTypes = meta.usage_types || {};
                const hasVjUsage = !!usageTypes['1VJusage'] || !!usageTypes['0VJusage'];
                const vjLabel = hasVjUsage
                    ? '<span class="badge bg-success me-1" style="font-size:.68rem;">VJ usage 可用</span>'
                    : '<span class="badge bg-secondary me-1" style="font-size:.68rem;">无 VJ usage</span>';
                const targetLabel = this.activeModule === 'volcano' ? '火山图'
                    : (this.activeModule === 'ml-analysis' ? '机器学习' : 'UMAPin');
                return `<div class="sh-cached-source-card" data-cached-id="${this.escapeHtml(asset.id)}" data-index="${idx}" title="点击使用此缓存数据作为 ${targetLabel} 的数据源"><div class="d-flex justify-content-between align-items-start gap-2"><div class="fw-semibold">${this.escapeHtml(asset.original_name || 'Usage ' + String(idx + 1))}</div>${vjLabel}</div><div class="small text-muted">链：${this.escapeHtml(chains || '-')} | 分组：${this.escapeHtml(groups || '-')}</div><div class="small text-muted" style="font-size:.7rem;word-break:break-all;">${this.escapeHtml(this.getPathName(asset.storage_path) || asset.storage_path || '')}</div></div>`;
            }).join('');

            cardsDiv.querySelectorAll('.sh-cached-source-card').forEach((card) => {
                card.addEventListener('click', () => {
                    cardsDiv.querySelectorAll('.sh-cached-source-card').forEach(c => c.classList.remove('is-selected'));
                    card.classList.add('is-selected');
                    this._selectedCachedAssetId = card.dataset.cachedId;
                    const asset = assets[parseInt(card.dataset.index)];
                    if (asset) this._applyCachedUsageToModule(asset);
                });
            });
        } catch (error) {
            console.warn('Failed to fetch cached usage assets:', error);
            cardsDiv.innerHTML = '<span class="text-danger small">加载缓存数据失败。</span>';
        }
    },

    hideCachedUsageConfig() {
        const section = document.getElementById('scriptHubCachedUsageConfigSection');
        if (section) section.style.display = 'none';
    },

    async _applyCachedUsageToModule(asset) {
        const meta = asset.metadata || asset.metadata_json || {};
        const usageTypes = meta.usage_types || {};
        const vjUsagePath = usageTypes['1VJusage'] || usageTypes['0VJusage'] || '';

        try {
            const resp = await fetch(`/api/script-hub/cached-usage/${encodeURIComponent(asset.id)}/inspect`);
            const data = await resp.json();

            if (!data.success) {
                this.showSourceFeedback('读取缓存数据详情失败: ' + (data.message || '未知错误'), 'warning');
                return;
            }

            if (this.activeModule === 'volcano') {
                if (data.vj_usage_path) {
                    document.getElementById('scriptHubVolcanoDataDir').value = data.vj_usage_path;
                    this.showSourceFeedback('已选择缓存数据源 -> 火山图数据目录：' + (this.getPathName(data.vj_usage_path) || data.vj_usage_path), 'success');
                    await this.inspectVolcano(data.vj_usage_path, '扫描 VJ usage 数据...');
                } else {
                    const fallbackDir = data.storage_path;
                    if (fallbackDir && data.exists) {
                        document.getElementById('scriptHubVolcanoDataDir').value = fallbackDir;
                        this.showSourceFeedback('已选择缓存数据源，但未找到 1VJusage 子目录。将使用根目录。', 'warning');
                        await this.inspectVolcano(fallbackDir, '扫描数据...');
                    } else {
                        this.showSourceFeedback('所选缓存数据中未找到 VJ usage 子目录（1VJusage），无法用于火山图分析。', 'danger');
                    }
                }
            } else if (this.activeModule === 'umapin') {
                if (data.df_vj_all_path) {
                    document.getElementById('scriptHubUmapinDataPath').value = data.df_vj_all_path;
                    this.showSourceFeedback('已选择缓存数据源 -> UMAPin 数据文件：' + (this.getPathName(data.df_vj_all_path) || data.df_vj_all_path), 'success');
                    await this.inspectUmapin(data.df_vj_all_path, '扫描数据文件...');
                } else if (data.vj_usage_path) {
                    document.getElementById('scriptHubUmapinDataPath').value = data.vj_usage_path;
                    this.showSourceFeedback('已选择缓存数据源（1VJusage 目录），将自动查找数据文件。', 'info');
                    await this.inspectUmapin(data.vj_usage_path, '扫描数据文件...');
                } else if (data.storage_path) {
                    document.getElementById('scriptHubUmapinDataPath').value = data.storage_path;
                    this.showSourceFeedback('已选择缓存数据源，将自动查找数据文件。', 'info');
                    await this.inspectUmapin(data.storage_path, '扫描数据文件...');
                } else {
                    this.showSourceFeedback('所选缓存数据路径无效。', 'danger');
                }
            } else if (this.activeModule === 'ml-analysis') {
                const usagePath = data.vj_usage_path || data.storage_path || '';
                if (usagePath) {
                    document.getElementById('scriptHubMlUsagePath').value = usagePath;
                    const mode = document.getElementById('scriptHubMlMode');
                    if (mode) mode.value = 'vj-usage';
                    this.showSourceFeedback('已选择缓存数据源 -> 机器学习 VJ usage：' + (this.getPathName(usagePath) || usagePath), 'success');
                    await this.inspectMlAnalysis('检测机器学习输入...');
                } else {
                    this.showSourceFeedback('所选缓存数据路径无效。', 'danger');
                }
            }
        } catch (error) {
            console.warn('Failed to apply cached usage to module:', error);
            this.showSourceFeedback('应用缓存数据失败: ' + (error.message || '未知错误'), 'danger');
        }
    },

    async confirmDataSelection() {
        this.syncDataSelectionState();

        if (this.selectedPepPaths.length === 0 && this.selectedDatapointPaths.length === 0 && !this.selectedCachedAssetId) {
            alert('请先在目录树中加入 PEP 路径或设置 Profile 文件。');
            return;
        }

        let allPepPaths = [...this.selectedPepPaths];
        let allDpPaths = [...this.selectedDatapointPaths];
        let inspectResult = null;

        try {
            inspectResult = await this.inspectDataSelection();
            allPepPaths = [...this.selectedPepPaths];
            allDpPaths = [...this.selectedDatapointPaths];

            // Fill summary grid from inspection result
            const summaryGrid = document.getElementById('scriptHubSummaryGrid');
            if (summaryGrid && inspectResult) {
                summaryGrid.innerHTML = `
                    <div class="sh-metric">
                        <span class="sh-metric-label">Samples</span>
                        <div class="sh-metric-value">${this.escapeHtml(String(inspectResult.sample_count || 0))}</div>
                    </div>
                    <div class="sh-metric">
                        <span class="sh-metric-label">Chains</span>
                        <div class="sh-metric-value">${this.escapeHtml((inspectResult.chains || []).join(', ') || '-')}</div>
                    </div>
                    <div class="sh-metric">
                        <span class="sh-metric-label">Pep Files</span>
                        <div class="sh-metric-value">${this.escapeHtml(String(inspectResult.pep_file_count || 0))}</div>
                    </div>
                    <div class="sh-metric">
                        <span class="sh-metric-label">Profile</span>
                        <div class="sh-metric-value" title="${this.escapeHtml(inspectResult.profile_path || '未设置')}">${this.escapeHtml(this.getPathName(inspectResult.profile_path) || '未设置')}</div>
                    </div>
                `;
            }
        } catch (error) {
            this.showSourceFeedback(error.message || '数据选择检测失败。', 'danger');
            this.showError(error.message || '数据选择检测失败');
            return;
        }

        await this.previewDetectedAssets(inspectResult);

        this.evaluateAvailableModules(allPepPaths, allDpPaths);
        this.stageUnlocked.module = true;
        this.syncStageUI();
        this.renderModuleChips();
        this.renderDataSummary(allPepPaths, allDpPaths);
        this.showSourceFeedback('数据已确认。请在下方选择分析模块。', 'success');
        window.setTimeout(() => { document.getElementById('scriptHubAssetsStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 80);
    },

    async readPepPreview(filePath) {
        if (!filePath) return;
        const resp = await fetch('/api/script-hub/read-table-preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: filePath }),
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.message || '读取 PEP 文件失败');

        document.getElementById('scriptHubPepPreviewMeta').textContent =
            `PEP 示例文件：${filePath}。显示前 ${data.row_count || 0} 行，可横向滚动查看列。`;
        this.renderPepPreviewTable(data.columns || [], data.rows || []);
    },

    async previewDetectedAssets(inspectResult) {
        if (this.selectedDatapointPath) {
            try {
                await this.inspectProfile('', '正在读取 Profile 文件...', { skipScroll: true });
            } catch (e) {
                console.warn('Auto profile inspect failed:', e);
            }
        }

        const pepPreview = Array.isArray(inspectResult?.pep_files_preview) ? inspectResult.pep_files_preview : [];
        if (pepPreview.length > 0) {
            try {
                await this.readPepPreview(pepPreview[0].path);
            } catch (e) {
                console.warn('Auto pep preview failed:', e);
            }
        }
    },

    renderPepPreviewTable(columns, rows) {
        const table = document.getElementById('scriptHubPepPreviewTable');
        if (!table) return;
        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');
        const safeColumns = Array.isArray(columns) ? columns : [];
        const safeRows = Array.isArray(rows) ? rows.slice(0, 5) : [];

        if (!safeColumns.length) {
            thead.innerHTML = '';
            tbody.innerHTML = '<tr><td class="text-muted">等待检测 PEP 文件。</td></tr>';
            return;
        }
        thead.innerHTML = `<tr>${safeColumns.map((column) => `<th style="white-space:nowrap;">${this.escapeHtml(column)}</th>`).join('')}</tr>`;
        tbody.innerHTML = safeRows.length
            ? safeRows.map((row) => `<tr>${safeColumns.map((_, index) => `<td style="white-space:nowrap;">${this.escapeHtml(row[index] ?? '')}</td>`).join('')}</tr>`).join('')
            : '<tr><td class="text-muted" colspan="99">No preview rows</td></tr>';
    },

    evaluateAvailableModules(pepPaths, dpPaths) {
        const hasPep = pepPaths.length > 0 || !!this.selectedCachedAssetId;
        const hasDatapoint = dpPaths.length > 0;
        this.moduleAvailability = {
            'db-alignment': hasPep && hasDatapoint,
            'profile': hasDatapoint,
            'pep-analysis': hasPep && hasDatapoint,
            'pgen-analysis': hasPep && hasDatapoint,
            'topclone': hasPep && hasDatapoint,
            'umap': hasPep && hasDatapoint,
            'volcano': hasPep,
            'umapin': hasPep,
            'ml-analysis': hasDatapoint,
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
        this.resetDownstreamState({ preserveInspection: true });
        this._prefillModulePaths(moduleKey);
        this.syncModuleUI();
        this.stageUnlocked.config = true;
        this.syncStageUI();
        if (['db-alignment', 'profile', 'umap', 'pep-analysis', 'pgen-analysis', 'topclone', 'ml-analysis'].includes(moduleKey)) {
            this.ensureProfileControlsReady();
        }
        if (moduleKey === 'volcano' || moduleKey === 'umapin' || moduleKey === 'ml-analysis') {
            this.showSourceFeedback(
                moduleKey === 'volcano'
                    ? '已选择火山图分析。请从下方 PEP共享分析缓存数据中选择 VJ usage 数据源，或手动填写数据目录后点击检测。'
                    : (moduleKey === 'umapin'
                        ? '已选择 UMAPin 降维。请从下方 PEP共享分析缓存数据中选择 VJ usage 数据源，或手动填写数据文件后点击检测。'
                        : '已选择机器学习分析。默认使用 Profile 特征；切换到 VJ usage 模式时请选择 PEP共享分析缓存数据。'),
                'info'
            );
        } else {
            this.showSourceFeedback('已选择分析模块。请点击上方「检测数据」按钮扫描文件并自动填充配置。', 'info');
        }
        // Show cached usage data sources for volcano / umapin
        if (moduleKey === 'volcano' || moduleKey === 'umapin' || moduleKey === 'ml-analysis') {
            this.fetchAndRenderCachedUsageConfig();
        } else {
            this.hideCachedUsageConfig();
        }
        this.scheduleModuleAutoInspect(moduleKey);
        window.setTimeout(() => { document.getElementById('scriptHubConfigStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 120);
    },

    scheduleModuleAutoInspect(moduleKey) {
        const token = Date.now() + ':' + String(moduleKey || '');
        this._moduleAutoInspectToken = token;
        window.setTimeout(async () => {
            if (this._moduleAutoInspectToken !== token || this.activeModule !== moduleKey) return;
            if (!this.shouldAutoInspectModule(moduleKey)) return;
            try {
                await this.inspectBasePath('', this.getAutoInspectMessage(moduleKey));
            } catch (error) {
                console.warn('Auto inspect failed:', error);
            }
        }, 160);
    },

    shouldAutoInspectModule(moduleKey) {
        const hasPep = this._resolvePepPaths().length > 0 || Boolean(this._resolvePrimaryPepPath());
        const hasProfile = Boolean(this._resolveProfilePath());
        if (moduleKey === 'db-alignment') return hasPep && hasProfile;
        if (moduleKey === 'profile') return hasProfile;
        if (moduleKey === 'pep-analysis') return hasPep && hasProfile;
        if (moduleKey === 'pgen-analysis') return hasPep && hasProfile;
        if (moduleKey === 'topclone') return hasPep && hasProfile;
        if (moduleKey === 'umap') return hasProfile;
        if (moduleKey === 'ml-analysis') return hasProfile;
        return false;
    },

    getAutoInspectMessage(moduleKey) {
        const messages = {
            'db-alignment': '自动检测数据库比对数据...',
            'profile': '自动检测 Profile 文件...',
            'pep-analysis': '自动检测 PEP 共享分析数据...',
            'pgen-analysis': '自动检测 Pgen 输入...',
            'topclone': '自动检测 TopClone 数据...',
            'umap': '自动检测 UMAP Profile 数据...',
            'ml-analysis': '自动检测机器学习输入...',
        };
        return messages[moduleKey] || '自动检测数据...';
    },

    /** Pre-fill module-specific path fields from data-selection stage values (readonly inputs only, no auto-select). */
    _prefillModulePaths(moduleKey) {
        const pepPath = this._resolvePrimaryPepPath();
        const dpPath = this._resolveProfilePath();

        const setText = (id, val) => {
            const el = document.getElementById(id);
            if (el && val) this.ensureControlValue(el, val);
        };

        if (moduleKey === 'db-alignment') {
            setText('scriptHubProfilePath', dpPath);
        }
        if (moduleKey === 'profile') {
            setText('scriptHubDatapointPath', dpPath);
            setText('scriptHubBpDatapointPath', dpPath);
        }
        if (moduleKey === 'pep-analysis') {
            setText('scriptHubPepDataDir', pepPath);
            setText('scriptHubPepProfilePath', dpPath);
        }
        if (moduleKey === 'pgen-analysis') {
            setText('scriptHubPgenDataDir', pepPath);
            setText('scriptHubPgenProfilePath', dpPath);
        }
        if (moduleKey === 'topclone') {
            setText('scriptHubTcPepDataPath', pepPath);
            setText('scriptHubTcDatapointPath', dpPath);
        }
        if (moduleKey === 'umap') {
            setText('scriptHubDatapointPath', dpPath);
        }
        if (moduleKey === 'ml-analysis') {
            setText('scriptHubMlProfilePath', dpPath);
        }
        // volcano/umapin: do NOT prefill from pepPath - they need VJ usage data from PEP shared analysis cache
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
        this.resetDownstreamState({ preserveInspection: true });
        this.syncModuleUI();
    },

    syncModuleUI() {
        const module = this.activeModule || 'db-alignment';
        const isProfile = module === 'profile';
        const isBoxPlot = isProfile;
        const isTopClone = module === 'topclone';
        const isUmap = module === 'umap';
        const isMl = module === 'ml-analysis';
        const isPgen = module === 'pgen-analysis';

        document.querySelectorAll('[data-module]').forEach((el) => {
            const allowed = (el.getAttribute('data-module') || '').split(/\s+/);
            if (allowed.includes(module)) {
                el.style.display = '';
            } else {
                el.style.display = 'none';
            }
        });

        const runBtn = document.getElementById('scriptHubRunBtn');
        if (runBtn) {
            runBtn.style.display = '';
        }

        // Inspect button: visibility + icon/label update
        const inspectBtn = document.getElementById('scriptHubInspectBtn');
        if (inspectBtn) {
            inspectBtn.style.display = '';
            inspectBtn.querySelector('i').className = (isBoxPlot || isTopClone || isUmap || isMl || isPgen || module === 'pep-analysis') ? 'bi bi-table me-1' : 'bi bi-search me-1';
            const ibtnLabel = document.getElementById('scriptHubInspectBtnLabel');
            if (ibtnLabel) ibtnLabel.textContent = (isBoxPlot || isTopClone || isUmap || isMl || isPgen || module === 'pep-analysis' || module === 'volcano') ? '检测数据文件' : '检测数据';
        }

        const btnLabel = document.getElementById('scriptHubRunBtnLabel');
        const configHint = document.getElementById('scriptHubConfigHint');
        const summaryEl = document.getElementById('scriptHubResultSummary');
        const metaEl = document.getElementById('scriptHubResultMeta');

        if (isBoxPlot) {
            if (btnLabel) btnLabel.textContent = isProfile ? '运行 Profile 分析' : '运行箱线图分析';
            if (configHint) configHint.textContent = '启用分组可按组绘制箱线图并做 Mann-Whitney U 检验，取消则所有样本作为未分组箱体。';
            if (summaryEl) summaryEl.textContent = isProfile ? 'Profile 分析完成。' : '箱线图分析完成。';
            if (metaEl) metaEl.textContent = isProfile
                ? '任务完成后打开 Viewer 查看 Profile 箱线图结果。'
                : '任务完成后查看箱线图 PNG 和 p-value CSV。';
        } else if (module === 'pep-analysis') {
            if (btnLabel) btnLabel.textContent = '运行 PEP 共享分析';
            if (configHint) configHint.textContent = '选择 pep 数据目录、链类型、Profile 文件和分组字段，运行 PEP 共享分析流水线（步骤 2-8）。';
            if (summaryEl) summaryEl.textContent = 'PEP 共享分析完成。';
            if (metaEl) metaEl.textContent = '查看共享矩阵、usage 表、热图和分类结果。';
        } else if (isPgen) {
            if (btnLabel) btnLabel.textContent = '运行 Pgen 分析';
            if (configHint) configHint.textContent = '参考 Pgen_260213，使用 SoNNia 按样本/链计算 CDR3 Pgen、Q、Ppost，并汇总 Pgen_mean.csv。';
            if (summaryEl) summaryEl.textContent = 'Pgen 分析完成。';
            if (metaEl) metaEl.textContent = '打开 Viewer 查看 Pgen 图表，下载 ZIP 获取明细 CSV 和汇总表。';
        } else if (isTopClone) {
            if (btnLabel) btnLabel.textContent = '运行 TopClone 分析';
            if (configHint) configHint.textContent = 'Trace 模式：从 pep_data + Profile_All.csv 生成 topclone.csv 再做 BoxPlot。Per-sample 模式：每个样本单独提取 top clone。';
            if (summaryEl) summaryEl.textContent = 'TopClone 分析完成。';
            if (metaEl) metaEl.textContent = '任务完成后查看 topclone.csv 和箱线图。';
            const tcDatapointContainer = document.getElementById('scriptHubTcDatapointContainer');
            const tcSameDirToggle = document.getElementById('scriptHubTcSameDirToggle');
            if (tcDatapointContainer && tcSameDirToggle) {
                tcDatapointContainer.style.display = tcSameDirToggle.checked ? 'none' : '';
            }
        } else if (isUmap) {
            if (btnLabel) btnLabel.textContent = '运行 UMAP 分析';
            if (configHint) configHint.textContent = '基于 Mann-Whitney U 显著性过滤后做 UMAP 降维投影。';
            if (summaryEl) summaryEl.textContent = 'UMAP 分析完成。';
            if (metaEl) metaEl.textContent = '下载 ZIP 压缩包查看所有 UMAP 图和坐标数据。';
        } else if (module === 'volcano') {
            if (btnLabel) btnLabel.textContent = '运行火山图分析';
            if (configHint) configHint.textContent = '对 VJ usage 数据做两组间差异比较，生成火山图。';
            if (summaryEl) summaryEl.textContent = '火山图分析完成。';
            if (metaEl) metaEl.textContent = '查看火山图 PNG 和差异结果 CSV。';
        } else if (module === 'umapin') {
            if (btnLabel) btnLabel.textContent = '运行 UMAPin 降维';
            if (configHint) configHint.textContent = '基于 VJ usage 拼接数据做 UMAP 降维，可选 FDR 校正。';
            if (summaryEl) summaryEl.textContent = 'UMAPin 降维完成。';
            if (metaEl) metaEl.textContent = '查看 UMAP 散点图和坐标 CSV。';
        } else if (isMl) {
            const mlMode = document.getElementById('scriptHubMlMode')?.value || 'profile';
            const usageInput = document.getElementById('scriptHubMlUsagePath');
            if (usageInput) usageInput.closest('.sh-col-12').style.display = mlMode === 'vj-usage' ? '' : 'none';
            this.syncMlFeatureMode();
            if (btnLabel) btnLabel.textContent = '运行机器学习分析';
            if (configHint) configHint.textContent = '参考 ML_260526 随机森林流程，输出 CV accuracy、混淆矩阵、特征重要性和 ROC。';
            if (summaryEl) summaryEl.textContent = '机器学习分析完成。';
            if (metaEl) metaEl.textContent = '查看机器学习图表、CSV、报告文本和结果 ZIP。';
        } else {
            if (btnLabel) btnLabel.textContent = '运行数据库比对';
            if (configHint) configHint.textContent = '字段与 Profile 设置基于检测结果自动填充，之后可手动调整。';
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

    setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    },

    setHtml(id, value) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = value;
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
        this.toggleStage('scriptHubAssetsStage', unlocked.module);
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
            unlocked.config ? { text: '已检测', tone: 'success' }
            : unlocked.module ? { text: '等待选模块', tone: 'active' } : { text: '未激活', tone: 'default' });

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

    resetDownstreamState(options = {}) {
        const preserveInspection = Boolean(options && options.preserveInspection);
        if (!preserveInspection) {
            this.inspectData = null;
        }
        this.result = null;
        this.activeTaskId = null;
        this.stopTaskPolling();
        if (!preserveInspection) {
            this.setInspectSummary('等待检测目录。', 'info');
        }
        this.setText('scriptHubResultLog', '等待结果。');
        const isProfile = this.activeModule === 'profile';
        const isBp = this.activeModule === 'boxplot' || isProfile;
        this.setText('scriptHubResultSummary', isProfile ? 'Profile 分析完成。' : (isBp ? '箱线图分析完成。' : '数据库比对完成。'));
        this.setText('scriptHubResultMeta', isBp
            ? (isProfile ? '任务完成后打开 Viewer 查看 Profile 箱线图结果。' : '任务完成后在这里查看箱线图结果。')
            : '任务完成后在这里查看输出、下载结果。');
        if (!preserveInspection) {
            this.setText('scriptHubPreviewFileMeta', '等待检测文件。');
            this.renderPreviewTable([], []);
            this.renderDataPreview([], [], '等待检测 Profile 或 PEP 文件。检测后显示一个示例文件的前 5 行。');
            this.renderPepPreviewTable([], []);
            document.getElementById('scriptHubPepPreviewMeta').textContent = '等待检测 PEP 文件。';
        }
        const dpSelect = document.getElementById('scriptHubDatapointPath');
        if (dpSelect && !preserveInspection) {
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

        if (!preserveInspection) {
            this.setHtml('scriptHubParamBegin', '<option value="">Select column</option>');
            this.setHtml('scriptHubParamOver', '<option value="">Select column</option>');
            this.setHtml('scriptHubColumnChips', '<span class="sh-chip">No columns detected</span>');
            this.setText('scriptHubBpParamSuggestion', '-');
            document.getElementById('scriptHubBpSuggestions')?.classList.add('sh-hidden');
        }

        this.setHtml('scriptHubBoxPlotSingleImage', '<p class="text-muted small">Select a parameter above to view its boxplot.</p>');
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
        const pepLinks = document.getElementById('scriptHubPepResultLinks');
        if (pepLinks) pepLinks.innerHTML = '';
        const pepImage = document.getElementById('scriptHubPepResultImage');
        if (pepImage) pepImage.innerHTML = '<p class="text-muted small">Select result type and chain above to view.</p>';
        const pepGroupSelect = document.getElementById('scriptHubPepGroupSelect');
        if (pepGroupSelect) pepGroupSelect.innerHTML = '<option value="">-- Select --</option>';
        const pepChainSelect = document.getElementById('scriptHubPepChainSelect');
        if (pepChainSelect) pepChainSelect.innerHTML = '<option value="">-- Select --</option>';
        this.setUiState(preserveInspection && this.inspectData ? 'inspected' : 'idle');
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
        // Main run button is hidden by syncModuleUI for charts
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

    getSelectedMultiValues(selectId) {
        return Array.from(document.getElementById(selectId)?.selectedOptions || [])
            .map(option => option.value)
            .filter(Boolean);
    },

    populateMultiSelect(selectId, options, selectedValues = [], { preserve = false } = {}) {
        const select = document.getElementById(selectId);
        if (!select) return;

        const safeOptions = Array.isArray(options)
            ? options.map(item => String(item || '')).filter(Boolean)
            : [];
        const previousValues = Array.from(select.selectedOptions || []).map(option => option.value).filter(Boolean);
        const desiredValues = preserve && previousValues.length ? previousValues : selectedValues;
        const desiredSet = new Set((Array.isArray(desiredValues) ? desiredValues : []).map(item => String(item || '')));

        select.innerHTML = safeOptions.length
            ? safeOptions.map((option) => `<option value="${this.escapeHtml(option)}">${this.escapeHtml(option)}</option>`).join('')
            : '<option value="">No options</option>';

        Array.from(select.options).forEach((option) => {
            option.selected = desiredSet.has(option.value);
        });
    },

    renderPepGroupFieldList(categoryMeta = null) {
        const list = document.getElementById('scriptHubPepGroupFieldList');
        const select = document.getElementById('scriptHubPepGroupFields');
        if (!list || !select) return;
        const selected = new Set(this.getSelectedMultiValues('scriptHubPepGroupFields'));
        const countMap = new Map();
        if (Array.isArray(categoryMeta)) {
            categoryMeta.forEach((item) => {
                countMap.set(String(item.field || ''), Number(item.unique_count || 0));
            });
        }
        const options = Array.from(select.options || []).map(option => option.value).filter(Boolean);
        if (!options.length) {
            list.innerHTML = '<div class="sh-category-preview-empty">等待 Profile 检测</div>';
            return;
        }
        list.innerHTML = options.map((field) => {
            const isSelected = selected.has(field);
            const count = countMap.has(field) ? '<span class="sh-category-field-count">' + countMap.get(field) + ' 类</span>' : '<span class="sh-category-field-count">字段</span>';
            return '<button type="button" class="sh-category-field ' + (isSelected ? 'is-selected' : '') + '" data-pep-group-field="' + this.escapeHtml(field) + '" title="' + this.escapeHtml(field) + '"><span>' + this.escapeHtml(field) + '</span>' + count + '</button>';
        }).join('');
    },

    togglePepGroupField(field) {
        if (!field) return;
        const select = document.getElementById('scriptHubPepGroupFields');
        if (!select) return;
        const option = Array.from(select.options || []).find(item => item.value === field);
        if (!option) return;
        option.selected = !option.selected;
        this.markFieldTouched('scriptHubPepGroupFields');
        this.renderPepGroupFieldList();
        this.updatePepGroupValuePreview();
    },

    onPepGroupSelectChange() {
        this.renderPepGroupFieldList();
        this.updatePepGroupValuePreview();
    },

    renderPepGroupValuePreview(fields = [], { loading = false, message = '' } = {}) {
        const preview = document.getElementById('scriptHubPepGroupValuePreview');
        if (!preview) return;
        if (loading) { preview.innerHTML = '<div class="sh-category-preview-empty">正在读取分类值...</div>'; return; }
        if (message) { preview.innerHTML = '<div class="sh-category-preview-empty">' + this.escapeHtml(message) + '</div>'; return; }
        if (!Array.isArray(fields) || !fields.length) { preview.innerHTML = '<div class="sh-category-preview-empty">选择字段后展示分类值</div>'; return; }
        preview.innerHTML = fields.map((fieldInfo) => {
            const values = Array.isArray(fieldInfo.values) ? fieldInfo.values : [];
            const chips = values.length ? values.map(value => '<span class="sh-category-value" title="' + this.escapeHtml(value) + '">' + this.escapeHtml(value) + '</span>').join('') : '<span class="sh-category-value">无非空分类值</span>';
            const extra = fieldInfo.truncated ? '，仅显示前 40 个' : '';
            return '<div class="sh-category-preview-item"><div class="sh-category-preview-title"><span>' + this.escapeHtml(fieldInfo.field || '') + '</span><span class="text-muted">' + String(fieldInfo.unique_count || 0) + ' 类' + extra + '</span></div><div class="sh-category-values">' + chips + '</div></div>';
        }).join('');
    },

    async updatePepGroupValuePreview() {
        const categories = this.getSelectedMultiValues('scriptHubPepGroupFields');
        if (!categories.length) { this.renderPepGroupFieldList(); this.renderPepGroupValuePreview([]); return; }
        const profilePath = document.getElementById('scriptHubPepProfilePath')?.value?.trim() || this.selectedDatapointPath || '';
        if (!profilePath) { this.renderPepGroupValuePreview([], { message: '请先选择 Profile 文件' }); return; }
        this.renderPepGroupValuePreview([], { loading: true });
        try {
            const response = await fetch('/api/script-hub/db-alignment/profile-categories', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ profile_path: profilePath, profile_sheet: null, categories }),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '读取分类值失败');
            const fields = Array.isArray(data.fields) ? data.fields : [];
            this.renderPepGroupFieldList(fields);
            this.renderPepGroupValuePreview(fields, { message: fields.length ? '' : '所选字段没有可预览的分类值' });
        } catch (error) {
            this.renderPepGroupValuePreview([], { message: error.message || '读取分类值失败' });
        }
    },

    renderDataPreview(columns, rows, metaText = '') {
        const table = document.getElementById('scriptHubBpPreviewTable');
        if (!table) return;

        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');
        const safeColumns = Array.isArray(columns) ? columns : [];
        const safeRows = Array.isArray(rows) ? rows.slice(0, 5) : [];
        const meta = document.getElementById('scriptHubBpPreviewMeta');
        if (meta) {
            meta.textContent = metaText || (safeColumns.length ? `已加载示例文件前 ${safeRows.length} 行。可横向滚动查看列。` : '等待检测 Profile 或 PEP 文件。检测后显示一个示例文件的前 5 行。');
        }

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

    renderPreviewTable(columns, rows, metaText = '') {
        this.renderDataPreview(columns, rows, metaText);
        const table = document.getElementById('scriptHubPreviewTable');
        if (!table) return;

        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');
        const safeColumns = Array.isArray(columns) ? columns : [];
        const safeRows = Array.isArray(rows) ? rows.slice(0, 5) : [];

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
        return this._resolvePrimaryPepPath();
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
        // Show main run button for charts
        const runBtn = document.getElementById('scriptHubRunBtn');
        if (runBtn) runBtn.style.display = '';
    },

    hideChartFieldAndRunSteps() {
        const fieldStep = document.getElementById('scriptHubChartFieldStep');
        const runStep = document.getElementById('scriptHubChartRunStep');
        if (fieldStep) fieldStep.style.display = 'none';
        if (runStep) runStep.style.display = 'none';
        document.getElementById('scriptHubChartFlow')?.classList.remove('has-confirmed-samples');
        // Re-hide main run button — needs re-confirm fields to show again
        const runBtn = document.getElementById('scriptHubRunBtn');
        if (runBtn && this.activeModule === 'charts') {
            runBtn.style.display = 'none';
        }
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

        const usingProjectAssets = !!this.getActiveProjectId() && (this._resolveProjectPepPaths().length > 0 || !!this._resolveProfilePath());
        document.getElementById('scriptHubPreviewFileMeta').textContent = usingProjectAssets
            ? `项目资产：PEP ${this._resolveProjectPepPaths().length} 个；Profile ${this.getPathName(this._resolveProfilePath()) || '未注册'}。`
            : (data.preview_file_path ? `Preview file: ${data.preview_file_path}` : 'No preview file detected.');
        document.getElementById('scriptHubConfigHint').textContent = usingProjectAssets
            ? '已直接使用项目注册的 PEP/Profile 资产；字段建议来自项目资产，可直接运行或微调参数。'
            : (data.preview_file_path
                ? `Auto-filled from ${data.preview_file_path}. You can adjust any value before running.`
                : 'Field suggestions are based on the current inspection result. You can adjust any value before running.');
        this.renderPreviewTable(
            data.preview_columns || [],
            data.preview_rows || [],
            data.preview_file_path
                ? `PEP 示例文件：${data.preview_file_path}。显示前 5 行，可横向滚动查看列。`
                : '未检测到可预览的 PEP 文件。'
        );

        document.getElementById('scriptHubResultLog').textContent = '等待结果。';
        document.getElementById('scriptHubResultSummary').textContent = 'DB alignment completed.';
        document.getElementById('scriptHubResultMeta').textContent = '任务完成后在这里查看输出、下载结果或打开 viewer。';

        window.setTimeout(() => {
            document.getElementById('scriptHubConfigStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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

    async addHighlightedPep() {
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
        // Register to project immediately so tags update
        const projectId = document.getElementById('scriptHubProjectSelect')?.value || '';
        if (projectId) {
            await this._registerPathToProject('pep', path);
            await this.refreshProjectAssetSummary(projectId);
        }
        this.showSourceFeedback(`已加入 PEP 路径：${path}`, 'success');
    },

    async removeSelectedPep(path) {
        const name = this.getPathName(path) || path;
        if (!confirm(`确定要移除此 PEP 路径吗？\n\n${name}`)) return;

        // Delete project asset first so it doesn't come back on refresh
        const assetId = this._findProjectAssetId('pep', path);
        const projectId = document.getElementById('scriptHubProjectSelect')?.value || '';
        if (assetId) {
            await fetch(`/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}`, { method: 'DELETE' });
        }

        this.dataSelection.pepPaths = this.dataSelection.pepPaths.filter(item => item.path !== path);
        this.dataSelection.validation = null;
        this.syncDataSelectionState();
        // Refresh project asset tags
        if (projectId) await this.refreshProjectAssetSummary(projectId);
        this.showSourceFeedback('已移除 PEP 路径。', 'info');
    },

    async clearSelectedProfile() {
        const name = this.getPathName(this.dataSelection.profilePath) || this.dataSelection.profilePath;
        if (!confirm(`确定要清除 Profile 文件吗？\n\n${name}`)) return;

        const oldPath = this.dataSelection.profilePath;
        // Delete project asset first so it doesn't come back on refresh
        const assetId = this._findProjectProfileAssetId(oldPath);
        const projectId = document.getElementById('scriptHubProjectSelect')?.value || '';
        if (assetId) {
            await fetch(`/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}`, { method: 'DELETE' });
        }

        this.dataSelection.profilePath = '';
        this.dataSelection.profileSheet = null;
        this.dataSelection.profileType = '';
        this.dataSelection.validation = null;
        this.syncDataSelectionState();
        // Refresh project asset tags
        if (projectId) await this.refreshProjectAssetSummary(projectId);
        this.showSourceFeedback('已清除 Profile 文件。', 'info');
    },

    _findProjectAssetId(assetType, storagePath) {
        if (!storagePath || !this.projectAssets) return null;
        const normalized = String(storagePath).replace(/\\/g, '/');
        const asset = this.projectAssets.find(a =>
            a.asset_type === assetType &&
            String(a.storage_path || '').replace(/\\/g, '/') === normalized
        );
        return asset ? asset.id : null;
    },

    isProjectProfileAsset(asset) {
        if (!asset) return false;
        const assetType = String(asset.asset_type || '').toLowerCase();
        return assetType === 'profile';
    },

    getProjectProfileAssets(assets) {
        return (assets || []).filter((asset) => this.isProjectProfileAsset(asset));
    },

    getProjectPepAssets(assets) {
        return (assets || []).filter((asset) => asset && asset.asset_type === 'pep' && asset.storage_path);
    },

    _resolveProjectPepPaths() {
        if (!this.getActiveProjectId()) return [];
        return [...new Set(this.getProjectPepAssets(this.projectAssets || []).map(asset => asset.storage_path).filter(Boolean))];
    },

    _resolvePepPaths() {
        const projectPepPaths = this._resolveProjectPepPaths();
        if (projectPepPaths.length) return projectPepPaths;
        return [...new Set([
            ...(this.selectedPepPaths || []),
            ...(this.customPepPaths || []),
            document.getElementById('scriptHubBasePath')?.value?.trim() || '',
        ].filter(Boolean))];
    },

    _resolvePrimaryPepPath() {
        return this._resolvePepPaths()[0] || '';
    },

    _findProjectProfileAssetId(storagePath) {
        if (!storagePath || !this.projectAssets) return null;
        const normalized = String(storagePath).replace(/\\/g, '/');
        const asset = this.getProjectProfileAssets(this.projectAssets).find(a =>
            String(a.storage_path || '').replace(/\\/g, '/') === normalized
        );
        return asset ? asset.id : null;
    },

    ensureControlValue(controlOrId, value, label = '') {
        const control = typeof controlOrId === 'string' ? document.getElementById(controlOrId) : controlOrId;
        if (!control) return;
        if (!value) {
            control.value = '';
            return;
        }
        if (control.tagName !== 'SELECT') {
            control.value = value;
            return;
        }
        const stringValue = String(value);
        const hasOption = Array.from(control.options || []).some(option => option.value === stringValue);
        if (!hasOption) {
            const option = document.createElement('option');
            option.value = stringValue;
            option.textContent = label || this.getPathName(stringValue) || stringValue;
            control.appendChild(option);
        }
        control.value = stringValue;
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
        const boxplotProfileInput = document.getElementById('scriptHubBpDatapointPath');
        const pepProfileInput = document.getElementById('scriptHubPepProfilePath');
        const sheetInput = document.getElementById('scriptHubProfileSheet');
        const dbProfileInput = document.getElementById('scriptHubProfilePath');
        if (baseInput) baseInput.value = this.selectedPepPaths[0] || '';
        if (profileInput) this.ensureControlValue(profileInput, this.selectedDatapointPath);
        if (boxplotProfileInput) this.ensureControlValue(boxplotProfileInput, this.selectedDatapointPath);
        if (pepProfileInput) this.ensureControlValue(pepProfileInput, this.selectedDatapointPath);
        if (sheetInput) sheetInput.value = this.dataSelection.profileSheet || '';
        if (dbProfileInput) {
            dbProfileInput.value = this.selectedDatapointPath || '';
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
            const sheetInfo = this.dataSelection.profileSheet
                ? `<span class="badge bg-info ms-1" style="font-size:.7rem;">工作表: ${this.escapeHtml(this.dataSelection.profileSheet)}</span>` : '';
            profileList.innerHTML = profilePath
                ? `<div class="sh-selected-row">
                    <div title="${this.escapeHtml(profilePath)}">
                        <strong>${this.escapeHtml(this.getPathName(profilePath) || profilePath)}${sheetInfo}</strong>
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
        const currentProfilePath = this.selectedDatapointPath || this.dataSelection.profilePath || '';
        const body = {
            project_id: projectId || null,
            pep_paths: this.selectedPepPaths,
            profile_path: currentProfilePath || null,
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
        if (data.profile_path) {
            this.dataSelection.profilePath = data.profile_path;
            this.dataSelection.profileType = 'file';
            this.selectedDatapointPath = data.profile_path;
            this.selectedDatapointPaths = [data.profile_path];
            this.syncDataSelectionState();
            this.dataSelection.validation = data;
        } else if (data.invalid_profile_paths && data.invalid_profile_paths.length) {
            const registeredProfilePath = (Array.isArray(data.registered_profile_paths) && data.registered_profile_paths[0])
                || currentProfilePath
                || '';
            this.dataSelection.profilePath = registeredProfilePath;
            this.dataSelection.profileType = registeredProfilePath ? 'file' : '';
            this.selectedDatapointPath = registeredProfilePath;
            this.selectedDatapointPaths = registeredProfilePath ? [registeredProfilePath] : [];
            this.syncDataSelectionState();
            this.dataSelection.validation = data;
        }
        this.showSourceFeedback(
            `数据检测完成：${data.sample_count || 0} 个样本，${data.pep_file_count || 0} 个 PEP 文件，${(data.chains || []).join(', ') || '未识别链'}。`,
            (data.warnings || []).length ? 'warning' : 'success'
        );
        return data;
    },

    async refreshProjectAssetSummary(projectId) {
        if (!projectId) return;
        try {
            const resp = await fetch(`/api/projects/${encodeURIComponent(projectId)}`);
            const project = await resp.json();
            this.projectAssets = project.assets || [];
            this.renderProjectAssetSummary(project);
        } catch (e) {
            console.warn('Failed to refresh project asset summary:', e);
        }
    },

    getPathName(path) {
        return String(path || '').replace(/\\/g, '/').split('/').filter(Boolean).pop() || String(path || '');
    },

    isTabularFile(path) {
        return /\.(csv|tsv|csv\.gz|xlsx)$/i.test(String(path || ''));
    },

    async setHighlightedProfile() {
        const selection = this.highlightedSource;
        if (!selection?.path) return;
        if (selection.type !== 'file' || !this.isTabularFile(selection.path)) {
            this.showSourceFeedback('Profile 需要选择 CSV/TSV/XLSX 文件。', 'warning');
            return;
        }

        // If it's an xlsx, show sheet picker first
        if (/\.xlsx$/i.test(selection.path)) {
            await this._selectXlsxSheet(selection.path);
            return;
        }

        this.dataSelection.profilePath = selection.path;
        this.dataSelection.profileSheet = null;
        this.dataSelection.profileType = selection.type || 'file';
        this.dataSelection.validation = null;
        this.syncDataSelectionState();
        // Register to project immediately so tags update
        const projectId = document.getElementById('scriptHubProjectSelect')?.value || '';
        if (projectId) {
            await this._registerPathToProject('profile', selection.path, {
                source: 'script-hub',
                role: 'profile',
                registered_from: 'data-selection',
            });
            await this.refreshProjectAssetSummary(projectId);
        }
        this.showSourceFeedback(`已设置 Profile 文件：${selection.path}`, 'success');
    },

    async _selectXlsxSheet(filePath) {
        this.showSourceFeedback('正在读取 Excel 工作表列表...', 'secondary');
        try {
            const resp = await fetch('/api/file-sheets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: filePath }),
            });
            const data = await resp.json();
            if (!data.success) throw new Error(data.message || '读取工作表失败');

            const sheets = data.sheets || [];
            if (!sheets.length) throw new Error('Excel 文件没有工作表');

            if (sheets.length === 1) {
                // Single sheet, auto-select
                this.dataSelection.profilePath = filePath;
                this.dataSelection.profileSheet = sheets[0];
                this.dataSelection.profileType = 'file';
                this.dataSelection.validation = null;
                this.syncDataSelectionState();
                this.showSourceFeedback(`已设置 Profile：${filePath} → ${sheets[0]}`, 'success');
                return;
            }

            // Multiple sheets — show picker
            this._showXlsxSheetPicker(filePath, sheets);
        } catch (error) {
            this.showSourceFeedback(error.message || '读取工作表失败', 'danger');
        }
    },

    _showXlsxSheetPicker(filePath, sheets) {
        const profileList = document.getElementById('scriptHubProfileSelectionList');
        if (!profileList) return;
        profileList.innerHTML = '<div class="d-flex flex-column gap-2">' +
            '<div class="fw-semibold small">选择工作表</div>' +
            '<div class="text-muted small text-truncate">' + this.escapeHtml(filePath) + '</div>' +
            sheets.map((s, i) =>
                '<button class="btn btn-outline-secondary btn-sm text-start" data-xlsx-sheet="' + this.escapeHtml(s) + '">' +
                this.escapeHtml(s) +
                '</button>'
            ).join('') +
            '<button class="btn btn-link btn-sm text-muted text-start" data-xlsx-sheet="">取消</button>' +
            '</div>';
        profileList.querySelectorAll('[data-xlsx-sheet]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const sheet = btn.dataset.xlsxSheet;
                const projectId = document.getElementById('scriptHubProjectSelect')?.value || '';
                if (sheet) {
                    this.dataSelection.profilePath = filePath;
                    this.dataSelection.profileSheet = sheet;
                    this.dataSelection.profileType = 'file';
                    this.dataSelection.validation = null;
                    this.syncDataSelectionState();
                    // Register to project immediately so tags update
                    if (projectId) {
                        await this._registerPathToProject('profile', filePath, {
                            source: 'script-hub',
                            role: 'profile',
                            profile_sheet: sheet,
                            registered_from: 'data-selection',
                        });
                        await this.refreshProjectAssetSummary(projectId);
                    }
                    this.showSourceFeedback(`已设置 Profile：${filePath} → ${sheet}`, 'success');
                } else {
                    this.syncDataSelectionState();
                }
            });
        });
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
        this.selectedDatapointPaths = dp ? [dp] : [];
        this.selectedDatapointPath = dp || '';

        if (any) {
            this.evaluateAvailableModules(this.selectedPepPaths, this.selectedDatapointPaths);
            const mainBtn = document.getElementById('scriptHubDataConfirmBtn');
            if (mainBtn) mainBtn.disabled = false;
            if (both) {
                this.showSourceFeedback('PEP 和 Profile 均已确认，全部模块可用。点击下方按钮进入下一步。', 'success');
            } else if (pep) {
                this.showSourceFeedback('PEP 已确认；数据库比对/共享分析/TopClone 还需要 Profile 文件。', 'warning');
            } else {
                this.showSourceFeedback('Profile 已确认（箱线图/UMAP/火山图/UMAPin 可用），数据库比对/共享分析/TopClone 还需要 PEP 目录。', 'warning');
            }
        }
    },


    _resolveProfilePath() {
        const projectProfile = this.getProjectProfileAssets(this.projectAssets || [])[0]?.storage_path || '';
        if (this.getActiveProjectId() && projectProfile) return projectProfile;
        return this.selectedDatapointPath
            || document.getElementById('scriptHubDatapointPath')?.value?.trim()
            || document.getElementById('scriptHubBpDatapointPath')?.value?.trim()
            || document.getElementById('scriptHubProfilePath')?.value?.trim()
            || document.getElementById('scriptHubPgenProfilePath')?.value?.trim()
            || (this.dataSelection && this.dataSelection.profilePath)
            || projectProfile
            || '';
    },

    getActiveProjectId() {
        return document.getElementById('scriptHubProjectSelect')?.value || this.projectContext?.projectId || '';
    },

    async inspectBasePath(explicitBasePath = '', loadingText = 'Scanning asset directory...') {
        const module = this.activeModule || 'db-alignment';

        if (module === 'profile') {
            return this.inspectProfile(explicitBasePath, loadingText);
        }
        if (module === 'boxplot') {
            return this.inspectProfile(explicitBasePath, loadingText);
        }
        if (module === 'pep-analysis') {
            return this.inspectPepAnalysis(explicitBasePath, loadingText);
        }
        if (module === 'pgen-analysis') {
            return this.inspectPgenAnalysis(explicitBasePath, loadingText);
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
        if (module === 'ml-analysis') {
            return this.inspectMlAnalysis(loadingText);
        }

        const basePath = explicitBasePath
            || this._resolvePrimaryPepPath();

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
                project_id: this.getActiveProjectId() || null,
                profile_path: this._resolveProfilePath() || null,
                pep_paths: this._resolvePepPaths(),
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
                project_id: this.getActiveProjectId() || null,
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
                fileSelect.innerHTML = '<option value="">-- 请选择 --</option>' + (candidates.length
                    ? candidates.map((f) => {
                        const parts = f.replace(/\\/g, '/').split('/');
                        const basename = parts[parts.length - 1] || f;
                        return `<option value="${this.escapeHtml(f)}">${this.escapeHtml(basename)}</option>`;
                    }).join('')
                    : '<option value="">No CSV/TSV files found</option>');
            });

            this.showSourceFeedback(
                `箱线图检测完成。在 ${data.datapoint_path || '数据文件'} 中检测到 ${data.column_count || 0} 列。`,
                'success'
            );
            this.setInspectSummary(`数据文件：${data.datapoint_path} — ${data.column_count} 列`, 'success');

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
            this.renderDataPreview(
                columns,
                data.preview_rows || [],
                `Profile 示例文件：${data.datapoint_path || '-'}. 显示前 5 行，可横向滚动查看列。`
            );

            this._populateParamRangeSelects(columns);

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
                document.getElementById('scriptHubConfigStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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

    async inspectPepAnalysis(explicitBasePath = '', loadingText = 'Scanning pep data...') {
        const basePath = explicitBasePath
            || this._resolvePrimaryPepPath();
        const profilePath = this._resolveProfilePath();

        if (!basePath) {
            this.showSourceFeedback('请先提供 PEP 数据路径。', 'warning');
            this.showError('请先提供 PEP 数据路径');
            return;
        }

        this.setUiState('inspecting');
        this.showSourceFeedback('正在检测 PEP 数据...', 'secondary');
        this.showLoading(loadingText || '扫描 PEP 数据...', '检测 PEP 共享分析');
        try {
            const body = {
                base_path: basePath,
                pep_paths: this._resolvePepPaths(),
                profile_path: profilePath || null,
                project_id: this.getActiveProjectId() || null,
            };
            const response = await fetch('/api/script-hub/pep-analysis/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || 'PEP 分析检测失败');

            this.inspectData = data;
            this.result = null;
            this.lastInspectedBasePath = basePath;
            this.setUiState('inspected');

            document.getElementById('scriptHubPepDataDir').value = basePath;
            this._pepSelectedChains = Array.isArray(data.chains) ? data.chains : [];
            this._pepAvailableChains = Array.isArray(data.chains) ? data.chains : [];

            const chainChips = document.getElementById('scriptHubPepChains');
            if (chainChips) {
                chainChips.innerHTML = this._pepAvailableChains.length
                    ? this._pepAvailableChains.map(c => `<span class="sh-chip sh-chip-selectable sh-chip-selected" data-pep-chain="${this.escapeHtml(c)}">${this.escapeHtml(c)}</span>`).join('')
                    : '<span class="sh-chip">No chains detected</span>';
                chainChips.querySelectorAll('.sh-chip-selectable').forEach(chip => {
                    chip.addEventListener('click', () => {
                        chip.classList.toggle('sh-chip-selected');
                        this._pepSelectedChains = this._getSelectedPepChains();
                    });
                });
            }

            const profileSelect = document.getElementById('scriptHubPepProfilePath');
            if (profileSelect && Array.isArray(data.profile_candidates)) {
                profileSelect.innerHTML = '<option value="">-- Select a Profile CSV --</option>' +
                    data.profile_candidates.map(p => `<option value="${this.escapeHtml(p)}">${this.escapeHtml(p.split('/').filter(Boolean).pop() || p)}</option>`).join('');
                if (data.profile_path) {
                    if (!Array.from(profileSelect.options).some(option => option.value === data.profile_path)) {
                        const opt = document.createElement('option');
                        opt.value = data.profile_path;
                        opt.textContent = data.profile_path.replace(/\\/g, '/').split('/').pop() || data.profile_path;
                        profileSelect.appendChild(opt);
                    }
                    profileSelect.value = data.profile_path;
                    this.selectedDatapointPath = data.profile_path;
                    this.selectedDatapointPaths = [data.profile_path];
                    this.dataSelection.profilePath = data.profile_path;
                }
            }

            const groupFieldsSelect = document.getElementById('scriptHubPepGroupFields');
            if (groupFieldsSelect && Array.isArray(data.group_fields)) {
                const previousSelection = this.shouldPreserveField('scriptHubPepGroupFields')
                    ? new Set(this.getSelectedMultiValues('scriptHubPepGroupFields'))
                    : new Set();
                groupFieldsSelect.innerHTML = data.group_fields.map(f => `<option value="${this.escapeHtml(f)}">${this.escapeHtml(f)}</option>`).join('');
                Array.from(groupFieldsSelect.options).forEach(option => { option.selected = previousSelection.has(option.value); });
                this.renderPepGroupFieldList();
                this.updatePepGroupValuePreview();
            }

            this.showSourceFeedback(`PEP 共享分析检测完成。发现 ${data.chain_count} 条链，${data.sample_count} 个样本。`, 'success');
            this.setInspectSummary(`链：${(data.chains || []).join(', ')} — ${data.sample_count} 个样本`, 'success');
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.setInspectSummary(error.message || 'PEP analysis inspection failed', 'danger');
            this.showSourceFeedback(error.message || 'PEP analysis inspection failed.', 'danger');
            this.showError(error.message || 'PEP analysis inspection failed');
        } finally {
            this.hideLoading();
        }
    },

    _getSelectedPepChains() {
        const chips = document.querySelectorAll('#scriptHubPepChains .sh-chip-selected');
        return Array.from(chips).map(c => c.dataset.pepChain || '').filter(Boolean);
    },

    async inspectPgenAnalysis(explicitBasePath = '', loadingText = 'Scanning Pgen inputs...') {
        const basePath = explicitBasePath || this._resolvePrimaryPepPath();
        const profilePath = this._resolveProfilePath();

        if (!basePath) {
            this.showSourceFeedback('请先提供 PEP 数据路径。', 'warning');
            this.showError('请先提供 PEP 数据路径');
            return;
        }
        if (!profilePath) {
            this.showSourceFeedback('请先提供 Profile 文件。', 'warning');
            this.showError('请先提供 Profile 文件');
            return;
        }

        this.setUiState('inspecting');
        this.showSourceFeedback('正在检测 Pgen 输入...', 'secondary');
        this.showLoading(loadingText || '扫描 Pgen 输入...', '检测 Pgen 分析');
        try {
            const body = {
                base_path: basePath,
                pep_paths: this._resolvePepPaths(),
                profile_path: profilePath,
                project_id: this.getActiveProjectId() || null,
            };
            const response = await fetch('/api/script-hub/pgen-analysis/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || 'Pgen 分析检测失败');

            this.inspectData = data;
            this.result = null;
            this.lastInspectedBasePath = basePath;
            this.setUiState('inspected');

            document.getElementById('scriptHubPgenDataDir').value = data.base_path || basePath;
            document.getElementById('scriptHubPgenProfilePath').value = data.profile_path || profilePath;

            this._pgenAvailableChains = Array.isArray(data.chains) ? data.chains : [];
            this._pgenSelectedChains = Array.isArray(data.runnable_chains) ? data.runnable_chains : [];
            const chainChips = document.getElementById('scriptHubPgenChains');
            if (chainChips) {
                chainChips.innerHTML = this._pgenAvailableChains.length
                    ? this._pgenAvailableChains.map((chain) => {
                        const runnable = this._pgenSelectedChains.includes(chain);
                        const disabled = !runnable && (data.skipped_chains || []).includes(chain);
                        return `<span class="sh-chip sh-chip-selectable${runnable ? ' sh-chip-selected' : ''}${disabled ? ' is-disabled' : ''}" data-pgen-chain="${this.escapeHtml(chain)}" title="${disabled ? '参考脚本跳过 TRD/TRG' : '点击切换'}">${this.escapeHtml(chain)}</span>`;
                    }).join('')
                    : '<span class="sh-chip">No chains detected</span>';
            }

            const sampleSelect = document.getElementById('scriptHubPgenSampleCol');
            if (sampleSelect) {
                const columns = Array.isArray(data.profile_columns) ? data.profile_columns : [];
                sampleSelect.innerHTML = columns.length
                    ? columns.map(col => `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`).join('')
                    : '<option value="sample">sample</option>';
                const sampleCandidate = (data.sample_column_candidates || [])[0] || 'sample';
                if (Array.from(sampleSelect.options).some(option => option.value === sampleCandidate)) {
                    sampleSelect.value = sampleCandidate;
                }
            }

            const depBox = document.getElementById('scriptHubPgenDependency');
            if (depBox) {
                const sonnia = data.sonnia || {};
                depBox.className = `alert mb-0 ${sonnia.available ? 'alert-success' : 'alert-warning'}`;
                depBox.innerHTML = sonnia.available
                    ? '<i class="bi bi-check-circle me-1"></i>SoNNia 环境可用，可以运行 Pgen 分析。'
                    : `<i class="bi bi-exclamation-triangle me-1"></i>${this.escapeHtml(sonnia.message || 'SoNNia 环境不可用，运行前需安装依赖。')}`;
                depBox.style.display = '';
            }

            this.showSourceFeedback(`Pgen 检测完成。发现 ${data.chain_count} 条链，${data.sample_count} 个样本。`, 'success');
            this.setInspectSummary(`Pgen: ${(data.chains || []).join(', ')} — ${data.sample_count} 个样本`, data?.sonnia?.available ? 'success' : 'warning');
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.setInspectSummary(error.message || 'Pgen analysis inspection failed', 'danger');
            this.showSourceFeedback(error.message || 'Pgen analysis inspection failed.', 'danger');
            this.showError(error.message || 'Pgen analysis inspection failed');
        } finally {
            this.hideLoading();
        }
    },

    _getSelectedPgenChains() {
        const chips = document.querySelectorAll('#scriptHubPgenChains .sh-chip-selected[data-pgen-chain]');
        return Array.from(chips).map(c => c.dataset.pgenChain || '').filter(Boolean);
    },

    async inspectUmap(loadingText = 'Scanning datapoint...') {
        const filePath = this._resolveProfilePath();
        if (!filePath) {
            this.showSourceFeedback('请先提供 datapoint 路径。', 'warning');
            this.showError('请先提供 datapoint 路径');
            return;
        }
        this.setUiState('inspecting');
        this.showSourceFeedback('正在检测 UMAP datapoint...', 'secondary');
        this.showLoading(loadingText || '扫描 datapoint...', '检测 UMAP');
        try {
            const body = { datapoint_path: filePath, project_id: this.getActiveProjectId() || null };
            const response = await fetch('/api/script-hub/umap/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || 'UMAP 检测失败');
            this.inspectData = data;
            this.result = null;
            this.setUiState('inspected');

            document.getElementById('scriptHubDatapointPath').value = data.datapoint_path || filePath;
            this._populateParamRangeSelects(data.columns || [], data.suggested_param_begin, data.suggested_param_over);

            this.showSourceFeedback(`UMAP 检测完成。发现 ${data.column_count} 列。`, 'success');
            this.setInspectSummary(`Datapoint: ${data.datapoint_path} — ${data.column_count} columns`, 'success');
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.showError(error.message || 'UMAP inspection failed');
        } finally {
            this.hideLoading();
        }
    },

    // ---- Shared utilities (used by multiple inspect methods) ----

    _resolveDatapointPath() {
        return this.selectedDatapointPath
            || document.getElementById('scriptHubDatapointPath')?.value?.trim()
            || document.getElementById('scriptHubBpDatapointPath')?.value?.trim()
            || '';
    },

    _populateParamRangeSelects(columns, selectedBegin = '', selectedOver = '') {
        const safeCols = Array.isArray(columns) ? columns : [];
        const paramBegin = document.getElementById('scriptHubParamBegin');
        const paramOver = document.getElementById('scriptHubParamOver');
        [paramBegin, paramOver].forEach(select => {
            if (select) {
                select.innerHTML = '<option value="">-- 请选择 --</option>' + safeCols.map(col =>
                    `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`
                ).join('');
            }
        });
        if (paramBegin && selectedBegin && safeCols.includes(selectedBegin)) paramBegin.value = selectedBegin;
        if (paramOver && selectedOver && safeCols.includes(selectedOver)) paramOver.value = selectedOver;
    },

    _populateProfileControls(data) {
        const columns = Array.isArray(data?.columns) ? data.columns : [];
        if (!columns.length) return;
        const groupBegin = document.getElementById('scriptHubProfileGroupBegin');
        const groupOver = document.getElementById('scriptHubProfileGroupOver');
        [groupBegin, groupOver].forEach((select) => {
            if (!select) return;
            select.innerHTML = '<option value="">-- 请选择 --</option>' + columns.map((col) =>
                `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`
            ).join('');
        });
        if (groupBegin && data?.suggested_grouping_begin && columns.includes(data.suggested_grouping_begin)) {
            groupBegin.value = data.suggested_grouping_begin;
        }
        if (groupOver && data?.suggested_grouping_over && columns.includes(data.suggested_grouping_over)) {
            groupOver.value = data.suggested_grouping_over;
        }

        this._populateParamRangeSelects(columns, data?.suggested_param_begin || '', data?.suggested_param_over || '');

        const groupFieldsSelect = document.getElementById('scriptHubProfileGroupFields');
        if (groupFieldsSelect) {
            groupFieldsSelect.innerHTML = columns.map((col) =>
                `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`
            ).join('');
            const start = columns.indexOf(data?.suggested_grouping_begin || '');
            const end = columns.indexOf(data?.suggested_grouping_over || '');
            Array.from(groupFieldsSelect.options).forEach((option, index) => {
                option.selected = start >= 0 && end >= start
                    ? index >= start && index <= end
                    : index === 0;
            });
            this.detectGroupValuesForAll();
        }

        const pepGroupFieldsSelect = document.getElementById('scriptHubPepGroupFields');
        if (pepGroupFieldsSelect) {
            const previousSelection = this.shouldPreserveField('scriptHubPepGroupFields')
                ? new Set(this.getSelectedMultiValues('scriptHubPepGroupFields'))
                : new Set();
            const suggestedGroupFields = Array.isArray(data?.group_fields) && data.group_fields.length
                ? data.group_fields
                : columns.filter(col => {
                    const lowered = String(col || '').trim().toLowerCase();
                    return !['sample', 'sample_id', 'sample_name'].includes(lowered);
                });
            pepGroupFieldsSelect.innerHTML = suggestedGroupFields.map((col) =>
                `<option value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</option>`
            ).join('');
            Array.from(pepGroupFieldsSelect.options).forEach((option) => {
                option.selected = previousSelection.has(option.value);
            });
            this.renderPepGroupFieldList();
            this.updatePepGroupValuePreview();
        }
    },

    async _loadProfileColumns(profilePath, { showFeedback = false } = {}) {
        const filePath = String(profilePath || '').trim();
        if (!filePath) return null;
        const response = await fetch('/api/script-hub/profile/columns', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_path: filePath }),
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.message || '读取 Profile 列失败');
        this.selectedDatapointPath = filePath;
        this.selectedDatapointPaths = [filePath];
        this.dataSelection.profilePath = filePath;
        this.dataSelection.profileType = 'file';
        this.ensureControlValue('scriptHubDatapointPath', filePath);
        this.ensureControlValue('scriptHubBpDatapointPath', filePath);
        this.ensureControlValue('scriptHubPepProfilePath', filePath);
        this.ensureControlValue('scriptHubProfilePath', filePath);
        this._populateProfileControls(data);
        if (showFeedback) {
            this.showSourceFeedback(`已读取 Profile 字段：${data.column_count || 0} 列。`, 'success');
        }
        return data;
    },

    async ensureProfileControlsReady() {
        const profilePath = this._resolveProfilePath();
        if (!profilePath) return;
        const paramBegin = document.getElementById('scriptHubParamBegin');
        const pepGroupFields = document.getElementById('scriptHubPepGroupFields');
        const hasParamOptions = Array.from(paramBegin?.options || []).some(option => option.value);
        const hasPepGroupOptions = Array.from(pepGroupFields?.options || []).some(option => option.value);
        if (hasParamOptions && (this.activeModule !== 'pep-analysis' || hasPepGroupOptions)) return;

        if (Array.isArray(this.inspectData?.columns) && this.inspectData.columns.length) {
            this._populateProfileControls(this.inspectData);
            return;
        }
        try {
            await this._loadProfileColumns(profilePath);
        } catch (error) {
            console.warn('ensureProfileControlsReady failed:', error);
            if (this.activeModule === 'pep-analysis') {
                this.renderPepGroupValuePreview([], { message: error.message || '读取 Profile 字段失败' });
            }
        }
    },

    async onPepProfileChange() {
        const profilePath = document.getElementById('scriptHubPepProfilePath')?.value?.trim()
            || this._resolveProfilePath();
        if (!profilePath) {
            this.renderPepGroupFieldList();
            this.renderPepGroupValuePreview([], { message: '请先选择 Profile 文件' });
            return;
        }
        try {
            await this._loadProfileColumns(profilePath, { showFeedback: true });
        } catch (error) {
            this.renderPepGroupValuePreview([], { message: error.message || '读取 Profile 字段失败' });
            this.showSourceFeedback(error.message || '读取 Profile 字段失败', 'danger');
        }
    },

    // ---- Volcano inspection ----
    async inspectVolcano(explicitBasePath = '', loadingText = '扫描 VJ usage 数据...') {
        const projectId = this.getActiveProjectId();
        const dataDir = explicitBasePath
            || document.getElementById('scriptHubVolcanoDataDir')?.value?.trim()
            || '';
        if (!dataDir && !projectId) {
            this.showSourceFeedback('请先提供 VJ Usage 数据目录，或从上方缓存数据源中选择。', 'warning');
            return;
        }
        this.setUiState('inspecting');
        this.showSourceFeedback('正在检测火山图数据...', 'secondary');
        this.showLoading(loadingText || '扫描火山图数据...', '检测火山图');
        try {
            const body = { data_dir: dataDir, project_id: projectId || null };
            const response = await fetch('/api/script-hub/volcano/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '火山图检测失败');
            this.inspectData = data;
            this.result = null;
            this.setUiState('inspected');
            document.getElementById('scriptHubVolcanoDataDir').value = data.data_dir || dataDir;
            this.showSourceFeedback(`火山图检测完成。发现 ${data.file_count || 0} 个文件。`, 'success');
            this.setInspectSummary(`目录: ${data.data_dir || dataDir} — ${data.file_count || 0} 个文件`, 'success');
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.showError(error.message || '火山图检测失败');
            this.showSourceFeedback(error.message || '火山图检测失败。', 'danger');
        } finally {
            this.hideLoading();
        }
    },

    // ---- UMAPin inspection ----
    async inspectUmapin(explicitBasePath = '', loadingText = '扫描数据文件...') {
        const projectId = this.getActiveProjectId();
        const dataPath = explicitBasePath
            || document.getElementById('scriptHubUmapinDataPath')?.value?.trim()
            || '';
        if (!dataPath && !projectId) {
            this.showSourceFeedback('请先提供 UMAPin 数据文件路径，或从上方缓存数据源中选择。', 'warning');
            return;
        }
        this.setUiState('inspecting');
        this.showSourceFeedback('正在检测 UMAPin 数据...', 'secondary');
        this.showLoading(loadingText || '扫描 UMAPPin 数据...', '检测 UMAPin');
        try {
            const body = { data_path: dataPath, project_id: projectId || null };
            const response = await fetch('/api/script-hub/umapin/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || 'UMAPin 检测失败');
            this.inspectData = data;
            this.result = null;
            this.setUiState('inspected');
            document.getElementById('scriptHubUmapinDataPath').value = data.data_path || dataPath;
            if (data.category_col) {
                document.getElementById('scriptHubUmapinCategoryCol').value = data.category_col;
            }
            this._populateParamRangeSelects(data.columns || [], data.suggested_param_begin, data.suggested_param_over);
            this.showSourceFeedback(`UMAPin 检测完成。发现 ${data.column_count || 0} 列。`, 'success');
            this.setInspectSummary(`数据: ${data.data_path || dataPath} — ${data.column_count || 0} 列`, 'success');
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.showError(error.message || 'UMAPin 检测失败');
            this.showSourceFeedback(error.message || 'UMAPin 检测失败。', 'danger');
        } finally {
            this.hideLoading();
        }
    },

    syncMlFeatureMode() {
        const mode = document.getElementById('scriptHubMlMode')?.value || 'profile';
        const profilePathBlock = document.getElementById('scriptHubMlProfilePathBlock');
        const paramBeginBlock = document.getElementById('scriptHubMlParamBeginBlock');
        const paramOverBlock = document.getElementById('scriptHubMlParamOverBlock');
        const showProfileConfig = mode === 'profile';
        if (profilePathBlock) profilePathBlock.style.display = showProfileConfig ? '' : 'none';
        if (paramBeginBlock) paramBeginBlock.style.display = '';
        if (paramOverBlock) paramOverBlock.style.display = '';
        this.populateMlParamRangeForMode(mode);
    },

    populateMlParamRangeForMode(mode = null) {
        const activeMode = mode || document.getElementById('scriptHubMlMode')?.value || 'profile';
        if (activeMode === 'vj-usage') {
            const usageOptions = this.mlUsageFeatureCandidates.map((item) => ({
                value: item.value || '',
                label: `${item.source || 'usage'} | ${item.label || item.value || ''}`,
            })).filter((item) => item.value);
            this.populateLabeledFieldSelect('scriptHubMlParamBegin', usageOptions, usageOptions[0]?.value || '');
            this.populateLabeledFieldSelect('scriptHubMlParamOver', usageOptions, usageOptions[usageOptions.length - 1]?.value || '');
            return;
        }
        const columns = Array.isArray(this.inspectData?.columns) ? this.inspectData.columns : [];
        this.populateFieldSelect('scriptHubMlParamBegin', columns, this.inspectData?.suggested_param_begin || '');
        this.populateFieldSelect('scriptHubMlParamOver', columns, this.inspectData?.suggested_param_over || '');
    },

    populateLabeledFieldSelect(selectId, options, selectedValue) {
        const select = document.getElementById(selectId);
        if (!select) return;
        const safeOptions = Array.isArray(options) ? options : [];
        select.innerHTML = safeOptions.length
            ? safeOptions.map((item) =>
                `<option value="${this.escapeHtml(item.value)}">${this.escapeHtml(item.label || item.value)}</option>`
            ).join('')
            : '<option value="">-- 无可选特征 --</option>';
        if (selectedValue && safeOptions.some((item) => item.value === selectedValue)) {
            select.value = selectedValue;
        }
    },

    // ---- Machine learning inspection ----
    async inspectMlAnalysis(loadingText = '检测机器学习输入...') {
        const projectId = this.getActiveProjectId();
        const profilePath = this._resolveProfilePath()
            || document.getElementById('scriptHubMlProfilePath')?.value?.trim()
            || '';
        const usagePath = document.getElementById('scriptHubMlUsagePath')?.value?.trim() || '';
        if (!profilePath && !projectId) {
            this.showSourceFeedback('请先选择 Profile 文件。', 'warning');
            return;
        }

        this.setUiState('inspecting');
        this.showSourceFeedback('正在检测机器学习输入...', 'secondary');
        this.showLoading(loadingText || '检测机器学习输入...', '检测 ML');
        try {
            const response = await fetch('/api/script-hub/ml-analysis/inspect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_id: projectId || null,
                    profile_path: profilePath,
                    usage_path: usagePath,
                    sample_col: document.getElementById('scriptHubMlSampleCol')?.value || '',
                    label_col: document.getElementById('scriptHubMlLabelCol')?.value || '',
                    filter_col: document.getElementById('scriptHubMlFilterCol')?.value || '',
                }),
            });
            const data = await response.json();
            if (!data.success) throw new Error(data.message || '机器学习检测失败');

            this.inspectData = data;
            this.result = null;
            this.setUiState('inspected');

            const columns = Array.isArray(data.columns) ? data.columns : [];
            const profileInput = document.getElementById('scriptHubMlProfilePath');
            const usageInput = document.getElementById('scriptHubMlUsagePath');
            if (profileInput) profileInput.value = data.profile_path || profilePath;
            if (usageInput && data.usage_path) usageInput.value = data.usage_path;

            this.populateFieldSelect('scriptHubMlSampleCol', columns, data.sample_col || 'Sample');
            this.populateFieldSelect('scriptHubMlLabelCol', columns, data.label_col || '');
            this.populateFieldSelect('scriptHubMlFilterCol', [''].concat(data.filter_candidates || columns), '');
            this.populateFieldSelect('scriptHubMlParamBegin', columns, data.suggested_param_begin || '');
            this.populateFieldSelect('scriptHubMlParamOver', columns, data.suggested_param_over || '');
            this._populateParamRangeSelects(columns, data.suggested_param_begin, data.suggested_param_over);
            this.mlUsageFeatureCandidates = Array.isArray(data.usage_feature_candidates)
                ? data.usage_feature_candidates
                : [];
            this.syncMlFeatureMode();

            document.getElementById('scriptHubColumnCount').textContent = columns.length;
            document.getElementById('scriptHubColumnChips').innerHTML = columns.length
                ? columns.slice(0, 80).map((col) => `<span class="sh-chip">${this.escapeHtml(col)}</span>`).join('')
                : '<span class="sh-chip">No columns detected</span>';

            this.showSourceFeedback(`机器学习检测完成。Profile 共 ${columns.length} 列。`, 'success');
            this.setInspectSummary(`Profile: ${data.profile_path || profilePath} — ${columns.length} columns`, 'success');
        } catch (error) {
            this.setUiState(this.inspectData ? 'inspected' : 'idle');
            this.showError(error.message || '机器学习检测失败');
            this.showSourceFeedback(error.message || '机器学习检测失败。', 'danger');
        } finally {
            this.hideLoading();
        }
    },


    _getSelectedGroupFields() {
        const select = document.getElementById('scriptHubProfileGroupFields');
        const selectedFromSelect = Array.from(select?.selectedOptions || []).map(option => option.value).filter(Boolean);
        if (selectedFromSelect.length) return selectedFromSelect;
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
        const projectProfile = this.getActiveProjectId() ? this._resolveProfilePath() : '';
        if (projectProfile) return projectProfile;
        const toggle = document.getElementById('scriptHubTcSameDirToggle');
        if (toggle && toggle.checked) {
            return document.getElementById('scriptHubTcPepDataPath')?.value?.trim() || '';
        }
        return document.getElementById('scriptHubTcDatapointPath')?.value?.trim() || '';
    },

    async inspectTopClone(loadingText = 'Scanning pep_data...') {
        let pepDataPath = this._resolvePrimaryPepPath()
            || document.getElementById('scriptHubTcPepDataPath')?.value?.trim()
            || '';
        let datapointPath = this._resolveTcDatapointPath();

        if (!pepDataPath) {
            pepDataPath = document.getElementById('scriptHubBasePath')?.value?.trim() || '';
            if (pepDataPath) {
                document.getElementById('scriptHubTcPepDataPath').value = pepDataPath;
            }
        }
        if (!datapointPath) {
            datapointPath = this._resolveProfilePath();
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
            const body = {
                pep_data_path: pepDataPath,
                datapoint_path: datapointPath,
                project_id: this.getActiveProjectId() || null,
            };
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

            this._populateParamRangeSelects(columns);

            const bpChips = document.getElementById('scriptHubBoxplotGroupChips');
            if (bpChips) {
                bpChips.innerHTML = columns.map((col) =>
                    `<span class="sh-chip sh-chip-selectable" data-value="${this.escapeHtml(col)}">${this.escapeHtml(col)}</span>`
                ).join('');
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

    async inspectProfile(explicitBasePath = '', loadingText = 'Scanning for Profile files...', { skipScroll = false } = {}) {
        const datapointPath = this._resolveProfilePath();
        const basePath = explicitBasePath
            || datapointPath
            || document.getElementById('scriptHubBasePath')?.value?.trim()
            || '';

        if (!basePath) {
            this.showSourceFeedback('请先选择 Profile 文件。', 'warning');
            this.showError('请先选择 Profile 文件');
            return;
        }

        this.setUiState('inspecting');
        this.showSourceFeedback('正在检测 Profile 文件...', 'secondary');
        this.showLoading(loadingText || 'Scanning for Profile files...', 'Inspect Profile assets');
        try {
            const body = {
                base_path: basePath,
                datapoint_path: datapointPath || basePath,
                project_id: this.getActiveProjectId() || null,
            };

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
            const visibleFileSelect = document.getElementById('scriptHubBpDatapointPath');
            const candidates = Array.isArray(data.file_candidates) ? data.file_candidates : [];
            [fileSelect, visibleFileSelect].forEach((select) => {
                if (!select) return;
                select.innerHTML = candidates.length
                    ? candidates.map((f) => {
                        const parts = f.replace(/\\/g, '/').split('/');
                        const basename = parts[parts.length - 1] || f;
                        return `<option value="${this.escapeHtml(f)}">${this.escapeHtml(basename)}</option>`;
                    }).join('')
                    : '<option value="">No CSV/TSV files found</option>';
                if (data.datapoint_path) select.value = data.datapoint_path;
            });
            this.selectedDatapointPath = data.datapoint_path || datapointPath || '';
            this.selectedDatapointPaths = this.selectedDatapointPath ? [this.selectedDatapointPath] : [];

            this.showSourceFeedback(
                `Profile inspection completed. Detected ${data.column_count || 0} columns.`,
                'success'
            );
            this.setInspectSummary(`Datapoint: ${data.datapoint_path} — ${data.column_count} columns`, 'success');

            const summaryGridEl = document.getElementById('scriptHubSummaryGrid');
            if (summaryGridEl) {
                summaryGridEl.innerHTML = `
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
            this.renderDataPreview(
                columns,
                data.preview_rows || [],
                `Profile 示例文件：${data.datapoint_path || '-' }。显示前 5 行，可横向滚动查看列。`
            );

            this._populateProfileControls(data);

            this.setText('scriptHubProfileGroupSuggestion',
                `${data.suggested_grouping_begin || '-'} → ${data.suggested_grouping_over || '-'}`);
            this.setText('scriptHubProfileParamSuggestion',
                `${data.suggested_param_begin || '-'} → ${data.suggested_param_over || '-'}`);
            document.getElementById('scriptHubProfileSuggestions')?.classList.remove('sh-hidden');

            document.getElementById('scriptHubResultLog').textContent = '等待结果。';
            document.getElementById('scriptHubResultSummary').textContent = 'Profile analysis completed.';
            document.getElementById('scriptHubResultMeta').textContent = '任务完成后在这里查看 Profile 结果、PNGs 和 p-value CSVs。';

            if (!skipScroll) {
                window.setTimeout(() => {
                    document.getElementById('scriptHubConfigStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }, 80);
            }
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
        const filePath = document.getElementById('scriptHubDatapointPath')?.value?.trim()
            || document.getElementById('scriptHubBpDatapointPath')?.value?.trim()
            || this._resolveProfilePath();
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
            this._populateProfileControls(data);

            document.getElementById('scriptHubColumnCount').textContent = columns.length;
            document.getElementById('scriptHubColumnChips').innerHTML = columns.length
                ? columns.map((col) => `<span class="sh-chip">${this.escapeHtml(col)}</span>`).join('')
                : '<span class="sh-chip">No columns detected</span>';
            this.renderDataPreview(
                columns,
                data.preview_rows || [],
                `Profile 示例文件：${filePath}. 显示前 5 行，可横向滚动查看列。`
            );
            this.setText('scriptHubProfileGroupSuggestion',
                `${data.suggested_grouping_begin || '-'} → ${data.suggested_grouping_over || '-'}`);
            this.setText('scriptHubProfileParamSuggestion',
                `${data.suggested_param_begin || '-'} → ${data.suggested_param_over || '-'}`);
            this.setInspectSummary(`Datapoint: ${filePath} — ${columns.length} columns`, 'success');
            this.showSourceFeedback(`Loaded ${columns.length} columns from the selected file.`, 'success');
        } catch (error) {
            this.showError(error.message || 'Failed to read file columns');
            this.showSourceFeedback(error.message || 'Failed to read columns.', 'danger');
        }
    },

    collectRunPayload() {
        const projectId = this.getActiveProjectId();
        if (this.activeModule === 'profile') {
            const datapointPath = this._resolveProfilePath();
            if (!datapointPath || !this.inspectData) {
                throw new Error('请先检测 Profile 文件再运行 Profile 分析');
            }
            const groupToggle = document.getElementById('scriptHubBoxplotGroupToggle');
            const useGrouping = groupToggle ? groupToggle.checked : true;
            const selectedGroupFields = useGrouping ? this._getSelectedGroupFields() : [];
            const groupOrder = useGrouping ? this._getGroupOrderFromChips() : '';
            return {
                module: 'profile',
                datapoint_path: datapointPath,
                grouping_begin: '',
                grouping_over: '',
                grouptype_fields: selectedGroupFields,
                group_order: useGrouping ? groupOrder : '',
                param_begin: document.getElementById('scriptHubParamBegin')?.value || '',
                param_over: document.getElementById('scriptHubParamOver')?.value || '',
                pvalue_threshold: parseFloat(document.getElementById('scriptHubPvalueThreshold')?.value || '0.05'),
                output_name: document.getElementById('scriptHubOutputName')?.value?.trim() || null,
                project_id: projectId || null,
            };
        }

        if (this.activeModule === 'volcano') {
            const dataDir = document.getElementById('scriptHubVolcanoDataDir')?.value?.trim() || '';
            if (!dataDir && !projectId) throw new Error('请先检测数据目录');
            return {
                module: 'volcano',
                data_dir: dataDir,
                project_id: projectId || null,
                pvalue_threshold: parseFloat(document.getElementById('scriptHubVolcanoPvalueThreshold')?.value || '0.05'),
            };
        }

        if (this.activeModule === 'umapin') {
            const dataPath = document.getElementById('scriptHubUmapinDataPath')?.value?.trim() || '';
            if ((!dataPath && !projectId) || !this.inspectData) throw new Error('请先检测数据文件');
            return {
                module: 'umapin',
                data_path: dataPath,
                project_id: projectId || null,
                param_begin: document.getElementById('scriptHubParamBegin')?.value || '',
                param_over: document.getElementById('scriptHubParamOver')?.value || '',
                category_col: document.getElementById('scriptHubUmapinCategoryCol')?.value || 'Category',
                n_neighbors: parseInt(document.getElementById('scriptHubUmapinNNeighbors')?.value || '6'),
                min_dist: parseFloat(document.getElementById('scriptHubUmapinMinDist')?.value || '0.01'),
                do_fdr: document.getElementById('scriptHubUmapinFdrToggle')?.checked || false,
            };
        }

        if (this.activeModule === 'umap') {
            const datapointPath = this._resolveProfilePath();
            if (!datapointPath || !this.inspectData) {
                throw new Error('Please inspect a datapoint file before running UMAP');
            }
            return {
                module: 'umap',
                datapoint_path: datapointPath,
                classification_begin: this.inspectData?.suggested_classification_begin || '',
                classification_over: this.inspectData?.suggested_classification_over || '',
                param_begin: document.getElementById('scriptHubParamBegin')?.value || '',
                param_over: document.getElementById('scriptHubParamOver')?.value || '',
                pvalue_threshold: parseFloat(document.getElementById('scriptHubPvalueThreshold')?.value || '0.05'),
                n_neighbors: parseInt(document.getElementById('scriptHubUmapNNeighbors')?.value || '6', 10),
                min_dist: parseFloat(document.getElementById('scriptHubUmapMinDist')?.value || '0.01'),
                output_name: document.getElementById('scriptHubOutputName')?.value?.trim() || null,
                project_id: projectId || null,
            };
        }

        if (this.activeModule === 'ml-analysis') {
            const profilePath = this._resolveProfilePath()
                || document.getElementById('scriptHubMlProfilePath')?.value?.trim()
                || '';
            if (!profilePath || !this.inspectData) {
                throw new Error('请先检测 Profile 文件再运行机器学习分析');
            }
            const mode = document.getElementById('scriptHubMlMode')?.value || 'profile';
            const usagePath = document.getElementById('scriptHubMlUsagePath')?.value?.trim() || '';
            if (mode === 'vj-usage' && !usagePath) {
                throw new Error('请先选择 VJ usage 缓存数据');
            }
            const paramBegin = document.getElementById('scriptHubMlParamBegin')?.value || '';
            const paramOver = document.getElementById('scriptHubMlParamOver')?.value || '';
            if (mode === 'profile' && (!paramBegin || !paramOver)) {
                throw new Error('请先选择 Profile 参数起始列和结束列');
            }
            if (mode === 'vj-usage' && (!paramBegin || !paramOver)) {
                throw new Error('请先选择 VJ usage 参数起始列和结束列');
            }
            return {
                module: 'ml-analysis',
                project_id: projectId || null,
                profile_path: profilePath,
                mode,
                usage_path: usagePath,
                sample_col: document.getElementById('scriptHubMlSampleCol')?.value || 'Sample',
                label_col: document.getElementById('scriptHubMlLabelCol')?.value || '',
                filter_col: document.getElementById('scriptHubMlFilterCol')?.value || '',
                filter_value: document.getElementById('scriptHubMlFilterValue')?.value?.trim() || '',
                param_begin: paramBegin,
                param_over: paramOver,
                custom_threshold: parseFloat(document.getElementById('scriptHubMlThreshold')?.value || '0.003'),
                cv_splits: parseInt(document.getElementById('scriptHubMlCvSplits')?.value || '3', 10),
                roc_cv_splits: parseInt(document.getElementById('scriptHubMlRocCvSplits')?.value || '7', 10),
                output_name: document.getElementById('scriptHubOutputName')?.value?.trim() || null,
            };
        }

        if (this.activeModule === 'pgen-analysis') {
            const pepDir = this._resolvePrimaryPepPath()
                || document.getElementById('scriptHubPgenDataDir')?.value?.trim()
                || '';
            const profilePath = this._resolveProfilePath()
                || document.getElementById('scriptHubPgenProfilePath')?.value?.trim()
                || '';
            if (!pepDir || !profilePath || !this.inspectData) {
                throw new Error('请先检测 Pgen 输入');
            }
            const chains = this._pgenSelectedChains || this._getSelectedPgenChains();
            if (!chains.length) throw new Error('请至少选择一条 Pgen 可运行链');
            return {
                module: 'pgen-analysis',
                pep_data_dir: pepDir,
                profile_path: profilePath,
                selected_chains: chains,
                sample_col: document.getElementById('scriptHubPgenSampleCol')?.value || 'sample',
                species: document.getElementById('scriptHubPgenSpecies')?.value || 'human',
                output_name: document.getElementById('scriptHubOutputName')?.value?.trim() || null,
                project_id: projectId || null,
            };
        }

        if (this.activeModule === 'topclone') {
            const pepDataPath = this._resolvePrimaryPepPath()
                || document.getElementById('scriptHubTcPepDataPath')?.value?.trim()
                || '';
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
                project_id: projectId || null,
            };
        }

        if (this.activeModule === 'pep-analysis') {
            const pepDir = this._resolvePrimaryPepPath()
                || document.getElementById('scriptHubPepDataDir')?.value?.trim()
                || '';
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
                optional_steps: this.getSelectedPepOptionalSteps(),
            };
        }

        const allPepPaths = this._resolvePepPaths();
        const basePath = this._resolvePrimaryPepPath();
        const allDpPaths = this.selectedDatapointPaths;
        const datapointPath = allDpPaths[0] || document.getElementById('scriptHubDatapointPath')?.value?.trim() || '';

        if (!basePath && allPepPaths.length === 0) {
            throw new Error('请先选择数据');
        }
        return {
            module: 'db-alignment',
            base_path: basePath || null,
            output_name: document.getElementById('scriptHubOutputName')?.value?.trim() || null,
            profile_path: this._resolveProfilePath() || null,
            project_id: projectId || null,
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
            const isBoxPlot = module === 'boxplot' || module === 'profile';
            const isTopClone = module === 'topclone';
            const isPep = module === 'pep-analysis';
            const isPgen = module === 'pgen-analysis';
            const isUmap = module === 'umap';
            const isVolcano = module === 'volcano';
            const isUmapinModule = module === 'umapin';
            const isProfile = module === 'profile';
            const isMl = module === 'ml-analysis';
            const endpoint = isUmapinModule ? '/api/script-hub/umapin/run'
                : (isVolcano ? '/api/script-hub/volcano/run'
                : (isUmap ? '/api/script-hub/umap/run'
                : (isTopClone ? '/api/script-hub/topclone/run'
                : (isPep ? '/api/script-hub/pep-analysis/run'
                : (isPgen ? '/api/script-hub/pgen-analysis/run'
                : (isMl ? '/api/script-hub/ml-analysis/run'
                : (isProfile ? '/api/script-hub/profile/run'
                : (isBoxPlot ? '/api/script-hub/profile/run'
                : '/api/script-hub/db-alignment/run'))))))));
            const label = isUmapinModule ? 'UMAPin' : (isVolcano ? '火山图' : (isUmap ? 'UMAP' : (isTopClone ? 'TopClone' : (isPep ? 'PEP共享' : (isPgen ? 'Pgen' : (isMl ? '机器学习' : (isProfile ? 'Profile分析' : (isBoxPlot ? 'Profile' : '数据库比对'))))))));

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

    syncResultActions(result) {
        const setButtonState = (id, url, fallbackTitle) => {
            const button = document.getElementById(id);
            if (!button) return;
            button.disabled = !url;
            button.title = url ? fallbackTitle : '当前结果未生成该文件';
        };

        setButtonState('scriptHubOpenViewerBtn', result?.viewer_url, '打开 Viewer');
        setButtonState('scriptHubOpenZipBtn', result?.zip_url, '下载 ZIP');
        const metadataBtn = document.getElementById('scriptHubOpenMetadataBtn');
        if (metadataBtn) {
            metadataBtn.style.display = 'none';
            metadataBtn.disabled = true;
            metadataBtn.onclick = null;
        }

        const saveBtn = document.getElementById('scriptHubSaveDbResultBtn');
        if (saveBtn) {
            saveBtn.style.display = 'none';
            saveBtn.onclick = null;
        }
    },

    renderResultArtifacts(result) {
        const container = document.getElementById('scriptHubResultArtifacts');
        if (!container) return;
        container.innerHTML = '';
    },

    renderResult(result) {
        if (!result) return;

        this.setUiState('completed');

        const summary = this._getResultSummary(result);
        const meta = this._getResultMeta(result);
        const log = JSON.stringify({
            job_id: result.job_id,
            output_base: result.output_base,
            viewer_url: result.viewer_url || '',
            metadata_url: result.metadata_url || '',
            zip_url: result.zip_url || '',
        }, null, 2);

        this.setText('scriptHubResultSummary', summary);
        this.setText('scriptHubResultMeta', meta);
        this.setText('scriptHubResultLog', log);

        this._renderUnifiedResultActions(result);

        window.setTimeout(function() {
            document.getElementById('scriptHubResultStage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 80);
    },

    _getModuleLabel(module) {
        const labels = {
            'profile': 'Profile \u5206\u6790',
            'boxplot': '\u7bb1\u7ebf\u56fe\u5206\u6790',
            'db-alignment': '\u6570\u636e\u5e93\u6bd4\u5bf9',
            'pep-analysis': 'PEP \u5171\u4eab\u5206\u6790',
            'topclone': 'TopClone \u5206\u6790',
            'umap': 'UMAP \u964d\u7ef4\u5206\u6790',
            'volcano': '\u706b\u5c71\u56fe\u5206\u6790',
            'umapin': 'UMAPin \u964d\u7ef4',
            'ml-analysis': '\u673a\u5668\u5b66\u4e60\u5206\u6790',
            'pgen-analysis': 'Pgen \u5206\u6790',
        };
        return labels[module] || '\u5206\u6790';
    },

    _getResultSummary(result) {
        const m = result.metadata || {};
        const mod = result.module || '';
        if (mod === 'db-alignment') return '\u6570\u636e\u5e93\u6bd4\u5bf9\u5b8c\u6210\u3002\u5171 ' + (m.sample_count || 0) + ' \u4e2a\u6837\u672c\u3002';
        if (mod === 'pep-analysis') return 'PEP \u5171\u4eab\u5206\u6790\u5b8c\u6210\u3002' + (m.selected_chains || []).length + ' \u6761\u94fe\uff0c' + (m.group_fields || []).length + ' \u4e2a\u5206\u7ec4\u5b57\u6bb5\u3002';
        if (mod === 'pgen-analysis') return 'Pgen \u5206\u6790\u5b8c\u6210\u3002' + (m.sample_count ?? '-') + ' \u4e2a\u6837\u672c\uff0c' + (m.detail_file_count ?? '-') + ' \u4e2a\u660e\u7ec6\u6587\u4ef6\u3002';
        if (mod === 'profile' || mod === 'boxplot') {
            const cnt = m.plot_count || (result.png_urls?.length || 0);
            const sig = m.significant_plot_count || 0;
            return '\u7bb1\u7ebf\u56fe\u5206\u6790\u5b8c\u6210\u3002' + cnt + ' \u5f20\u56fe\uff08' + sig + ' \u663e\u8457\uff09\u3002';
        }
        if (mod === 'topclone') return 'TopClone \u5206\u6790\u5b8c\u6210\u3002' + (result.png_urls?.length || 0) + ' \u5f20\u7bb1\u7ebf\u56fe\u3002';
        if (mod === 'umap') return 'UMAP \u5206\u6790\u5b8c\u6210\u3002' + (result.png_urls?.length || 0) + ' \u5f20\u56fe\u3002';
        if (mod === 'volcano') return '\u706b\u5c71\u56fe\u5206\u6790\u5b8c\u6210\u3002';
        if (mod === 'umapin') return 'UMAPin \u964d\u7ef4\u5b8c\u6210\u3002';
        if (mod === 'ml-analysis') return '\u673a\u5668\u5b66\u4e60\u5206\u6790\u5b8c\u6210\u3002\u5e73\u5747 CV accuracy: ' + (m.mean_cv_accuracy ?? '-');
        return '\u5206\u6790\u5b8c\u6210\u3002';
    },

    _getResultMeta(result) {
        const m = result.metadata || {};
        const mod = result.module || '';
        if (mod === 'db-alignment') return '\u94fe\uff1a' + ((m.selected_chains || []).join(', ') || '-') + ' | Profile\uff1a' + (m.profile_path || '\u672a\u5408\u5e76');
        if (mod === 'pep-analysis') return '\u94fe\uff1a' + ((m.selected_chains || []).join(', ')) + ' | \u5206\u7ec4\uff1a' + ((m.group_fields || []).join(', '));
        if (mod === 'pgen-analysis') return 'Chains: ' + ((m.selected_chains || []).join(', ') || '-') + ' | Species: ' + (m.species || '-');
        if (mod === 'profile' || mod === 'boxplot') return 'P\u503c\u9608\u503c\uff1a' + (m.pvalue_threshold || 0.05) + ' | \u53c2\u6570\u8303\u56f4\uff1a' + (m.param_begin || '-') + ' \u2192 ' + (m.param_over || '-');
        if (mod === 'topclone') return 'Mode: ' + (m.mode || 'trace') + ' | Chains: ' + ((m.chains || []).join(', '));
        if (mod === 'umap') return 'n_neighbors: ' + (m.n_neighbors || 6) + ' | min_dist: ' + (m.min_dist || 0.01);
        if (mod === 'volcano') return 'P\u503c\u9608\u503c: ' + (m.pvalue_threshold || 0.05) + ' | \u6587\u4ef6\u6570: ' + (m.file_count || 0);
        if (mod === 'umapin') return '\u5206\u7c7b\u5217: ' + (m.category_col || '-') + ' | FDR: ' + (m.do_fdr ? '\u662f' : '\u5426');
        if (mod === 'ml-analysis') return 'Mode: ' + (m.mode || '-') + ' | Label: ' + (m.label_col || '-') + ' | Selected features: ' + (m.selected_feature_number ?? '-');
        return '';
    },

    _renderUnifiedResultActions(result) {
        const viewerBtn = document.getElementById('scriptHubOpenViewerBtn');
        const zipBtn = document.getElementById('scriptHubOpenZipBtn');
        const metaBtn = document.getElementById('scriptHubOpenMetadataBtn');

        if (viewerBtn) {
            viewerBtn.style.display = result.viewer_url ? '' : 'none';
            viewerBtn.onclick = function() { if (result.viewer_url) window.open(result.viewer_url, '_blank', 'noopener'); };
        }
        if (zipBtn) {
            zipBtn.style.display = result.zip_url ? '' : 'none';
            zipBtn.onclick = function() { if (result.zip_url) { var a = document.createElement('a'); a.href = result.zip_url; a.download = ''; document.body.appendChild(a); a.click(); document.body.removeChild(a); } };
        }
        if (metaBtn) {
            metaBtn.style.display = 'none';
            metaBtn.disabled = true;
            metaBtn.onclick = null;
        }
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
        // Skip if this path is already registered as an asset (prevents duplicates)
        const existingId = assetType === 'profile'
            ? this._findProjectProfileAssetId(storagePath)
            : this._findProjectAssetId(assetType, storagePath);
        if (existingId) return;
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
