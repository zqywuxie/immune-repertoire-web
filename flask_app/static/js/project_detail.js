function formatDateTime(value) {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('zh-CN', { hour12: false });
}

function formatFileSize(bytes) {
    const size = Number(bytes || 0);
    if (!Number.isFinite(size) || size <= 0) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB'];
    let value = size;
    let unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
        value /= 1024;
        unitIndex += 1;
    }
    return `${value.toFixed(value >= 100 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

function showManagementToast(message, type = 'info') {
    let stack = document.querySelector('.mg-toast-stack');
    if (!stack) {
        stack = document.createElement('div');
        stack.className = 'mg-toast-stack';
        document.body.appendChild(stack);
    }
    const toast = document.createElement('div');
    toast.className = `mg-toast mg-toast-${type}`;
    toast.textContent = message;
    stack.appendChild(toast);
    window.setTimeout(() => toast.remove(), 3200);
}

const ProjectDetailPage = {
    projectId: '',
    projectData: null,
    selectedUploads: [],
    uploadModal: null,
    assetFilters: {
        query: '',
        type: '',
    },
    settingsSnapshot: null,

    init() {
        if (!window.PROJECT_DETAIL_CONTEXT) return;
        
        this.projectId = window.PROJECT_DETAIL_CONTEXT.projectId;
        
        // Initialize Bootstrap modal
        const modalElement = document.getElementById('assetUploadModal');
        if (modalElement) {
            this.uploadModal = new bootstrap.Modal(modalElement);
        }
        
        // Initialize tab switching
        this.initTabs();
        
        // Event listeners
        document.getElementById('refreshProjectDetailBtn')?.addEventListener('click', () => this.loadProject());
        document.getElementById('refreshAssetsBtn')?.addEventListener('click', () => this.loadProject());
        document.getElementById('refreshSamplesBtn')?.addEventListener('click', () => this.loadProject());
        document.getElementById('uploadAssetBtn')?.addEventListener('click', () => this.showUploadModal());
        document.getElementById('selectAssetFilesBtn')?.addEventListener('click', () => document.getElementById('assetFilesInput')?.click());
        document.getElementById('selectAssetFolderBtn')?.addEventListener('click', () => document.getElementById('assetFolderInput')?.click());
        document.getElementById('assetFilesInput')?.addEventListener('change', (event) => this.captureUploads(event.target.files, false));
        document.getElementById('assetFolderInput')?.addEventListener('change', (event) => this.captureUploads(event.target.files, true));
        document.getElementById('uploadAssetsBtn')?.addEventListener('click', () => this.uploadAssets());
        document.getElementById('addGroupRowBtn')?.addEventListener('click', () => this.appendGroupRow());
        document.getElementById('saveGroupSpecBtn')?.addEventListener('click', () => this.saveGroupSpec());
        document.getElementById('clearGroupSpecBtn')?.addEventListener('click', () => this.clearGroupSpecs());
        document.getElementById('assetSearchInput')?.addEventListener('input', (event) => {
            this.assetFilters.query = event.target.value.trim().toLowerCase();
            this.renderAssets(this.projectData?.assets || []);
        });
        document.getElementById('assetTypeFilter')?.addEventListener('change', (event) => {
            this.assetFilters.type = event.target.value;
            this.renderAssets(this.projectData?.assets || []);
        });
        document.getElementById('clearAssetFiltersBtn')?.addEventListener('click', () => this.clearAssetFilters());
        document.getElementById('resetProjectSettingsBtn')?.addEventListener('click', () => this.resetProjectSettingsForm());
        
        // Project settings form
        const settingsForm = document.getElementById('projectSettingsForm');
        if (settingsForm) {
            settingsForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.updateProjectSettings();
            });
            settingsForm.querySelectorAll('input, textarea, select').forEach(input => {
                input.addEventListener('input', () => this.updateSettingsDirtyState());
                input.addEventListener('change', () => this.updateSettingsDirtyState());
            });
        }
        
        // Analysis launch buttons
        document.querySelectorAll('[data-analysis-launch]').forEach(button => {
            button.addEventListener('click', () => this.launchAnalysis(button.dataset.analysisLaunch));
        });
        
        this.loadProject();
    },

    initTabs() {
        // Tab switching functionality
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const tabName = btn.dataset.tab;
                
                // Update button states
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                // Update content visibility
                document.querySelectorAll('.project-tab-panel').forEach(content => {
                    content.classList.remove('active');
                });
                const targetTab = document.getElementById(`${tabName}-tab`);
                if (targetTab) {
                    targetTab.classList.add('active');
                }
            });
        });
    },

    async loadProject() {
        const errorAlert = document.getElementById('projectDetailError');
        errorAlert?.classList.add('d-none');
        
        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(this.projectId)}`);
            const data = await response.json();
            
            if (!response.ok) throw new Error(data.message || '加载项目详情失败');
            
            this.projectData = data;
            this.renderProject();
        } catch (error) {
            if (errorAlert) {
                errorAlert.textContent = error.message || '加载项目详情失败';
                errorAlert.classList.remove('d-none');
            }
        }
    },

    renderProject() {
        const project = this.projectData;
        const counts = project.asset_counts || {};
        
        // Update basic info
        document.getElementById('projectTitle').textContent = project.name || '项目详情';
        document.getElementById('projectSubtitle').textContent = project.description || '项目尚未填写描述。';
        document.getElementById('projectInstitutionValue').textContent = project.institution || '-';
        document.getElementById('projectCooperationValue').textContent = project.cooperation_level || '-';
        
        // Update status badge
        const statusElement = document.getElementById('projectStatusValue');
        if (project.status === 'active') {
            statusElement.textContent = '活跃';
            statusElement.className = 'status-badge status-active';
        } else {
            statusElement.textContent = '未激活';
            statusElement.className = 'status-badge status-inactive';
        }
        
        document.getElementById('projectUpdatedAtValue').textContent = formatDateTime(project.updated_at || project.created_at);
        
        // Update overview statistics
        document.getElementById('overviewSampleCount').textContent = String(project.sample_count || 0);
        document.getElementById('overviewResultCount').textContent = String(project.result_count || 0);
        document.getElementById('overviewPepCount').textContent = String(counts.pep || 0);
        document.getElementById('overviewDatapointCount').textContent = String(counts.profile || 0);
        
        // Update asset statistics
        this.renderAssetStatistics(counts);
        
        // Update sample statistics
        this.renderSampleStatistics(counts);
        
        // Update project settings form
        this.updateProjectSettingsForm();
        this.updateAssetTypeFilter(project.assets || []);
        
        // Load detailed data
        this.renderAssets(project.assets || []);
        this.renderSamplesPreview(project.samples_preview || []);
        this.renderGroupSpecs(project.group_specs || []);
    },

    renderAssetStatistics(counts) {
        const container = document.getElementById('assetStatistics');
        if (!container) return;
        
        const totalSize = Object.values(counts).reduce((sum, count) => sum + (count || 0), 0);
        
        container.innerHTML = `
            <div class="summary-item">
                <div class="summary-value">${Object.keys(counts).length}</div>
                <div class="summary-label">资产类型</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">${totalSize}</div>
                <div class="summary-label">资产总数</div>
            </div>
        `;
    },

    renderSampleStatistics(counts) {
        const container = document.getElementById('sampleStatistics');
        if (!container) return;
        
        container.innerHTML = `
            <div class="summary-item">
                <div class="summary-value">${this.projectData.sample_count || 0}</div>
                <div class="summary-label">总样本数</div>
            </div>
            <div class="summary-item">
                <div class="summary-value">${this.projectData.result_count || 0}</div>
                <div class="summary-label">分析结果</div>
            </div>
        `;
    },

    updateProjectSettingsForm() {
        const project = this.projectData;
        document.getElementById('projectNameInput').value = project.name || '';
        document.getElementById('projectDescInput').value = project.description || '';
        document.getElementById('projectInstitutionInput').value = project.institution || '';
        document.getElementById('projectCooperationInput').value = project.cooperation_level || '';
        document.getElementById('projectStatusInput').value = project.status || 'active';
        document.getElementById('settingsProjectIdValue').textContent = this.projectId || '-';
        document.getElementById('settingsCreatedAtValue').textContent = formatDateTime(project.created_at);
        document.getElementById('settingsUpdatedAtValue').textContent = formatDateTime(project.updated_at || project.created_at);
        document.getElementById('projectNameInput')?.classList.remove('is-invalid');
        this.settingsSnapshot = this.collectProjectSettingsPayload();
        this.setSettingsDirty(false);
    },

    collectProjectSettingsPayload() {
        return {
            name: document.getElementById('projectNameInput')?.value.trim() || '',
            description: document.getElementById('projectDescInput')?.value || '',
            institution: document.getElementById('projectInstitutionInput')?.value || '',
            cooperation_level: document.getElementById('projectCooperationInput')?.value || '',
            status: document.getElementById('projectStatusInput')?.value || 'active',
        };
    },

    updateSettingsDirtyState() {
        const current = this.collectProjectSettingsPayload();
        const dirty = JSON.stringify(current) !== JSON.stringify(this.settingsSnapshot || {});
        this.setSettingsDirty(dirty);
        if (current.name) {
            document.getElementById('projectNameInput')?.classList.remove('is-invalid');
        }
    },

    setSettingsDirty(isDirty) {
        document.getElementById('settingsDirtyBadge')?.classList.toggle('d-none', !isDirty);
        const saveButton = document.getElementById('saveProjectSettingsBtn');
        const resetButton = document.getElementById('resetProjectSettingsBtn');
        if (saveButton) saveButton.disabled = !isDirty;
        if (resetButton) resetButton.disabled = !isDirty;
    },

    resetProjectSettingsForm() {
        if (!this.projectData) return;
        this.updateProjectSettingsForm();
        showManagementToast('已恢复为当前项目设置。', 'info');
    },

    async updateProjectSettings() {
        const payload = this.collectProjectSettingsPayload();
        const nameInput = document.getElementById('projectNameInput');
        if (!payload.name) {
            nameInput?.classList.add('is-invalid');
            nameInput?.focus();
            showManagementToast('项目名称不能为空。', 'info');
            return;
        }

        const saveButton = document.getElementById('saveProjectSettingsBtn');
        const originalLabel = saveButton?.innerHTML;
        if (saveButton) {
            saveButton.disabled = true;
            saveButton.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>保存中';
        }

        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(this.projectId)}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            });
            
            if (!response.ok) throw new Error('更新失败');
            
            this.settingsSnapshot = payload;
            this.setSettingsDirty(false);
            showManagementToast('项目设置已更新。', 'success');
            window.setTimeout(() => this.loadProject(), 600);
            
        } catch (error) {
            console.error('Error updating project settings:', error);
            showManagementToast(error.message || '项目设置更新失败。', 'danger');
            this.updateSettingsDirtyState();
        } finally {
            if (saveButton) {
                saveButton.innerHTML = originalLabel || '<i class="bi bi-check2-circle me-1"></i>保存设置';
            }
        }
    },

    getAssetTypeConfig(type) {
        const configs = {
            profile: { label: 'Profile Data', icon: 'bi-table', tone: 'blue' },
            pep: { label: 'Pep Files', icon: 'bi-filetype-csv', tone: 'green' },
            sample_summary: { label: 'Sample Summary', icon: 'bi-clipboard-data', tone: 'amber' },
            group_spec: { label: 'Group Spec', icon: 'bi-diagram-2', tone: 'gray' },
            processed_result: { label: 'Analysis Result', icon: 'bi-graph-up-arrow', tone: 'blue' },
            raw_archive: { label: 'Raw Archive', icon: 'bi-archive', tone: 'gray' },
            cached_usage: { label: 'Pep Usage Cache', icon: 'bi-database-check', tone: 'green' },
        };
        return configs[type] || { label: type || 'Unknown', icon: 'bi-file-earmark', tone: 'gray' };
    },

    getAssetRelativePath(asset) {
        const metadata = asset.metadata_json || asset.metadata || {};
        if (asset.asset_type === 'processed_result') {
            return metadata.output_base || metadata.report_path || asset.storage_path || '-';
        }
        return metadata.relative_path || metadata.report_path || asset.storage_path || '-';
    },

    getAssetSearchText(asset) {
        const metadata = asset.metadata_json || asset.metadata || {};
        const typeConfig = this.getAssetTypeConfig(asset.asset_type);
        return [
            asset.original_name,
            asset.asset_type,
            typeConfig.label,
            this.getAssetRelativePath(asset),
            metadata.analysis_type,
            metadata.analysis_signature,
            metadata.source,
            Array.isArray(metadata.chains) ? metadata.chains.join(' ') : '',
            Array.isArray(metadata.group_fields) ? metadata.group_fields.join(' ') : '',
        ].filter(Boolean).join(' ').toLowerCase();
    },

    updateAssetTypeFilter(assets) {
        const select = document.getElementById('assetTypeFilter');
        if (!select) return;

        const previous = select.value;
        const types = Array.from(new Set(assets.map(asset => asset.asset_type).filter(Boolean))).sort();
        select.innerHTML = '<option value="">全部类型</option>' + types.map(type => {
            const config = this.getAssetTypeConfig(type);
            return `<option value="${escapeHtml(type)}">${escapeHtml(config.label)}</option>`;
        }).join('');
        if (types.includes(previous)) {
            select.value = previous;
        } else {
            select.value = '';
            this.assetFilters.type = '';
        }
    },

    clearAssetFilters() {
        this.assetFilters = { query: '', type: '' };
        const searchInput = document.getElementById('assetSearchInput');
        const typeFilter = document.getElementById('assetTypeFilter');
        if (searchInput) searchInput.value = '';
        if (typeFilter) typeFilter.value = '';
        this.renderAssets(this.projectData?.assets || []);
    },

    getFilteredAssets(assets) {
        return assets.filter(asset => {
            const matchesType = !this.assetFilters.type || asset.asset_type === this.assetFilters.type;
            const matchesQuery = !this.assetFilters.query || this.getAssetSearchText(asset).includes(this.assetFilters.query);
            return matchesType && matchesQuery;
        });
    },

    renderAssetMetadata(asset) {
        const metadata = asset.metadata_json || asset.metadata || {};
        const chips = [];
        if (metadata.source) chips.push(`Source: ${metadata.source}`);
        if (asset.asset_type === 'cached_usage') {
            const chains = Array.isArray(metadata.chains) ? metadata.chains.join(', ') : '';
            const groups = Array.isArray(metadata.group_fields) ? metadata.group_fields.join(', ') : '';
            if (chains) chips.push(`Chains: ${chains}`);
            if (groups) chips.push(`Groups: ${groups}`);
        }
        if (asset.asset_type === 'processed_result') {
            if (metadata.analysis_type) chips.push(`Type: ${metadata.analysis_type}`);
            if (metadata.analysis_signature) chips.push(`Signature: ${String(metadata.analysis_signature).slice(0, 12)}`);
            const inputCount = Array.isArray(metadata.input_assets) ? metadata.input_assets.length : 0;
            if (inputCount) chips.push(`Inputs: ${inputCount}`);
        }
        if (!chips.length) return '';
        return `<div class="asset-meta-chips">${chips.map(chip => `<span>${escapeHtml(chip)}</span>`).join('')}</div>`;
    },

    renderAssetActions(asset) {
        const metadata = asset.metadata_json || asset.metadata || {};
        const openUrl = metadata.report_url || metadata.viewer_url || metadata.metadata_url || '';
        const zipUrl = metadata.zip_url || '';
        const canDirectDownload = (asset.asset_type !== 'processed_result' && asset.asset_type !== 'cached_usage')
            || (metadata.report_path && !String(metadata.report_path).startsWith('/api/'));
        const deleteButton = metadata.source === 'mongodb'
            ? ''
            : `<button class="btn btn-sm btn-outline-danger asset-icon-btn" data-asset-delete="${escapeHtml(asset.id)}" title="删除资产" aria-label="删除资产"><i class="bi bi-trash3"></i></button>`;

        return `
            <div class="asset-action-group">
                ${openUrl ? `<a class="btn btn-sm btn-outline-primary asset-icon-btn" href="${escapeHtml(openUrl)}" target="_blank" rel="noopener" title="打开 Viewer" aria-label="打开 Viewer"><i class="bi bi-box-arrow-up-right"></i></a>` : ''}
                ${zipUrl ? `<a class="btn btn-sm btn-outline-secondary asset-icon-btn" href="${escapeHtml(zipUrl)}" target="_blank" rel="noopener" title="下载 ZIP" aria-label="下载 ZIP"><i class="bi bi-file-earmark-zip"></i></a>` : ''}
                ${canDirectDownload ? `<a class="btn btn-sm btn-outline-secondary asset-icon-btn" href="/api/projects/${encodeURIComponent(this.projectId)}/assets/${encodeURIComponent(asset.id)}/download" title="下载文件" aria-label="下载文件"><i class="bi bi-download"></i></a>` : ''}
                ${deleteButton}
            </div>
        `;
    },

    renderAssets(assets) {
        const tableBody = document.getElementById('projectAssetsTableBody');
        if (!tableBody) return;

        const meta = document.getElementById('projectAssetsMeta');
        const filteredAssets = this.getFilteredAssets(assets);
        const filterActive = Boolean(this.assetFilters.query || this.assetFilters.type);
        if (meta) {
            meta.textContent = filterActive
                ? `显示 ${filteredAssets.length} / ${assets.length} 个资产`
                : `${assets.length} 个资产`;
        }

        if (!assets.length) {
            tableBody.innerHTML = '<tr><td colspan="5"><div class="mg-empty"><i class="bi bi-folder2-open"></i>该项目暂无资产。</div></td></tr>';
            return;
        }

        if (!filteredAssets.length) {
            tableBody.innerHTML = '<tr><td colspan="5"><div class="mg-empty"><i class="bi bi-funnel"></i>没有匹配当前筛选条件的资产。</div></td></tr>';
            return;
        }
        
        // Group assets by type for summary
        const assetsByType = {};
        filteredAssets.forEach(asset => {
            if (!assetsByType[asset.asset_type]) {
                assetsByType[asset.asset_type] = [];
            }
            assetsByType[asset.asset_type].push(asset);
        });

        tableBody.innerHTML = Object.entries(assetsByType).map(([type, typeAssets]) => `
            <tr class="asset-group-row">
                <td colspan="5">
                    <div class="asset-group-title">
                        <span class="file-type-badge asset-type-${escapeHtml(this.getAssetTypeConfig(type).tone)}">
                            <i class="bi ${escapeHtml(this.getAssetTypeConfig(type).icon)}"></i>
                            ${escapeHtml(this.getAssetTypeConfig(type).label)}
                        </span>
                        <strong>${typeAssets.length} 个资产</strong>
                    </div>
                </td>
            </tr>
            ${typeAssets.map(asset => {
                const metadata = asset.metadata_json || asset.metadata || {};
                const typeConfig = this.getAssetTypeConfig(asset.asset_type);
                const relativePath = this.getAssetRelativePath(asset);
                const sourceLabel = metadata.source === 'mongodb' ? 'MongoDB 缓存' : '项目资产';
                
                return `
                    <tr class="asset-data-row">
                        <td>
                            <div class="asset-name-cell">
                                <span class="asset-file-icon asset-type-${escapeHtml(typeConfig.tone)}"><i class="bi ${escapeHtml(typeConfig.icon)}"></i></span>
                                <div>
                                    <div class="fw-semibold">${escapeHtml(asset.original_name || '-')}</div>
                                    <div class="asset-row-meta">${escapeHtml(sourceLabel)}</div>
                                    ${this.renderAssetMetadata(asset)}
                                </div>
                            </div>
                        </td>
                        <td>
                            <div class="asset-path-cell">
                                <code title="${escapeHtml(relativePath)}">${escapeHtml(relativePath)}</code>
                                <button class="btn btn-sm btn-light asset-copy-btn" data-copy-path="${escapeHtml(relativePath)}" title="复制路径" aria-label="复制路径">
                                    <i class="bi bi-copy"></i>
                                </button>
                            </div>
                        </td>
                        <td>${escapeHtml(formatFileSize(asset.size || 0))}</td>
                        <td>${escapeHtml(formatDateTime(asset.uploaded_at))}</td>
                        <td class="text-end">
                            ${this.renderAssetActions(asset)}
                        </td>
                    </tr>
                `;
            }).join('')}
        `).join('');
        
        // Add delete event listeners
        tableBody.querySelectorAll('[data-asset-delete]').forEach(button => {
            button.addEventListener('click', () => this.deleteAsset(button.dataset.assetDelete));
        });
        tableBody.querySelectorAll('[data-copy-path]').forEach(button => {
            button.addEventListener('click', () => this.copyAssetPath(button.dataset.copyPath));
        });
    },

    async copyAssetPath(path) {
        if (!path || path === '-') {
            showManagementToast('没有可复制的路径。', 'info');
            return;
        }
        try {
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(path);
            } else {
                const textarea = document.createElement('textarea');
                textarea.value = path;
                textarea.setAttribute('readonly', '');
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                textarea.remove();
            }
            showManagementToast('资产路径已复制。', 'success');
        } catch (error) {
            showManagementToast('复制失败，请手动复制路径。', 'danger');
        }
    },

    renderSamplesPreview(samples) {
        const tbody = document.getElementById('samplesPreviewBody');
        if (!tbody) return;
        
        if (!samples.length) {
            tbody.innerHTML = '<tr><td colspan="4"><div class="mg-empty"><i class="bi bi-collection"></i>该项目暂无样本。</div></td></tr>';
            return;
        }
        
        // Show only first 5 samples
        const previewSamples = samples.slice(0, 5);
        
        tbody.innerHTML = previewSamples.map(sample => `
            <tr>
                <td>${escapeHtml(sample.sample_id || '-')}</td>
                <td>${escapeHtml(sample.sample_name || '-')}</td>
                <td>${escapeHtml(sample.chain || '-')}</td>
                <td class="text-end">
                    <button class="btn btn-sm btn-outline-primary" onclick="viewSampleDetail('${escapeHtml(sample.sample_id || '')}')">查看</button>
                </td>
            </tr>
        `).join('');
        
        if (samples.length > 5) {
            tbody.innerHTML += `
                <tr>
                    <td colspan="4" class="text-center text-muted">
                        还有 ${samples.length - 5} 个样本，<a href="${window.PROJECT_DETAIL_CONTEXT?.samplesPageUrl || '/samples'}?project_id=${encodeURIComponent(window.PROJECT_DETAIL_CONTEXT?.projectId || '')}">点击查看全部</a>
                    </td>
                </tr>
            `;
        }
    },

    renderGroupSpecs(groupSpecs) {
        const editor = document.getElementById('groupSpecEditor');
        const existing = document.getElementById('existingGroupSpecs');
        
        if (!editor || !existing) return;
        
        // Clear existing content
        editor.innerHTML = '';
        existing.innerHTML = '';
        
        if (!groupSpecs || groupSpecs.length === 0) {
            existing.innerHTML = '<div class="mg-empty"><i class="bi bi-diagram-2"></i>暂无保存的 group 规格。</div>';
            return;
        }
        
        // Render existing group specs
        existing.innerHTML = groupSpecs.map((spec, index) => `
            <div class="saved-group-spec">
                <div class="samples">${escapeHtml(spec.samples)}</div>
                <div>
                    <button class="btn btn-sm btn-outline-primary" onclick="editGroupSpec(${index})">编辑</button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteGroupSpec(${index})">删除</button>
                </div>
            </div>
        `).join('');
    },

    showUploadModal() {
        if (this.uploadModal) {
            this.uploadModal.show();
        }
    },

    captureUploads(files, isFolder) {
        const list = document.getElementById('selectedUploadList');
        if (!list) return;
        
        this.selectedUploads = Array.from(files);
        
        if (this.selectedUploads.length === 0) {
            list.innerHTML = '<div class="text-muted small">尚未选择待上传文件。</div>';
            return;
        }
        
        list.innerHTML = this.selectedUploads.map(file => `
            <div class="file-item">
                <div class="d-flex justify-content-between align-items-center">
                    <span>${escapeHtml(file.name)}</span>
                    <span class="text-muted">${formatFileSize(file.size)}</span>
                </div>
            </div>
        `).join('');
    },

    async uploadAssets() {
        if (!this.selectedUploads.length) {
            showManagementToast('请先选择要上传的文件。', 'info');
            return;
        }
        
        const formData = new FormData();
        const assetType = document.getElementById('assetTypeSelect')?.value || 'pep';
        const replaceExisting = document.getElementById('replaceExistingAssetsSwitch')?.checked || false;
        
        formData.append('asset_type', assetType);
        formData.append('replace_existing', replaceExisting);
        
        this.selectedUploads.forEach(file => {
            formData.append('files', file);
        });
        
        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(this.projectId)}/assets`, {
                method: 'POST',
                body: formData,
            });
            
            if (!response.ok) throw new Error('上传失败');
            
            // Close modal and refresh
            this.uploadModal.hide();
            this.loadProject();
            showManagementToast('项目资产已上传。', 'success');
            
            // Clear selections
            this.selectedUploads = [];
            document.getElementById('selectedUploadList').innerHTML = '<div class="text-muted small">尚未选择待上传文件。</div>';
            document.getElementById('assetFilesInput').value = '';
            document.getElementById('assetFolderInput').value = '';
            
        } catch (error) {
            showManagementToast('上传失败: ' + error.message, 'danger');
        }
    },

    async deleteAsset(assetId) {
        if (!confirm('确定要删除这个资产吗？')) return;
        
        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(this.projectId)}/assets/${encodeURIComponent(assetId)}`, {
                method: 'DELETE',
            });
            
            if (!response.ok) throw new Error('删除失败');
            
            this.loadProject();
            showManagementToast('资产已删除。', 'success');
            
        } catch (error) {
            showManagementToast('删除失败: ' + error.message, 'danger');
        }
    },

    appendGroupRow() {
        const editor = document.getElementById('groupSpecEditor');
        if (!editor) return;
        
        const rowDiv = document.createElement('div');
        rowDiv.className = 'group-spec-row';
        rowDiv.innerHTML = `
            <input type="text" class="form-control form-control-sm" placeholder="输入样本名，用逗号分隔">
            <button class="btn btn-sm btn-outline-danger" onclick="this.parentElement.remove()">删除</button>
        `;
        
        editor.appendChild(rowDiv);
    },

    async saveGroupSpec() {
        const rows = document.querySelectorAll('#groupSpecEditor .group-spec-row');
        const specs = Array.from(rows).map(row => {
            const input = row.querySelector('input');
            return input.value.trim();
        }).filter(spec => spec);
        
        if (specs.length === 0) {
            showManagementToast('请至少输入一个 group 规格。', 'info');
            return;
        }
        
        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(this.projectId)}/group-specs`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    spec_json: Object.fromEntries(specs.map((v, i) => [String(i), v])),
                    name: 'default'
                }),
            });
            
            if (!response.ok) throw new Error('保存失败');
            
            this.loadProject();
            showManagementToast('Group 规格已保存。', 'success');
            
        } catch (error) {
            showManagementToast('保存失败: ' + error.message, 'danger');
        }
    },

    clearGroupSpecs() {
        const editor = document.getElementById('groupSpecEditor');
        if (!editor) return;
        
        if (confirm('确定要清空所有输入的 group 规格吗？')) {
            editor.innerHTML = '';
            showManagementToast('已清空未保存的 group 输入。', 'info');
        }
    },

    launchAnalysis(type) {
        let url = '';
        switch (type) {
            case 'pipeline-comparison':
                url = `/api/pipeline-comparison/project/${this.projectId}`;
                break;
            case 'script-hub':
                url = `/analysis/script-hub?project_id=${encodeURIComponent(this.projectId)}&auto_scan=1&analysis_type=pep-analysis`;
                break;
            default:
                return;
        }
        
        window.open(url, '_blank');
    },
};

// Helper functions for onclick handlers
function viewSampleDetail(sampleId) {
    if (!sampleId) return;
    const samplesPageUrl = window.PROJECT_DETAIL_CONTEXT?.samplesPageUrl || '/samples';
    window.open(`${samplesPageUrl}?sample_id=${encodeURIComponent(sampleId)}`, '_blank');
}

function editGroupSpec(index) {
    // Implementation for editing group spec
    console.log('Edit group spec:', index);
}

function deleteGroupSpec(index) {
    if (!confirm('确定要删除这个 group 规格吗？')) return;
    
    fetch(`/api/projects/${encodeURIComponent(ProjectDetailPage.projectId)}/group-specs/${index}`, {
        method: 'DELETE',
    })
    .then(response => {
        if (!response.ok) throw new Error('删除失败');
        ProjectDetailPage.loadProject();
        showManagementToast('Group 规格已删除。', 'success');
    })
    .catch(error => {
        showManagementToast('删除失败: ' + error.message, 'danger');
    });
}

document.addEventListener('DOMContentLoaded', () => {
    ProjectDetailPage.init();
});
