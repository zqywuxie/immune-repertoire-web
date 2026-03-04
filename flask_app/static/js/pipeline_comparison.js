const PipelineComparisonPage = {
    storageKey: 'pipeline_comparison_page_config_v1',
    isRunning: false,

    init() {
        this.bindEvents();
        this.loadConfig();
        this.log('Pipeline comparison page ready.');
    },

    bindEvents() {
        document.getElementById('pcGenerateBtn')?.addEventListener('click', () => this.generate());
        document.getElementById('pcSaveConfigBtn')?.addEventListener('click', () => this.saveConfig(true));
        document.getElementById('pcClearLogBtn')?.addEventListener('click', () => this.clearLog());
    },

    parseCsvList(raw) {
        return (raw || '')
            .split(',')
            .map(item => item.trim())
            .filter(Boolean);
    },

    log(message) {
        const el = document.getElementById('pcLog');
        if (!el) return;
        const now = new Date().toLocaleTimeString('en-GB', { hour12: false });
        const prefix = `[${now}] `;
        if (!el.textContent || el.textContent === 'Idle.') {
            el.textContent = `${prefix}${message}`;
        } else {
            el.textContent += `\n${prefix}${message}`;
        }
        el.scrollTop = el.scrollHeight;
    },

    clearLog() {
        const el = document.getElementById('pcLog');
        if (el) el.textContent = 'Idle.';
    },

    setRunning(running) {
        this.isRunning = running;
        const btn = document.getElementById('pcGenerateBtn');
        if (!btn) return;
        btn.disabled = running;
        btn.innerHTML = running
            ? '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Running...'
            : '<i class="bi bi-play-fill me-1"></i>Run Pipeline Comparison';
    },

    collectPayload() {
        const basePath = (document.getElementById('pcBasePath')?.value || '').trim();
        if (!basePath) {
            throw new Error('Root folder is required.');
        }

        const pipelines = this.parseCsvList(document.getElementById('pcPipelines')?.value || '')
            .map(item => item.toUpperCase());
        if (pipelines.length < 2) {
            throw new Error('At least 2 pipelines are required.');
        }

        const samples = this.parseCsvList(document.getElementById('pcSamples')?.value || '');
        const chains = this.parseCsvList(document.getElementById('pcChains')?.value || '')
            .map(item => item.toUpperCase());
        const outputName = (document.getElementById('pcOutputName')?.value || '').trim();

        return {
            base_path: basePath,
            pipelines,
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

    saveConfig(showAlert = false) {
        const payload = this.collectPayload();
        localStorage.setItem(this.storageKey, JSON.stringify(payload));
        this.log('Parameters saved to local storage.');
        if (showAlert) {
            alert('Parameters saved.');
        }
    },

    loadConfig() {
        const raw = localStorage.getItem(this.storageKey);
        if (!raw) return;

        try {
            const cfg = JSON.parse(raw);
            if (cfg.base_path) document.getElementById('pcBasePath').value = cfg.base_path;
            if (Array.isArray(cfg.pipelines)) document.getElementById('pcPipelines').value = cfg.pipelines.join(',');
            if (Array.isArray(cfg.samples)) document.getElementById('pcSamples').value = cfg.samples.join(',');
            if (Array.isArray(cfg.selected_chains)) document.getElementById('pcChains').value = cfg.selected_chains.join(',');
            if (cfg.output_name) document.getElementById('pcOutputName').value = cfg.output_name;
            if (typeof cfg.enable_heatmap === 'boolean') document.getElementById('pcEnableHeatmap').checked = cfg.enable_heatmap;
            if (typeof cfg.enable_venn === 'boolean') document.getElementById('pcEnableVenn').checked = cfg.enable_venn;
            if (typeof cfg.enable_html_report === 'boolean') document.getElementById('pcEnableHtmlReport').checked = cfg.enable_html_report;
            if (typeof cfg.include_cdr3_analysis === 'boolean') document.getElementById('pcIncludeCdr3').checked = cfg.include_cdr3_analysis;
            if (typeof cfg.embed_images === 'boolean') document.getElementById('pcEmbedImages').checked = cfg.embed_images;
            this.log('Loaded parameters from local storage.');
        } catch (error) {
            this.log(`Load config failed: ${error.message}`);
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
        summary.textContent = `Pipelines: ${pipelines} | Samples: ${samples} | Chains: ${chains}`;

        resultCard.style.display = '';
    },

    async generate() {
        if (this.isRunning) return;

        let payload;
        try {
            payload = this.collectPayload();
        } catch (error) {
            alert(error.message || 'Validation failed.');
            return;
        }

        this.setRunning(true);
        this.log(`Start run with base_path=${payload.base_path}`);

        try {
            localStorage.setItem(this.storageKey, JSON.stringify(payload));
            const response = await fetch('/api/auto-heatmap/generate-pipeline-report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();
            if (!response.ok || !data.success) {
                const errMsg = data.message || 'Generation failed.';
                this.log(`Failed: ${errMsg}`);
                throw new Error(errMsg);
            }

            this.log(`Done. job_id=${data.job_id}`);
            if (data.report_url) {
                this.log(`Report URL: ${data.report_url}`);
            }
            this.renderResult(data);

            if (data.report_url) {
                window.open(data.report_url, '_blank');
            }
        } catch (error) {
            alert(error.message || 'Generation failed.');
        } finally {
            this.setRunning(false);
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    PipelineComparisonPage.init();
});
