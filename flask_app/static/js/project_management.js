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

const ProjectManagementPage = {
    createModal: null,

    init() {
        if (!document.getElementById('projectsTableBody')) return;
        this.createModal = new bootstrap.Modal(document.getElementById('createProjectModal'));
        document.getElementById('searchProjectsBtn')?.addEventListener('click', () => this.loadProjects());
        document.getElementById('submitCreateProjectBtn')?.addEventListener('click', () => this.createProject());
        this.loadProjects();
    },

    async loadProjects() {
        const params = new URLSearchParams({
            name: document.getElementById('filterProjectName')?.value || '',
            institution: document.getElementById('filterInstitution')?.value || '',
            cooperation_level: document.getElementById('filterCooperationLevel')?.value || '',
        });
        const errorAlert = document.getElementById('projectsErrorAlert');
        errorAlert?.classList.add('d-none');

        try {
            const response = await fetch(`/api/projects?${params.toString()}`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || '加载项目失败');
            this.renderProjects(data.projects || []);
        } catch (error) {
            if (errorAlert) {
                errorAlert.textContent = error.message || '加载项目失败';
                errorAlert.classList.remove('d-none');
            }
        }
    },

    renderProjects(projects) {
        const tableBody = document.getElementById('projectsTableBody');
        if (!tableBody) return;

        const totalSamples = projects.reduce((sum, item) => sum + Number(item.sample_count || 0), 0);
        const totalResults = projects.reduce((sum, item) => sum + Number(item.result_count || 0), 0);
        const pepProjects = projects.filter((item) => item.has_pep).length;

        document.getElementById('statProjectCount').textContent = String(projects.length);
        document.getElementById('statPepCount').textContent = String(pepProjects);
        document.getElementById('statSampleCount').textContent = String(totalSamples);
        document.getElementById('statResultCount').textContent = String(totalResults);

        if (!projects.length) {
            tableBody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-4">没有匹配的项目。</td></tr>';
            return;
        }

        tableBody.innerHTML = projects.map((project) => {
            const chips = [
                project.has_profile ? '<span class="asset-chip">profile</span>' : '',
                project.has_pep ? '<span class="asset-chip">pep</span>' : '',
                project.has_sample_summary ? '<span class="asset-chip">sample summary</span>' : '',
                project.has_group_spec ? '<span class="asset-chip">group spec</span>' : '',
            ].join('');
            return `
                <tr>
                    <td>
                        <div class="fw-semibold">${escapeHtml(project.name)}</div>
                        <div class="small text-muted">${escapeHtml(project.description || '未填写项目说明')}</div>
                    </td>
                    <td>
                        <div>${escapeHtml(project.institution || '-')}</div>
                        <div class="small text-muted">${escapeHtml(project.cooperation_level || '-')}</div>
                    </td>
                    <td>
                        <div class="fw-semibold">${project.sample_count || 0}</div>
                        <div class="small text-muted">group spec: ${project.group_spec_count || 0}</div>
                    </td>
                    <td>${chips || '<span class="text-muted small">暂无资产</span>'}</td>
                    <td>
                        <span class="project-status-badge">
                            <i class="bi bi-bar-chart"></i>${project.result_count || 0} 个结果
                        </span>
                    </td>
                    <td>${escapeHtml(formatDateTime(project.updated_at || project.created_at))}</td>
                    <td class="text-end">
                        <a class="btn btn-sm btn-outline-primary" href="/projects/${encodeURIComponent(project.id)}">打开</a>
                        <button class="btn btn-sm btn-outline-danger ms-1" data-project-delete="${escapeHtml(project.id)}">删除</button>
                    </td>
                </tr>
            `;
        }).join('');

        tableBody.querySelectorAll('[data-project-delete]').forEach((button) => {
            button.addEventListener('click', () => this.deleteProject(button.dataset.projectDelete));
        });
    },

    async createProject() {
        const payload = {
            name: document.getElementById('projectNameInput')?.value || '',
            institution: document.getElementById('projectInstitutionInput')?.value || '',
            cooperation_level: document.getElementById('projectCooperationInput')?.value || '',
            description: document.getElementById('projectDescriptionInput')?.value || '',
            status: document.getElementById('projectStatusInput')?.value || 'active',
        };

        try {
            const response = await fetch('/api/projects', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || '创建项目失败');
            this.createModal?.hide();
            window.location.href = `/projects/${encodeURIComponent(data.id)}`;
        } catch (error) {
            alert(error.message || '创建项目失败');
        }
    },

    async deleteProject(projectId) {
        if (!projectId || !window.confirm('删除项目会同时删除项目资产和样本记录，是否继续？')) {
            return;
        }
        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' });
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || '删除项目失败');
            this.loadProjects();
        } catch (error) {
            alert(error.message || '删除项目失败');
        }
    },
};

