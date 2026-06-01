/**
 * Settings Management Module
 * Handles application settings and server persistence.
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
        vmaxDefault: 1
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
            ...(settings || {})
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
            vmaxDefault: config.heatmap_vmax
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
            heatmap_vmax: settings.vmaxDefault
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
            vmaxDefault: parseFloat(document.getElementById('vmaxDefault')?.value || this.defaultSettings.vmaxDefault)
        });
    },

    async saveSettings() {
        const settings = this.collectSettingsFromForm();

        localStorage.setItem('appSettings', JSON.stringify(settings));

        try {
            await this.saveSettingsToServer(settings);
            this.updateSummary();
            this.showToast('设置已保存', 'success');
        } catch (error) {
            this.showToast(error.message || '保存设置失败', 'danger');
        }
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
                    if (Array.isArray(fieldErrors)) {
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

        if (colorScheme) colorScheme.textContent = settings.colorScheme || '-';
        if (size) size.textContent = `${settings.figureWidth} x ${settings.figureHeight} 英寸`;
        if (dpi) dpi.textContent = `${settings.exportDpi} DPI`;
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
