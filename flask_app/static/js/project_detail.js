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

const ProjectDetailPage = {
    projectId: '',
    projectData: null,
    selectedUploads: [],
    uploadModal: null,

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
        
        // Project settings form
        const settingsForm = document.getElementById('projectSettingsForm');
        if (settingsForm) {
            settingsForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.updateProjectSettings();
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
                document.querySelectorAll('.tab-content').forEach(content => {
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

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    ProjectDetailPage.init();
});
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
        document.getElementById('overviewDatapointCount').textContent = String(counts.datapoint || 0);
        
        // Update asset statistics
        this.renderAssetStatistics(counts);
        
        // Update sample statistics
        this.renderSampleStatistics(counts);
        
        // Update project settings form
        this.updateProjectSettingsForm();
        
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
    },

    async updateProjectSettings() {
        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(this.projectId)}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    name: document.getElementById('projectNameInput').value,
                    description: document.getElementById('projectDescInput').value,
                    institution: document.getElementById('projectInstitutionInput').value,
                    cooperation_level: document.getElementById('projectCooperationInput').value,
                    status: document.getElementById('projectStatusInput').value,
                }),
            });
            
            if (!response.ok) throw new Error('更新失败');
            
            // Show success message
            const alert = document.createElement('div');
            alert.className = 'alert alert-success alert-dismissible fade show';
            alert.innerHTML = '<i class="bi bi-check-circle me-2"></i>项目设置已更新';
            document.querySelector('#settings-tab .card-body').prepend(alert);
            
            setTimeout(() => {
                alert.remove();
                this.loadProject(); // Refresh the project data
            }, 2000);
            
        } catch (error) {
            console.error('Error updating project settings:', error);
        }
    },

    renderAssets(assets) {
        const tableBody = document.getElementById('projectAssetsTableBody');
        if (!tableBody) return;
        
        if (!assets.length) {
            tableBody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-4">该项目暂无资产。</td></tr>';
            return;
        }
        
        // Group assets by type for summary
        const assetsByType = {};
        assets.forEach(asset => {
            if (!assetsByType[asset.asset_type]) {
                assetsByType[asset.asset_type] = [];
            }
            assetsByType[asset.asset_type].push(asset);
        });
        
        const typeLabels = {
            'datapoint': 'Profile Data',
            'pep': 'Pep Files',
            'sample_summary': 'Sample Summary',
            'group_spec': 'Group Spec',
            'processed_result': 'Analysis Result',
            'raw_archive': 'Raw Archive',
            'cached_usage': 'Pep Usage Cache',
        };

        tableBody.innerHTML = Object.entries(assetsByType).map(([type, typeAssets]) => `
            <tr>
                <td colspan="4">
                    <div class="file-type-badge">${typeLabels[type] || type}</div>
                    <strong>${typeAssets.length} 个文件</strong>
                </td>
            </tr>
            ${typeAssets.map(asset => {
                const metadata = asset.metadata_json || asset.metadata || {};
                const openUrl = metadata.report_url || metadata.viewer_url || metadata.metadata_url || '';
                const zipUrl = metadata.zip_url || '';
                const relativePath = metadata.relative_path || metadata.report_path || '-';
                const canDirectDownload = asset.asset_type !== 'processed_result'
                    && asset.asset_type !== 'cached_usage'
                    || (metadata.report_path && !String(metadata.report_path).startsWith('/api/'));

                let extraMeta = '';
                if (asset.asset_type === 'cached_usage') {
                    const chains = (metadata.chains || []).join(', ');
                    const groups = (metadata.group_fields || []).join(', ');
                    extraMeta = `<div class="small text-muted">Chains: ${escapeHtml(chains || '-')} | Groups: ${escapeHtml(groups || '-')}</div>`;
                }
                if (asset.asset_type === 'processed_result') {
                    const analysisType = metadata.analysis_type || '';
                    extraMeta = `<div class="small text-muted">Type: ${escapeHtml(analysisType || '-')}</div>`;
                }
                
                return `
                    <tr>
                        <td>
                            <div class="fw-semibold">${escapeHtml(asset.original_name || '-')}</div>
                            <div class="asset-row-meta">${escapeHtml(formatFileSize(asset.size || 0))}</div>
                            ${extraMeta}
                        </td>
                        <td class="text-break">${escapeHtml(relativePath)}</td>
                        <td>${escapeHtml(formatDateTime(asset.uploaded_at))}</td>
                        <td class="text-end">
                            ${openUrl ? `<a class="btn btn-sm btn-outline-primary" href="${escapeHtml(openUrl)}" target="_blank" rel="noopener">打开</a>` : ''}
                            ${zipUrl ? `<a class="btn btn-sm btn-outline-secondary" href="${escapeHtml(zipUrl)}" target="_blank" rel="noopener">ZIP</a>` : ''}
                            ${canDirectDownload ? `<a class="btn btn-sm btn-outline-secondary" href="/api/projects/${encodeURIComponent(this.projectId)}/assets/${encodeURIComponent(asset.id)}/download">下载</a>` : ''}
                            <button class="btn btn-sm btn-outline-danger" data-asset-delete="${escapeHtml(asset.id)}">删除</button>
                        </td>
                    </tr>
                `;
            }).join('')}
        `).join('');
        
        // Add delete event listeners
        tableBody.querySelectorAll('[data-asset-delete]').forEach(button => {
            button.addEventListener('click', () => this.deleteAsset(button.dataset.assetDelete));
        });
    },

    renderSamplesPreview(samples) {
        const tbody = document.getElementById('samplesPreviewBody');
        if (!tbody) return;
        
        if (!samples.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-4">该项目暂无样本。</td></tr>';
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
                        还有 ${samples.length - 5} 个样本，<a href="{{ url_for('pages.samples_page') }}?project_id={{ project_id }}">点击查看全部</a>
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
            existing.innerHTML = '<div class="text-muted small">暂无保存的 group 规格</div>';
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
            alert('请先选择要上传的文件');
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
            
            // Clear selections
            this.selectedUploads = [];
            document.getElementById('selectedUploadList').innerHTML = '<div class="text-muted small">尚未选择待上传文件。</div>';
            document.getElementById('assetFilesInput').value = '';
            document.getElementById('assetFolderInput').value = '';
            
        } catch (error) {
            alert('上传失败: ' + error.message);
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
            
        } catch (error) {
            alert('删除失败: ' + error.message);
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
            alert('请至少输入一个 group 规格');
            return;
        }
        
        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(this.projectId)}/group-specs`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ specs }),
            });
            
            if (!response.ok) throw new Error('保存失败');
            
            this.loadProject();
            
        } catch (error) {
            alert('保存失败: ' + error.message);
        }
    },

    clearGroupSpecs() {
        const editor = document.getElementById('groupSpecEditor');
        if (!editor) return;
        
        if (confirm('确定要清空所有输入的 group 规格吗？')) {
            editor.innerHTML = '';
        }
    },

    launchAnalysis(type) {
        let url = '';
        switch (type) {
            case 'combined-report':
                url = `/api/combined-analysis/project/${this.projectId}`;
                break;
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
    window.open(`/api/samples/${sampleId}`, '_blank');
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
    })
    .catch(error => {
        alert('删除失败: ' + error.message);
    });
}