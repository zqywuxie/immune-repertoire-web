const AdvancedAnalysisPage = {
    moduleConfig: {
        'pipeline-comparison': {
            title: 'Pipeline Comparison',
            badge: 'Pipeline',
            description: 'Compare multiple pipeline folders and generate heatmap, Venn, and HTML reports.',
            path: '/analysis/pipeline-comparison'
        },
        'db-alignment': {
            title: 'DB Alignment',
            badge: 'Integrated',
            description: 'Run VDJdb / McPAS-TCR alignment with profile merge and pathology filtering.',
            path: '/analysis/script-hub'
        }
    },
    activeModule: 'pipeline-comparison',

    init() {
        this.bindEvents();
        this.activeModule = this.resolveInitialModule();
        this.activateModule(this.activeModule, false);
    },

    bindEvents() {
        document.querySelectorAll('[data-module]').forEach((button) => {
            button.addEventListener('click', () => this.activateModule(button.dataset.module || 'pipeline-comparison'));
        });
    },

    resolveInitialModule() {
        const params = new URLSearchParams(window.location.search);
        const requested = (params.get('active_module') || '').trim().toLowerCase();
        return this.moduleConfig[requested] ? requested : 'pipeline-comparison';
    },

    buildModuleUrl(moduleName, embedded = true) {
        const config = this.moduleConfig[moduleName] || this.moduleConfig['pipeline-comparison'];
        const params = new URLSearchParams(window.location.search);
        if (embedded) params.set('embedded', '1');
        else params.delete('embedded');

        if (moduleName === 'db-alignment') {
            params.set('active_module', 'db-alignment');
        } else {
            params.delete('active_module');
        }

        return `${config.path}?${params.toString()}`;
    },

    activateModule(moduleName, pushHistory = true) {
        const config = this.moduleConfig[moduleName] || this.moduleConfig['pipeline-comparison'];
        this.activeModule = moduleName in this.moduleConfig ? moduleName : 'pipeline-comparison';

        document.querySelectorAll('[data-module]').forEach((button) => {
            button.classList.toggle('is-active', button.dataset.module === this.activeModule);
        });

        const badge = document.getElementById('advancedModuleBadge');
        const title = document.getElementById('advancedModuleTitle');
        const description = document.getElementById('advancedModuleDescription');
        const frame = document.getElementById('advancedModuleFrame');
        const openBtn = document.getElementById('advancedOpenModuleBtn');
        const nextUrl = this.buildModuleUrl(this.activeModule, true);
        const fullUrl = this.buildModuleUrl(this.activeModule, false);

        if (badge) badge.textContent = config.badge;
        if (title) title.textContent = config.title;
        if (description) description.textContent = config.description;
        if (frame) frame.src = nextUrl;
        if (openBtn) openBtn.href = fullUrl;

        if (pushHistory) {
            const outerUrl = new URL(window.location.href);
            outerUrl.searchParams.set('active_module', this.activeModule);
            window.history.replaceState({}, '', outerUrl);
        }
    }
};

document.addEventListener('DOMContentLoaded', () => {
    AdvancedAnalysisPage.init();
});