const ProjectDetailPage = {
    projectId: '',
    projectData: null,
    selectedUploads: [],

    init() {
        if (!window.PROJECT_DETAIL_CONTEXT || !document.getElementById('projectAssetsTableBody')) return;
        this.projectId = window.PROJECT_DETAIL_CONTEXT.projectId;
        document.getElementById('refreshProjectDetailBtn')?.addEventListener('click', () => this.loadProject());
        document.getElementById('selectAssetFilesBtn')?.addEventListener('click', () => document.getElementById('assetFilesInput')?.click());
        document.getElementById('selectAssetFolderBtn')?.addEventListener('click', () => document.getElementById('assetFolderInput')?.click());
        document.getElementById('assetFilesInput')?.addEventListener('change', (event) => this.captureUploads(event.target.files, false));
        document.getElementById('assetFolderInput')?.addEventListener('change', (event) => this.captureUploads(event.target.files, true));
        document.getElementById('uploadAssetsBtn')?.addEventListener('click', () => this.uploadAssets());
        document.getElementById('addGroupRowBtn')?.addEventListener('click', () => this.appendGroupRow());
        document.getElementById('saveGroupSpecBtn')?.addEventListener('click', () => this.saveGroupSpec());
        document.querySelectorAll('[data-analysis-launch]').forEach((button) => {
            button.addEventListener('click', () => this.launchAnalysis(button.dataset.analysisLaunch));
        });
        this.loadProject();
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
        document.getElementById('projectTitle').textContent = project.name || '项目详情';
        document.getElementById('projectSubtitle').textContent = project.description || '项目尚未填写描述。';
        document.getElementById('projectInstitutionValue').textContent = project.institution || '-';
        document.getElementById('projectCooperationValue').textContent = project.cooperation_level || '-';
        document.getElementById('projectStatusValue').textContent = project.status || '-';
        document.getElementById('projectUpdatedAtValue').textContent = formatDateTime(project.updated_at || project.created_at);

        document.getElementById('overviewSampleCount').textContent = String(project.sample_count || 0);
        document.getElementById('overviewResultCount').textContent = String(project.result_count || 0);
        document.getElementById('overviewPepCount').textContent = String(counts.pep || 0);
        document.getElementById('overviewDatapointCount').textContent = String(counts.profile || 0);

        this.renderAssets(project.assets || []);
        this.renderSamplesPreview(project.samples_preview || []);
        this.renderGroupSpecs(project.group_specs || []);
    },

    renderAssets(assets) {
        const tableBody = document.getElementById('projectAssetsTableBody');
        if (!assets.length) {
            tableBody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-4">该项目暂无资产。</td></tr>';
            return;
        }

        tableBody.innerHTML = assets.map((asset) => {
            const metadata = asset.metadata || {};
            const openUrl = metadata.report_url || metadata.viewer_url || metadata.metadata_url || '';
            const zipUrl = metadata.zip_url || '';
            const signature = metadata.analysis_signature || '';
            const relativePath = asset.asset_type === 'processed_result'
                ? (metadata.output_base || metadata.report_path || asset.storage_path || '-')
                : (metadata.relative_path || metadata.report_path || '-');
            const canDirectDownload = asset.asset_type !== 'processed_result'
                || (metadata.report_path && !String(metadata.report_path).startsWith('/api/'));
            const openButton = openUrl
                ? `<a class="btn btn-sm btn-outline-primary" href="${escapeHtml(openUrl)}" target="_blank" rel="noopener">打开 Viewer</a>`
                : '';
            const zipButton = zipUrl
                ? `<a class="btn btn-sm btn-outline-secondary" href="${escapeHtml(zipUrl)}" target="_blank" rel="noopener">下载 ZIP</a>`
                : '';
            const downloadButton = canDirectDownload
                ? `<a class="btn btn-sm btn-outline-secondary" href="/api/projects/${encodeURIComponent(this.projectId)}/assets/${encodeURIComponent(asset.id)}/download">下载</a>`
                : '';
            const deleteButton = metadata.source === 'mongodb'
                ? ''
                : `<button class="btn btn-sm btn-outline-danger" data-asset-delete="${escapeHtml(asset.id)}">删除</button>`;
            const resultMeta = asset.asset_type === 'processed_result'
                ? `<div class="asset-row-meta">Type: ${escapeHtml(metadata.analysis_type || '-')} | Signature: ${escapeHtml(signature ? signature.slice(0, 12) : '-')}</div>`
                : '';
            return `
                <tr>
                    <td>
                        <div class="fw-semibold">${escapeHtml(asset.asset_type)}</div>
                        <div>${escapeHtml(asset.original_name || '-')}</div>
                        <div class="asset-row-meta">${escapeHtml(formatFileSize(asset.size || 0))}</div>
                        ${resultMeta}
                    </td>
                    <td class="text-break">${escapeHtml(relativePath)}</td>
                    <td>${escapeHtml(formatDateTime(asset.uploaded_at))}</td>
                    <td class="text-end">
                        ${openButton}
                        ${zipButton}
                        ${downloadButton}
                        ${deleteButton}
                    </td>
                </tr>
            `;
        }).join('');

        tableBody.querySelectorAll('[data-asset-delete]').forEach((button) => {
            button.addEventListener('click', () => this.deleteAsset(button.dataset.assetDelete));
        });
    },

    renderSamplesPreview(samples) {
        const tbody = document.getElementById('samplesPreviewBody');
        if (!samples.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-4">尚未导入 sample summary。</td></tr>';
            return;
        }
        tbody.innerHTML = samples.map((sample) => `
            <tr>
              <td>${escapeHtml(sample.sample_id || '-')}</td>
              <td>${escapeHtml(sample.sample_name || '-')}</td>
              <td>${escapeHtml(sample.chain_flag || '-')}</td>
              <td>${escapeHtml(sample.illness || '-')}</td>
              <td>${escapeHtml(sample.iso_tag || '-')}</td>
            </tr>
        `).join('');
    },

    renderGroupSpecs(specs) {
        const existingContainer = document.getElementById('existingGroupSpecs');
        const editor = document.getElementById('groupSpecEditor');

        if (!editor.children.length) {
            if (specs.length > 0) {
                const groups = Array.isArray(specs[0].spec_json?.groups) ? specs[0].spec_json.groups : [];
                if (groups.length) {
                    groups.forEach((group) => this.appendGroupRow(group.name || '', (group.sample_names || []).join(',')));
                } else {
                    this.appendGroupRow();
                }
            } else {
                this.appendGroupRow();
            }
        }

        if (!specs.length) {
            existingContainer.innerHTML = '<div class="text-muted small">暂无已保存的 group 规格。</div>';
            return;
        }

        existingContainer.innerHTML = specs.map((spec) => {
            const groups = Array.isArray(spec.spec_json?.groups) ? spec.spec_json.groups : [];
            const summary = groups.map((group) => `${group.name}: ${(group.sample_names || []).join(', ')}`).join(' | ');
            return `
                <div class="border rounded-3 p-3 mb-2 bg-light-subtle">
                    <div class="fw-semibold">${escapeHtml(spec.name || 'default')}</div>
                    <div class="small text-muted">${escapeHtml(summary || '空规格')}</div>
                    <div class="small text-muted mt-1">更新时间：${escapeHtml(formatDateTime(spec.updated_at || spec.created_at))}</div>
                </div>
            `;
        }).join('');
    },

    appendGroupRow(groupName = '', sampleNames = '') {
        const container = document.getElementById('groupSpecEditor');
        const row = document.createElement('div');
        row.className = 'group-row';
        row.innerHTML = `
            <input type="text" class="form-control group-name-input" placeholder="Group 名称" value="${escapeHtml(groupName)}">
            <input type="text" class="form-control group-samples-input" placeholder="样本名，逗号分隔" value="${escapeHtml(sampleNames)}">
            <button class="btn btn-outline-danger btn-sm" type="button">删除</button>
        `;
        row.querySelector('button').addEventListener('click', () => row.remove());
        container.appendChild(row);
    },

    captureUploads(fileList, fromFolder) {
        this.selectedUploads = Array.from(fileList || []).map((file) => ({
            file,
            relativePath: fromFolder ? (file.webkitRelativePath || file.name) : file.name,
        }));
        this.renderSelectedUploads();
    },

    renderSelectedUploads() {
        const container = document.getElementById('selectedUploadList');
        if (!this.selectedUploads.length) {
            container.innerHTML = '<div class="text-muted small">尚未选择待上传文件。</div>';
            return;
        }
        container.innerHTML = this.selectedUploads.map((item) => `
            <div class="selected-upload-item">
                <div class="text-break">${escapeHtml(item.relativePath)}</div>
                <div class="text-muted">${escapeHtml(formatFileSize(item.file.size))}</div>
            </div>
        `).join('');
    },

    async uploadAssets() {
        if (!this.selectedUploads.length) {
            alert('请先选择要上传的文件或文件夹。');
            return;
        }
        const formData = new FormData();
        const relativePaths = [];
        formData.append('asset_type', document.getElementById('assetTypeSelect')?.value || 'pep');
        formData.append('replace_existing', document.getElementById('replaceExistingAssetsSwitch')?.checked ? 'true' : 'false');
        this.selectedUploads.forEach((item) => {
            formData.append('files', item.file, item.file.name);
            relativePaths.push(item.relativePath);
        });
        formData.append('relative_paths', JSON.stringify(relativePaths));

        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(this.projectId)}/assets`, {
                method: 'POST',
                body: formData,
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || '上传项目资产失败');
            this.selectedUploads = [];
            document.getElementById('assetFilesInput').value = '';
            document.getElementById('assetFolderInput').value = '';
            this.renderSelectedUploads();
            await this.loadProject();
        } catch (error) {
            alert(error.message || '上传项目资产失败');
        }
    },

    async deleteAsset(assetId) {
        if (!assetId || !window.confirm('确定删除该资产吗？')) return;
        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(this.projectId)}/assets/${encodeURIComponent(assetId)}`, {
                method: 'DELETE',
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || '删除资产失败');
            this.loadProject();
        } catch (error) {
            alert(error.message || '删除资产失败');
        }
    },

    async saveGroupSpec() {
        const groups = Array.from(document.querySelectorAll('#groupSpecEditor .group-row')).map((row) => {
            const name = row.querySelector('.group-name-input')?.value?.trim() || '';
            const sampleNames = (row.querySelector('.group-samples-input')?.value || '')
                .split(',')
                .map((item) => item.trim())
                .filter(Boolean);
            return { name, sample_names: sampleNames };
        }).filter((group) => group.name && group.sample_names.length > 0);

        if (!groups.length) {
            alert('至少填写一个有效 group。');
            return;
        }

        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(this.projectId)}/group-specs`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: 'default',
                    spec_json: { groups },
                }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || '保存 group 规格失败');
            this.renderGroupSpecs(data.group_specs || []);
        } catch (error) {
            alert(error.message || '保存 group 规格失败');
        }
    },

    async launchAnalysis(analysisType) {
        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(this.projectId)}/analysis/${encodeURIComponent(analysisType)}/prepare`, {
                method: 'POST',
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || '准备分析失败');
            window.location.href = data.page_url;
        } catch (error) {
            alert(error.message || '准备分析失败');
        }
    },
};

document.addEventListener('DOMContentLoaded', () => {
    ProjectManagementPage.init();
    ProjectDetailPage.init();
});
