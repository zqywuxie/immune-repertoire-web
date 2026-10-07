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

const ProjectManagementPage = {
    createModal: null,
    requestVersion: 0,
    currentPage: 1,

    init() {
        if (!document.getElementById('projectsTableBody')) return;
        this.createModal = new bootstrap.Modal(document.getElementById('createProjectModal'));
        document.getElementById('searchProjectsBtn')?.addEventListener('click', () => this.loadProjects());
        document.getElementById('resetProjectsBtn')?.addEventListener('click', () => this.resetFilters());
        document.getElementById('submitCreateProjectBtn')?.addEventListener('click', () => this.createProject());
        ['filterProjectName', 'filterInstitution', 'filterCooperationLevel'].forEach((id) => {
            document.getElementById(id)?.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') this.loadProjects();
            });
        });
        const query = new URLSearchParams(location.search);
        for (const [key,id] of [['name','filterProjectName'],['institution','filterInstitution'],['cooperation_level','filterCooperationLevel']]) {
            if(query.has(key)) document.getElementById(id).value=query.get(key);
        }
        this.loadProjects(Math.max(1,Number(query.get('page')) || 1));
        this.loadStatistics();
    },

    async loadProjects(page = 1) {
        const version = ++this.requestVersion;
        this.currentPage = Math.max(1, page);
        let navigation = document.getElementById('legacyProjectPages');
        if (!navigation) {
            navigation=document.createElement('div');navigation.id='legacyProjectPages';navigation.className='d-flex gap-2 align-items-center flex-wrap p-3';
            document.getElementById('projectsTableBody').closest('table').parentElement.after(navigation);
        }
        navigation.replaceChildren();
        const params = new URLSearchParams({
            page: String(this.currentPage), page_size: '24',
            name: document.getElementById('filterProjectName')?.value || '',
            institution: document.getElementById('filterInstitution')?.value || '',
            cooperation_level: document.getElementById('filterCooperationLevel')?.value || '',
        });
        const errorAlert = document.getElementById('projectsErrorAlert');
        errorAlert?.classList.add('d-none');
        this.setTableLoading();

        try {
            const response = await fetch(`/api/projects?${params.toString()}`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || '加载项目失败');
            if(version!==this.requestVersion)return;
            const last=Math.max(1,data.pagination.total_pages);
            if(this.currentPage>last)return this.loadProjects(last);
            history.replaceState(history.state,'',location.pathname+'?'+params);
            this.renderProjects(data.projects || []);
            const info=document.createElement('span');info.textContent=`共 ${data.pagination.total} 个匹配项目 · 第 ${this.currentPage} / ${last} 页`;navigation.append(info);
            for(const [label,next,disabled] of [['上一页',this.currentPage-1,this.currentPage<=1],['下一页',this.currentPage+1,this.currentPage>=last]]){
                const button=document.createElement('button');button.type='button';button.className='btn btn-sm btn-outline-primary';button.textContent=label;button.disabled=disabled;button.addEventListener('click',()=>this.loadProjects(next));navigation.append(button);
            }
        } catch (error) {
            if(version!==this.requestVersion)return;
            if (errorAlert) {
                errorAlert.textContent = error.message || '加载项目失败';
                errorAlert.classList.remove('d-none');
            }
            showManagementToast(error.message || '加载项目失败', 'danger');
        }
    },

    async loadStatistics() {
        const fields={statProjectCount:'project_count',statPepCount:'pep_project_count',statSampleCount:'registered_sample_count',statResultCount:'result_count'};
        try{
            const response=await fetch('/api/projects/statistics');const stats=await response.json();if(!response.ok)throw new Error(stats.message || '统计读取失败');
            for(const [id,key] of Object.entries(fields))document.getElementById(id).textContent=String(stats[key]);
        }catch(error){for(const id of Object.keys(fields))document.getElementById(id).textContent='—';showManagementToast(error.message || '统计读取失败，可刷新重试','danger');}
    },

    setTableLoading() {
        const tableBody = document.getElementById('projectsTableBody');
        if (tableBody) {
            tableBody.innerHTML = '<tr><td colspan="7"><div class="mg-empty"><i class="bi bi-hourglass-split"></i>正在加载项目...</div></td></tr>';
        }
    },

    renderProjects(projects) {
        const tableBody = document.getElementById('projectsTableBody');
        if (!tableBody) return;

        if (!projects.length) {
            tableBody.innerHTML = '<tr><td colspan="7"><div class="mg-empty"><i class="bi bi-search"></i>没有匹配的项目。</div></td></tr>';
            return;
        }

        tableBody.innerHTML = projects.map((project) => {
            const chips = [
                project.has_profile ? '<span class="asset-chip mg-badge-blue"><i class="bi bi-table"></i>profile</span>' : '',
                project.has_pep ? '<span class="asset-chip mg-badge-green"><i class="bi bi-file-earmark-binary"></i>pep</span>' : '',
                project.has_sample_summary ? '<span class="asset-chip mg-badge-amber"><i class="bi bi-collection"></i>sample summary</span>' : '',
                project.has_group_spec ? '<span class="asset-chip mg-badge-gray"><i class="bi bi-diagram-2"></i>group spec</span>' : '',
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
            showManagementToast('项目已创建，正在打开项目详情。', 'success');
            window.location.href = `/projects/${encodeURIComponent(data.id)}`;
        } catch (error) {
            showManagementToast(error.message || '创建项目失败', 'danger');
        }
    },

    async deleteProject(projectId) {
        if (!projectId || !window.confirm('删除项目会同时删除项目上传文件、分析结果和历史任务；有未结束任务时无法删除。是否继续？')) {
            return;
        }
        try {
            const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' });
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || '删除项目失败');
            showManagementToast('项目已删除。', 'success');
            this.loadProjects(this.currentPage); this.loadStatistics();
        } catch (error) {
            showManagementToast(error.message || '删除项目失败', 'danger');
        }
    },

    resetFilters() {
        ['filterProjectName', 'filterInstitution', 'filterCooperationLevel'].forEach((id) => {
            const input = document.getElementById(id);
            if (input) input.value = '';
        });
        this.loadProjects();
    },
};

document.addEventListener('DOMContentLoaded', () => {
    ProjectManagementPage.init();
});
