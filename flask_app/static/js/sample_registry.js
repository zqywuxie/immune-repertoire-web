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

        try {
            const response = await fetch(`/api/samples?${params.toString()}`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.message || '加载样本失败');
            this.samples = data.samples || [];
            this.renderSamples();
        } catch (error) {
            if (errorAlert) {
                errorAlert.textContent = error.message || '加载样本失败';
                errorAlert.classList.remove('d-none');
            }
        }
    },

    renderSamples() {
        const tbody = document.getElementById('samplesTableBody');
        if (!this.samples.length) {
            tbody.innerHTML = '<tr><td colspan="12" class="text-center text-muted py-4">没有匹配的样本记录。</td></tr>';
            return;
        }

        tbody.innerHTML = this.samples.map((sample) => `
            <tr>
              <td>${escapeHtml(sample.project_name || '-')}</td>
              <td>${escapeHtml(sample.sample_id || '-')}</td>
              <td>${escapeHtml(sample.sample_name || '-')}</td>
              <td>${escapeHtml(sample.sequence_id || '-')}</td>
              <td>${escapeHtml(sample.spices || '-')}</td>
              <td>${escapeHtml(sample.chain_flag || '-')}</td>
              <td>${escapeHtml(sample.is_healthy || '-')}</td>
              <td>${escapeHtml(sample.illness || '-')}</td>
              <td>${escapeHtml(sample.is_pe || '-')}</td>
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
            this.loadSamples();
        } catch (error) {
            alert(error.message || '保存样本失败');
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
        this.loadSamples();
    },

    exportSamples() {
        if (!this.samples.length) {
            alert('当前没有可导出的样本。');
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
    },
};

document.addEventListener('DOMContentLoaded', () => {
    SampleRegistryPage.init();
});
