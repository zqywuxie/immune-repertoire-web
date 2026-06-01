(function () {
    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    function getContainer() {
        return document.querySelector('.container-fluid.py-4');
    }

    function defaultShowError(message) {
        window.alert(message);
    }

    const AnalysisWorkspace = {
        enhance(target, config = {}) {
            if (!target) return target;

            const workspaceConfig = {
                analysisType: config.analysisType || '',
                displayName: config.displayName || 'Analysis',
                projectResultType: config.projectResultType || config.analysisType || '',
            };

            Object.assign(target, {
                workspaceConfig,
                projectContext: null,

                escapeHtml,

                getProjectContext() {
                    if (this.projectContext) return this.projectContext;
                    const params = new URLSearchParams(window.location.search);
                    this.projectContext = {
                        projectId: params.get('project_id') || '',
                        projectName: params.get('project_name') || '',
                        basePath: params.get('base_path') || '',
                        autoScan: params.get('auto_scan') === '1',
                    };
                    return this.projectContext;
                },

                initializeFromProjectContext() {
                    const context = this.getProjectContext();
                    if (!context.projectId) return;

                    const container = getContainer();
                    if (container && !container.querySelector('[data-project-context-banner]')) {
                        const banner = document.createElement('div');
                        banner.className = 'alert alert-primary d-flex justify-content-between align-items-center gap-3';
                        banner.setAttribute('data-project-context-banner', '1');
                        banner.innerHTML = `
                            <div>
                                <div class="fw-semibold">Project workspace enabled</div>
                                <div class="small">Current project: ${escapeHtml(context.projectName || context.projectId)}. ${escapeHtml(this.workspaceConfig.displayName)} will read data directly from the project asset directory.</div>
                            </div>
                            <a class="btn btn-sm btn-outline-primary" href="/projects/${encodeURIComponent(context.projectId)}">Back to project</a>
                        `;
                        container.insertBefore(banner, container.firstChild);
                    }

                    const basePathInput = document.getElementById('basePath');
                    if (basePathInput && context.basePath) {
                        basePathInput.value = context.basePath;
                    }

                    if (context.autoScan && context.basePath && !this._workspaceAutoScanTriggered) {
                        this._workspaceAutoScanTriggered = true;
                        this.scanFolder?.();
                    }
                },

                async registerProjectResult(payload) {
                    const context = this.getProjectContext ? this.getProjectContext() : { projectId: '' };
                    if (!context.projectId || !this.workspaceConfig.projectResultType) return;

                    try {
                        await fetch(`/api/projects/${encodeURIComponent(context.projectId)}/analysis/${encodeURIComponent(this.workspaceConfig.projectResultType)}/register-result`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(payload || {}),
                        });
                    } catch (error) {
                        console.warn(`Failed to register ${this.workspaceConfig.projectResultType} result for project:`, error);
                    }
                },

            });

            return target;
        },
    };

    window.AnalysisWorkspace = AnalysisWorkspace;
})();
