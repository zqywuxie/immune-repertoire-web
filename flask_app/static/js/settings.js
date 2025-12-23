/**
 * Settings Management Module
 * Handles application settings, local storage, and server synchronization
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
        this.loadSettings();
        this.bindEvents();
    },

    bindEvents() {
        // Add change listeners to update summary
        document.querySelectorAll('input, select').forEach(el => {
            el.addEventListener('change', () => this.updateSummary());
        });

        // Bind save and reset buttons
        const saveBtn = document.querySelector('[onclick="saveSettings()"]');
        const resetBtn = document.querySelector('[onclick="resetSettings()"]');
        const clearBtn = document.querySelector('[onclick="clearLocalData()"]');

        if (saveBtn) {
            saveBtn.removeAttribute('onclick');
            saveBtn.addEventListener('click', () => this.saveSettings());
        }

        if (resetBtn) {
            resetBtn.removeAttribute('onclick');
            resetBtn.addEventListener('click', () => this.resetSettings());
        }

        if (clearBtn) {
            clearBtn.removeAttribute('onclick');
            clearBtn.addEventListener('click', () => this.clearLocalData());
        }
    },

    loadSettings() {
        const saved = localStorage.getItem('appSettings');
        const settings = saved ? JSON.parse(saved) : this.defaultSettings;

        this.setFormValue('colorScheme', settings.colorScheme || this.defaultSettings.colorScheme);
        this.setFormValue('figureWidth', settings.figureWidth || this.defaultSettings.figureWidth);
        this.setFormValue('figureHeight', settings.figureHeight || this.defaultSettings.figureHeight);
        this.setFormValue('fontSize', settings.fontSize || this.defaultSettings.fontSize);
        this.setFormValue('exportDpi', settings.exportDpi || this.defaultSettings.exportDpi);
        this.setFormValue('defaultExportFormat', settings.defaultExportFormat || this.defaultSettings.defaultExportFormat);
        this.setFormValue('barWidth', settings.barWidth || this.defaultSettings.barWidth);
        this.setFormValue('barSpacing', settings.barSpacing || this.defaultSettings.barSpacing);
        this.setCheckboxValue('showValuesDefault', settings.showValuesDefault !== false);
        this.setCheckboxValue('showAnnotationDefault', settings.showAnnotationDefault !== false);
        this.setFormValue('vminDefault', settings.vminDefault ?? this.defaultSettings.vminDefault);
        this.setFormValue('vmaxDefault', settings.vmaxDefault ?? this.defaultSettings.vmaxDefault);

        this.updateSummary();
    },

    setFormValue(id, value) {
        const element = document.getElementById(id);
        if (element) element.value = value;
    },

    setCheckboxValue(id, checked) {
        const element = document.getElementById(id);
        if (element) element.checked = checked;
    },

    async saveSettings() {
        const settings = {
            colorScheme: document.getElementById('colorScheme')?.value || this.defaultSettings.colorScheme,
            figureWidth: parseInt(document.getElementById('figureWidth')?.value || this.defaultSettings.figureWidth),
            figureHeight: parseInt(document.getElementById('figureHeight')?.value || this.defaultSettings.figureHeight),
            fontSize: parseInt(document.getElementById('fontSize')?.value || this.defaultSettings.fontSize),
            exportDpi: parseInt(document.getElementById('exportDpi')?.value || this.defaultSettings.exportDpi),
            defaultExportFormat: document.getElementById('defaultExportFormat')?.value || this.defaultSettings.defaultExportFormat,
            barWidth: parseFloat(document.getElementById('barWidth')?.value || this.defaultSettings.barWidth),
            barSpacing: parseFloat(document.getElementById('barSpacing')?.value || this.defaultSettings.barSpacing),
            showValuesDefault: document.getElementById('showValuesDefault')?.checked !== false,
            showAnnotationDefault: document.getElementById('showAnnotationDefault')?.checked !== false,
            vminDefault: parseFloat(document.getElementById('vminDefault')?.value || this.defaultSettings.vminDefault),
            vmaxDefault: parseFloat(document.getElementById('vmaxDefault')?.value || this.defaultSettings.vmaxDefault)
        };

        localStorage.setItem('appSettings', JSON.stringify(settings));

        // Also save to server for persistence across devices
        await this.saveSettingsToServer(settings);

        this.updateSummary();
        this.showToast('设置已保存', 'success');
    },

    async saveSettingsToServer(settings) {
        try {
            await fetch('/api/config/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });
        } catch (error) {
            console.error('Failed to save settings to server:', error);
        }
    },

    resetSettings() {
        if (!confirm('确定要恢复默认设置吗？')) return;

        localStorage.removeItem('appSettings');
        this.loadSettings();
        this.showToast('已恢复默认设置', 'info');
    },

    clearLocalData() {
        if (!confirm('确定要清除所有本地数据吗？这将清除保存的设置和缓存。')) return;

        localStorage.clear();
        this.loadSettings();
        this.showToast('本地数据已清除', 'warning');
    },

    updateSummary() {
        const colorScheme = document.getElementById('summaryColorScheme');
        const size = document.getElementById('summarySize');
        const dpi = document.getElementById('summaryDpi');

        if (colorScheme) {
            colorScheme.textContent = document.getElementById('colorScheme')?.value || '-';
        }

        if (size) {
            const width = document.getElementById('figureWidth')?.value || '10';
            const height = document.getElementById('figureHeight')?.value || '8';
            size.textContent = `${width} × ${height} 英寸`;
        }

        if (dpi) {
            dpi.textContent = (document.getElementById('exportDpi')?.value || '300') + ' DPI';
        }
    },

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `alert alert-${type} position-fixed bottom-0 end-0 m-3`;
        toast.style.zIndex = '9999';

        const icon = type === 'success' ? 'check-circle' :
            type === 'warning' ? 'exclamation-triangle' : 'info-circle';

        toast.innerHTML = `<i class="bi bi-${icon} me-2"></i>${message}`;
        document.body.appendChild(toast);

        setTimeout(() => toast.remove(), 3000);
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('visualizationSettings') || document.querySelector('.settings-page')) {
        SettingsManager.init();
    }
});

// Global functions for backward compatibility
window.saveSettings = () => SettingsManager.saveSettings();
window.resetSettings = () => SettingsManager.resetSettings();
window.clearLocalData = () => SettingsManager.clearLocalData();
