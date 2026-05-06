/**
 * Settings Management Module
 * Handles application settings, server persistence, and SSH Linux remote sources.
 */
const SettingsManager = {
    defaultSettings: {
        colorScheme: 'viridis',
        figureWidth: 10,
        figureHeight: 8,
        fontSize: 12,
        exportDpi: 300,
        defaultExportFormat: 'png',
        barWidth: 0.8,
        barSpacing: 0.2,
        showValuesDefault: true,
        showAnnotationDefault: true,
        vminDefault: 0,
        vmaxDefault: 1,
        sshRemoteSources: []
    },

    init() {
        this.bindEvents();
        this.loadSettings();
    },

    bindEvents() {
        document.querySelectorAll('input, select').forEach(el => {
            el.addEventListener('change', () => this.updateSummary());
        });

        document.getElementById('saveSettingsBtn')?.addEventListener('click', () => this.saveSettings());
        document.getElementById('resetSettingsBtn')?.addEventListener('click', () => this.resetSettings());
        document.getElementById('clearLocalDataBtn')?.addEventListener('click', () => this.clearLocalData());
        document.getElementById('addRemoteSourceBtn')?.addEventListener('click', () => this.addRemoteSource());
    },

    async loadSettings() {
        let settings = { ...this.defaultSettings };

        try {
            const response = await fetch('/api/config');
            if (response.ok) {
                const payload = await response.json();
                settings = this.mergeSettings(this.mapServerConfigToClient(payload.config || {}));
            } else {
                settings = this.loadSettingsFromLocalStorage();
            }
        } catch (error) {
            settings = this.loadSettingsFromLocalStorage();
        }

        this.populateForm(settings);
        this.renderRemoteSources(settings.sshRemoteSources || []);
        this.updateSummary();
    },

    loadSettingsFromLocalStorage() {
        try {
            const saved = localStorage.getItem('appSettings');
            if (!saved) return { ...this.defaultSettings };
            return this.mergeSettings(JSON.parse(saved));
        } catch (error) {
            return { ...this.defaultSettings };
        }
    },

    mergeSettings(settings) {
        return {
            ...this.defaultSettings,
            ...(settings || {}),
            sshRemoteSources: Array.isArray(settings?.sshRemoteSources)
                ? settings.sshRemoteSources.map(source => this.normalizeRemoteSource(source))
                : []
        };
    },

    mapServerConfigToClient(config) {
        return {
            colorScheme: config.default_color_scheme,
            figureWidth: Array.isArray(config.default_figure_size) ? config.default_figure_size[0] : undefined,
            figureHeight: Array.isArray(config.default_figure_size) ? config.default_figure_size[1] : undefined,
            fontSize: config.default_font_size,
            exportDpi: config.default_dpi,
            defaultExportFormat: config.default_export_format,
            barWidth: config.bar_width,
            barSpacing: config.bar_spacing,
            showValuesDefault: config.bar_show_values,
            showAnnotationDefault: config.heatmap_annotation,
            vminDefault: config.heatmap_vmin,
            vmaxDefault: config.heatmap_vmax,
            sshRemoteSources: config.ssh_remote_sources || []
        };
    },

    mapClientSettingsToServer(settings) {
        return {
            default_color_scheme: settings.colorScheme,
            default_figure_size: [settings.figureWidth, settings.figureHeight],
            default_font_size: settings.fontSize,
            default_dpi: settings.exportDpi,
            default_export_format: settings.defaultExportFormat,
            bar_width: settings.barWidth,
            bar_spacing: settings.barSpacing,
            bar_show_values: settings.showValuesDefault,
            heatmap_annotation: settings.showAnnotationDefault,
            heatmap_vmin: settings.vminDefault,
            heatmap_vmax: settings.vmaxDefault,
            ssh_remote_sources: settings.sshRemoteSources
        };
    },

    populateForm(settings) {
        this.setFormValue('colorScheme', settings.colorScheme);
        this.setFormValue('figureWidth', settings.figureWidth);
        this.setFormValue('figureHeight', settings.figureHeight);
        this.setFormValue('fontSize', settings.fontSize);
        this.setFormValue('exportDpi', settings.exportDpi);
        this.setFormValue('defaultExportFormat', settings.defaultExportFormat);
        this.setFormValue('barWidth', settings.barWidth);
        this.setFormValue('barSpacing', settings.barSpacing);
        this.setCheckboxValue('showValuesDefault', settings.showValuesDefault !== false);
        this.setCheckboxValue('showAnnotationDefault', settings.showAnnotationDefault !== false);
        this.setFormValue('vminDefault', settings.vminDefault);
        this.setFormValue('vmaxDefault', settings.vmaxDefault);
    },

    setFormValue(id, value) {
        const element = document.getElementById(id);
        if (element && value !== undefined && value !== null) {
            element.value = value;
        }
    },

    setCheckboxValue(id, checked) {
        const element = document.getElementById(id);
        if (element) {
            element.checked = !!checked;
        }
    },

    normalizeRemoteSource(source = {}) {
        return {
            id: String(source.id || '').trim(),
            name: String(source.name || '').trim(),
            host: String(source.host || '').trim(),
            port: Number(source.port || 22),
            username: String(source.username || '').trim(),
            auth_type: String(source.auth_type || 'password').trim().toLowerCase() || 'password',
            password: String(source.password || ''),
            key_path: String(source.key_path || ''),
            root_path: String(source.root_path || '/').trim() || '/',
            enabled: source.enabled !== false,
            description: String(source.description || '').trim()
        };
    },

    getRemoteSourcesFromForm() {
        return Array.from(document.querySelectorAll('.remote-source-card')).map(card => {
            const authType = card.querySelector('[data-field="auth_type"]')?.value || 'password';
            return this.normalizeRemoteSource({
                id: card.querySelector('[data-field="id"]')?.value,
                name: card.querySelector('[data-field="name"]')?.value,
                host: card.querySelector('[data-field="host"]')?.value,
                port: card.querySelector('[data-field="port"]')?.value,
                username: card.querySelector('[data-field="username"]')?.value,
                auth_type: authType,
                password: authType === 'password' ? card.querySelector('[data-field="password"]')?.value : '',
                key_path: authType === 'private_key' ? card.querySelector('[data-field="key_path"]')?.value : '',
                root_path: card.querySelector('[data-field="root_path"]')?.value,
                enabled: !!card.querySelector('[data-field="enabled"]')?.checked,
                description: card.querySelector('[data-field="description"]')?.value
            });
        }).filter(source => source.id && source.host);
    },

    renderRemoteSources(sources) {
        const list = document.getElementById('remoteSourcesList');
        const empty = document.getElementById('remoteSourcesEmpty');
        if (!list || !empty) return;

        const normalizedSources = Array.isArray(sources) ? sources.map(source => this.normalizeRemoteSource(source)) : [];
        list.innerHTML = '';
        empty.classList.toggle('d-none', normalizedSources.length > 0);

        normalizedSources.forEach((source, index) => {
            const card = document.createElement('div');
            card.className = 'card remote-source-card';
            card.innerHTML = `
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-center gap-2 mb-3">
                        <div class="fw-semibold">数据源 ${index + 1}</div>
                        <button type="button" class="btn btn-outline-danger btn-sm" data-action="remove-source">删除</button>
                    </div>
                    <div class="row g-3">
                        <div class="col-md-4">
                            <label class="form-label">ID</label>
                            <input type="text" class="form-control" data-field="id" value="${this.escapeHtml(source.id)}" placeholder="linux_server_a">
                        </div>
                        <div class="col-md-4">
                            <label class="form-label">名称</label>
                            <input type="text" class="form-control" data-field="name" value="${this.escapeHtml(source.name)}" placeholder="Linux Server A">
                        </div>
                        <div class="col-md-4">
                            <label class="form-label">根目录</label>
                            <input type="text" class="form-control" data-field="root_path" value="${this.escapeHtml(source.root_path)}" placeholder="/data/repertoire">
                        </div>
                        <div class="col-md-4">
                            <label class="form-label">主机</label>
                            <input type="text" class="form-control" data-field="host" value="${this.escapeHtml(source.host)}" placeholder="10.0.0.8">
                        </div>
                        <div class="col-md-2">
                            <label class="form-label">端口</label>
                            <input type="number" class="form-control" data-field="port" value="${Number.isFinite(source.port) ? source.port : 22}" min="1" max="65535">
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">用户名</label>
                            <input type="text" class="form-control" data-field="username" value="${this.escapeHtml(source.username)}" placeholder="analysis_user">
                        </div>
                        <div class="col-md-3">
                            <label class="form-label">认证方式</label>
                            <select class="form-select" data-field="auth_type">
                                <option value="password"${source.auth_type === 'password' ? ' selected' : ''}>密码</option>
                                <option value="private_key"${source.auth_type === 'private_key' ? ' selected' : ''}>私钥</option>
                            </select>
                        </div>
                        <div class="col-md-6 auth-field auth-password"${source.auth_type !== 'password' ? ' style="display:none;"' : ''}>
                            <label class="form-label">密码</label>
                            <div class="input-group">
                                <input type="password" class="form-control" data-field="password" value="${this.escapeHtml(source.password)}" placeholder="server-side password">
                                <button type="button" class="btn btn-outline-secondary" data-action="toggle-password" title="显示/隐藏密码">
                                    <i class="bi bi-eye"></i>
                                </button>
                            </div>
                        </div>
                        <div class="col-md-6 auth-field auth-key"${source.auth_type !== 'private_key' ? ' style="display:none;"' : ''}>
                            <label class="form-label">私钥路径</label>
                            <input type="text" class="form-control" data-field="key_path" value="${this.escapeHtml(source.key_path)}" placeholder="/home/user/.ssh/id_rsa">
                        </div>
                        <div class="col-md-8">
                            <label class="form-label">说明</label>
                            <input type="text" class="form-control" data-field="description" value="${this.escapeHtml(source.description)}" placeholder="可选说明">
                        </div>
                        <div class="col-md-4 d-flex align-items-end">
                            <div class="form-check mb-2">
                                <input class="form-check-input" type="checkbox" data-field="enabled"${source.enabled ? ' checked' : ''}>
                                <label class="form-check-label">启用该数据源</label>
                            </div>
                        </div>
                    </div>
                </div>
            `;

            card.querySelector('[data-action="remove-source"]')?.addEventListener('click', () => {
                card.remove();
                this.updateRemoteSourcesEmptyState();
                this.updateSummary();
            });

            card.querySelector('[data-action="toggle-password"]')?.addEventListener('click', (event) => {
                const btn = event.currentTarget;
                const input = card.querySelector('[data-field="password"]');
                const icon = btn.querySelector('i');
                if (input && icon) {
                    const isPassword = input.type === 'password';
                    input.type = isPassword ? 'text' : 'password';
                    icon.className = isPassword ? 'bi bi-eye-slash' : 'bi bi-eye';
                }
            });

            card.querySelector('[data-field="auth_type"]')?.addEventListener('change', event => {
                this.toggleAuthFields(card, event.target.value);
                this.updateSummary();
            });

            card.querySelectorAll('input, select').forEach(element => {
                element.addEventListener('change', () => this.updateSummary());
            });

            list.appendChild(card);
            this.toggleAuthFields(card, source.auth_type);
        });

        this.updateRemoteSourcesEmptyState();
    },

    updateRemoteSourcesEmptyState() {
        const empty = document.getElementById('remoteSourcesEmpty');
        if (!empty) return;
        empty.classList.toggle('d-none', document.querySelectorAll('.remote-source-card').length > 0);
    },

    addRemoteSource() {
        const sources = this.getRemoteSourcesFromForm();
        sources.push({
            id: '',
            name: '',
            host: '',
            port: 22,
            username: '',
            auth_type: 'password',
            password: '',
            key_path: '',
            root_path: '/data/repertoire',
            enabled: true,
            description: ''
        });
        this.renderRemoteSources(sources);
        this.updateSummary();
    },

    toggleAuthFields(card, authType) {
        card.querySelector('.auth-password')?.style.setProperty('display', authType === 'password' ? '' : 'none');
        card.querySelector('.auth-key')?.style.setProperty('display', authType === 'private_key' ? '' : 'none');
    },

    collectSettingsFromForm() {
        return this.mergeSettings({
            colorScheme: document.getElementById('colorScheme')?.value || this.defaultSettings.colorScheme,
            figureWidth: parseInt(document.getElementById('figureWidth')?.value || this.defaultSettings.figureWidth, 10),
            figureHeight: parseInt(document.getElementById('figureHeight')?.value || this.defaultSettings.figureHeight, 10),
            fontSize: parseInt(document.getElementById('fontSize')?.value || this.defaultSettings.fontSize, 10),
            exportDpi: parseInt(document.getElementById('exportDpi')?.value || this.defaultSettings.exportDpi, 10),
            defaultExportFormat: document.getElementById('defaultExportFormat')?.value || this.defaultSettings.defaultExportFormat,
            barWidth: parseFloat(document.getElementById('barWidth')?.value || this.defaultSettings.barWidth),
            barSpacing: parseFloat(document.getElementById('barSpacing')?.value || this.defaultSettings.barSpacing),
            showValuesDefault: document.getElementById('showValuesDefault')?.checked !== false,
            showAnnotationDefault: document.getElementById('showAnnotationDefault')?.checked !== false,
            vminDefault: parseFloat(document.getElementById('vminDefault')?.value || this.defaultSettings.vminDefault),
            vmaxDefault: parseFloat(document.getElementById('vmaxDefault')?.value || this.defaultSettings.vmaxDefault),
            sshRemoteSources: this.getRemoteSourcesFromForm()
        });
    },

    async saveSettings() {
        const settings = this.collectSettingsFromForm();

        // Client-side validation for SSH remote sources
        const sshErrors = this.validateRemoteSources(settings.sshRemoteSources);
        if (sshErrors) {
            this.showToast(sshErrors, 'danger');
            return;
        }

        localStorage.setItem('appSettings', JSON.stringify(settings));

        try {
            await this.saveSettingsToServer(settings);
            this.updateSummary();
            this.showToast('设置已保存', 'success');
        } catch (error) {
            this.showToast(error.message || '保存设置失败', 'danger');
        }
    },

    validateRemoteSources(sources) {
        if (!Array.isArray(sources) || sources.length === 0) return null;
        const parts = [];
        sources.forEach((source, index) => {
            const label = source.name || source.id || `数据源 ${index + 1}`;
            if (source.auth_type === 'password' && !source.password) {
                parts.push(`${label}: 密码不能为空`);
            }
            if (source.auth_type === 'private_key' && !source.key_path) {
                parts.push(`${label}: 私钥路径不能为空`);
            }
            if (!source.root_path || !source.root_path.startsWith('/')) {
                parts.push(`${label}: 根目录必须以 / 开头`);
            }
            if (!source.name) {
                parts.push(`${label}: 名称不能为空`);
            }
            if (!source.username) {
                parts.push(`${label}: 用户名不能为空`);
            }
        });
        return parts.length ? 'SSH 数据源配置错误:\n' + parts.join('\n') : null;
    },

    async saveSettingsToServer(settings) {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                config_id: 'default',
                config: this.mapClientSettingsToServer(settings)
            })
        });

        const payload = await response.json();
        if (!response.ok) {
            let message = payload.message || '保存设置失败';
            const validationErrors = payload.details?.validation_errors;
            if (validationErrors) {
                const parts = [];
                for (const [field, fieldErrors] of Object.entries(validationErrors)) {
                    if (field === 'ssh_remote_sources' && Array.isArray(fieldErrors)) {
                        parts.push('SSH 数据源: ' + fieldErrors.join('; '));
                    } else if (Array.isArray(fieldErrors)) {
                        parts.push(field + ': ' + fieldErrors.join(', '));
                    } else {
                        parts.push(field + ': ' + fieldErrors);
                    }
                }
                if (parts.length) message = parts.join('\n');
            }
            throw new Error(message);
        }
        return payload;
    },

    async resetSettings() {
        if (!confirm('确定要恢复默认设置吗？')) return;

        try {
            const response = await fetch('/api/config/reset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config_id: 'default' })
            });
            const payload = await response.json();
            if (!response.ok || !payload.success) {
                throw new Error(payload.message || '恢复默认设置失败');
            }

            localStorage.removeItem('appSettings');
            const settings = this.mergeSettings(this.mapServerConfigToClient(payload.config || {}));
            this.populateForm(settings);
            this.renderRemoteSources(settings.sshRemoteSources || []);
            this.updateSummary();
            this.showToast('已恢复默认设置', 'info');
        } catch (error) {
            this.showToast(error.message || '恢复默认设置失败', 'danger');
        }
    },

    clearLocalData() {
        if (!confirm('确定要清除浏览器本地缓存吗？这不会删除服务端已保存的系统设置。')) return;
        localStorage.clear();
        this.showToast('本地缓存已清除', 'warning');
    },

    updateSummary() {
        const settings = this.collectSettingsFromForm();
        const colorScheme = document.getElementById('summaryColorScheme');
        const size = document.getElementById('summarySize');
        const dpi = document.getElementById('summaryDpi');
        const remoteCount = document.getElementById('summaryRemoteSources');
        const remoteRow = document.getElementById('summaryRemoteSourcesRow');

        if (colorScheme) colorScheme.textContent = settings.colorScheme || '-';
        if (size) size.textContent = `${settings.figureWidth} x ${settings.figureHeight} 英寸`;
        if (dpi) dpi.textContent = `${settings.exportDpi} DPI`;
        if (remoteCount) {
            const enabledCount = settings.sshRemoteSources.filter(source => source.enabled !== false).length;
            remoteCount.textContent = `${settings.sshRemoteSources.length} 个，启用 ${enabledCount} 个`;
        }
        if (remoteRow) {
            remoteRow.classList.remove('d-none');
        }
    },

    escapeHtml(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    },

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `alert alert-${type} position-fixed bottom-0 end-0 m-3`;
        toast.style.zIndex = '9999';

        const icon = type === 'success'
            ? 'check-circle'
            : type === 'warning'
                ? 'exclamation-triangle'
                : type === 'danger'
                    ? 'x-circle'
                    : 'info-circle';

        toast.innerHTML = `<i class="bi bi-${icon} me-2"></i>${this.escapeHtml(message)}`;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('visualizationSettings') || document.querySelector('.settings-page')) {
        SettingsManager.init();
    }
});

window.saveSettings = () => SettingsManager.saveSettings();
window.resetSettings = () => SettingsManager.resetSettings();
window.clearLocalData = () => SettingsManager.clearLocalData();
