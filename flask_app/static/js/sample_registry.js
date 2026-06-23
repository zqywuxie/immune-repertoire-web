function csvEscape(value) {
    const text = String(value ?? '');
    if (text.includes(',') || text.includes('"') || text.includes('\n')) {
        return `"${text.replaceAll('"', '""')}"`;
    }
    return text;
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

function renderBooleanBadge(value, trueLabel = 'True', falseLabel = 'False') {
    const normalized = String(value ?? '').toLowerCase();
    if (normalized === 'true' || normalized === '1' || normalized === 'yes') {
        return `<span class="mg-chip mg-badge-green">${trueLabel}</span>`;
    }
    if (normalized === 'false' || normalized === '0' || normalized === 'no') {
        return `<span class="mg-chip mg-badge-gray">${falseLabel}</span>`;
    }
    return '<span class="text-muted">-</span>';
}

const SampleRegistryPage = {
    samples: [],
    editModal: null,

    init() {
        if (!document.getElementById('samplesTableBody')) return;
        this.editModal = new bootstrap.Modal(document.getElementById('sampleEditModal'));
        document.getElementById('searchSamplesBtn')?.addEventListener('click', () => this.loadSamples());
        document.getElementById('resetSamplesBtn')?.addEventListener('click', () => this.resetFilters());
        document.getElementById('saveSampleChangesBtn')?.addEventListener('click', () => this.saveSampleChanges());
        document.getElementById('exportSamplesBtn')?.addEventListener('click', () => this.exportSamples());
        document.querySelectorAll('[id^="sampleFilter"]').forEach((input) => {
            input.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') this.loadSamples();
            });
        });
        this.bootstrapFromQuery();
        this.loadSamples();
    },

    bootstrapFromQuery() {
        const params = new URLSearchParams(window.location.search);
        const projectId = params.get('project_id');
        if (projectId) {
            document.getElementById('sampleFilterProjectId').value = projectId;
        }
        const projectName = params.get('project_name');
        if (projectName) {
            document.getElementById('sampleFilterProjectName').value = projectName;
        }
        const sampleId = params.get('sample_id');
        if (sampleId) {
            document.getElementById('sampleFilterSampleId').value = sampleId;
        }
    },

    collectFilters() {
        return {
            project_id: document.getElementById('sampleFilterProjectId')?.value || '',
            project_name: document.getElementById('sampleFilterProjectName')?.value || '',
            sample_id: document.getElementById('sampleFilterSampleId')?.value || '',
            sample_name: document.getElementById('sampleFilterSampleName')?.value || '',
            institution: document.getElementById('sampleFilterInstitution')?.value || '',
            sequence_id: document.getElementById('sampleFilterSequenceId')?.value || '',
            contain_method: document.getElementById('sampleFilterContainMethod')?.value || '',
            iso_tag: document.getElementById('sampleFilterIsoTag')?.value || '',
            spices: document.getElementById('sampleFilterSpices')?.value || '',
            chain_flag: document.getElementById('sampleFilterChainFlag')?.value || '',
            is_healthy: document.getElementById('sampleFilterIsHealthy')?.value || '',
            illness: document.getElementById('sampleFilterIllness')?.value || '',
            is_pe: document.getElementById('sampleFilterIsPe')?.value || '',
        };
    },

    async loadSamples() {
        const params = new URLSearchParams(this.collectFilters());
        const errorAlert = document.getElementById('samplesErrorAlert');
        errorAlert?.classList.add('d-none');
        this.setTableLoading();

        try {
            const response = await fetch(`/api/samples?${params.toString()}`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || '加载样本失败');
            this.samples = data.samples || [];
            this.renderSamples();
            this.renderResultMeta();
        } catch (error) {
            if (errorAlert) {
                errorAlert.textContent = error.message || '加载样本失败';
                errorAlert.classList.remove('d-none');
            }
            showManagementToast(error.message || '加载样本失败', 'danger');
        }
    },

    setTableLoading() {
        const tbody = document.getElementById('samplesTableBody');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="12"><div class="mg-empty"><i class="bi bi-hourglass-split"></i>正在加载样本...</div></td></tr>';
        }
    },

    renderSamples() {
        const tbody = document.getElementById('samplesTableBody');
        if (!this.samples.length) {
            tbody.innerHTML = '<tr><td colspan="12"><div class="mg-empty"><i class="bi bi-search"></i>没有匹配的样本记录。</div></td></tr>';
            return;
        }

        tbody.innerHTML = this.samples.map((sample) => `
            <tr>
              <td>${escapeHtml(sample.project_name || '-')}</td>
              <td>${escapeHtml(sample.sample_id || '-')}</td>
              <td>${escapeHtml(sample.sample_name || '-')}</td>
              <td>${escapeHtml(sample.sequence_id || '-')}</td>
              <td>${escapeHtml(sample.spices || '-')}</td>
              <td><span class="mg-chip mg-badge-blue">${escapeHtml(sample.chain_flag || '-')}</span></td>
              <td>${renderBooleanBadge(sample.is_healthy, 'Healthy', 'Non-healthy')}</td>
              <td>${escapeHtml(sample.illness || '-')}</td>
              <td>${renderBooleanBadge(sample.is_pe, 'PE', 'Non-PE')}</td>
              <td>${escapeHtml(sample.contain_method || '-')}</td>
              <td>${escapeHtml(sample.iso_tag || '-')}</td>
              <td class="text-end">
                <button class="btn btn-sm btn-outline-primary" data-sample-edit="${escapeHtml(sample.id)}">编辑</button>
              </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('[data-sample-edit]').forEach((button) => {
            button.addEventListener('click', () => this.openEditModal(button.dataset.sampleEdit));
        });
    },

    renderResultMeta() {
        const meta = document.getElementById('sampleResultCount');
        if (meta) {
            meta.textContent = `当前结果：${this.samples.length} 条样本记录`;
        }
        const exportBtn = document.getElementById('exportSamplesBtn');
        if (exportBtn) {
            exportBtn.disabled = this.samples.length === 0;
            exportBtn.title = this.samples.length ? '导出当前结果' : '当前没有可导出的样本';
        }
    },

    openEditModal(sampleId) {
        const sample = this.samples.find((item) => item.id === sampleId);
        if (!sample) return;
        document.getElementById('editSampleRecordId').value = sample.id || '';
        document.getElementById('editSampleId').value = sample.sample_id || '';
        document.getElementById('editSampleName').value = sample.sample_name || '';
        document.getElementById('editSequenceId').value = sample.sequence_id || '';
        document.getElementById('editSpices').value = sample.spices || '';
        document.getElementById('editInstitution').value = sample.institution || '';
        document.getElementById('editChainFlag').value = sample.chain_flag || '';
        document.getElementById('editIsHealthy').value = sample.is_healthy || '';
        document.getElementById('editIllness').value = sample.illness || '';
        document.getElementById('editIsPe').value = sample.is_pe || '';
        document.getElementById('editContainMethod').value = sample.contain_method || '';
        document.getElementById('editIsoTag').value = sample.iso_tag || '';
        this.editModal?.show();
    },

    async saveSampleChanges() {
        const sampleId = document.getElementById('editSampleRecordId')?.value || '';
        if (!sampleId) return;
        const payload = {
            sample_id: document.getElementById('editSampleId')?.value || '',
            sample_name: document.getElementById('editSampleName')?.value || '',
            sequence_id: document.getElementById('editSequenceId')?.value || '',
            spices: document.getElementById('editSpices')?.value || '',
            institution: document.getElementById('editInstitution')?.value || '',
            chain_flag: document.getElementById('editChainFlag')?.value || '',
            is_healthy: document.getElementById('editIsHealthy')?.value || '',
            illness: document.getElementById('editIllness')?.value || '',
            is_pe: document.getElementById('editIsPe')?.value || '',
            contain_method: document.getElementById('editContainMethod')?.value || '',
            iso_tag: document.getElementById('editIsoTag')?.value || '',
        };

        try {
            const response = await fetch(`/api/samples/${encodeURIComponent(sampleId)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || '保存样本失败');
            this.editModal?.hide();
            showManagementToast('样本记录已保存。', 'success');
            this.loadSamples();
        } catch (error) {
            showManagementToast(error.message || '保存样本失败', 'danger');
        }
    },

    resetFilters() {
        [
            'sampleFilterProjectId', 'sampleFilterProjectName', 'sampleFilterSampleId',
            'sampleFilterSampleName', 'sampleFilterInstitution', 'sampleFilterSequenceId',
            'sampleFilterContainMethod', 'sampleFilterIsoTag', 'sampleFilterSpices',
            'sampleFilterChainFlag', 'sampleFilterIllness'
        ].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        document.getElementById('sampleFilterIsHealthy').value = '';
        document.getElementById('sampleFilterIsPe').value = '';
        const advanced = document.getElementById('sampleAdvancedFilters');
        if (advanced && window.bootstrap) {
            bootstrap.Collapse.getOrCreateInstance(advanced, { toggle: false }).hide();
        }
        this.loadSamples();
    },

    exportSamples() {
        if (!this.samples.length) {
            showManagementToast('当前没有可导出的样本。', 'info');
            return;
        }

        const columns = [
            'project_name', 'sample_id', 'sample_name', 'sequence_id', 'spices',
            'institution', 'chain_flag', 'is_healthy', 'illness', 'is_pe',
            'contain_method', 'iso_tag'
        ];
        const header = columns.join(',');
        const rows = this.samples.map((sample) => columns.map((column) => csvEscape(sample[column] || '')).join(','));
        const csvContent = [header, ...rows].join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = 'sample_registry_export.csv';
        anchor.click();
        URL.revokeObjectURL(url);
        showManagementToast('已导出当前样本结果。', 'success');
    },
};

document.addEventListener('DOMContentLoaded', () => {
    SampleRegistryPage.init();
});
