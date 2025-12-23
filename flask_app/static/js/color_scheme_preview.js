/**
 * Color Scheme Preview Component
 * Displays color scheme previews for visualization selection
 * Requirements: 13.2, 13.3, 13.4, 13.5
 */

class ColorSchemePreview {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            throw new Error(`Container element not found: ${containerId}`);
        }

        this.options = {
            onChange: options.onChange || null,
            showDescription: options.showDescription !== false,
            barHeight: options.barHeight || 30,
            ...options
        };

        this.schemes = [];
        this.currentScheme = null;

        this.init();
    }

    async init() {
        await this.loadColorSchemes();
        this.render();
    }

    async loadColorSchemes() {
        try {
            const response = await fetch('/api/color-schemes');
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || 'Failed to load color schemes');
            }

            this.schemes = data.schemes;
            this.defaultScheme = data.default;
            this.currentScheme = this.defaultScheme;

        } catch (error) {
            console.error('Error loading color schemes:', error);
            this.showError('加载颜色方案失败: ' + error.message);
        }
    }

    render() {
        if (this.schemes.length === 0) {
            this.container.innerHTML = '<p class="text-muted">没有可用的颜色方案</p>';
            return;
        }

        this.container.innerHTML = `
            <div class="color-scheme-selector">
                <div class="mb-3">
                    <label class="form-label">颜色方案:</label>
                    <select class="form-select" id="colorSchemeSelect">
                        ${this.schemes.map(scheme => `
                            <option value="${scheme.name}" ${scheme.name === this.currentScheme ? 'selected' : ''}>
                                ${scheme.display_name}
                            </option>
                        `).join('')}
                    </select>
                </div>
                <div id="colorPreviewContainer">
                    <!-- Preview will be rendered here -->
                </div>
            </div>
        `;

        this.bindEvents();
        this.displayPreview(this.currentScheme);
    }

    bindEvents() {
        const select = document.getElementById('colorSchemeSelect');
        if (select) {
            select.addEventListener('change', (e) => {
                this.currentScheme = e.target.value;
                this.displayPreview(this.currentScheme);

                if (this.options.onChange) {
                    this.options.onChange(this.currentScheme);
                }
            });
        }
    }

    displayPreview(schemeName) {
        const scheme = this.schemes.find(s => s.name === schemeName);
        if (!scheme) {
            console.error('Scheme not found:', schemeName);
            return;
        }

        const container = document.getElementById('colorPreviewContainer');
        if (!container) return;

        const colors = this.getSchemeColors(schemeName);

        container.innerHTML = `
            <div class="color-preview">
                <div class="preview-label">预览:</div>
                <div class="color-bars" style="height: ${this.options.barHeight}px;">
                    ${colors.map(color => `
                        <div class="color-bar" style="background-color: ${color}; flex: 1;" title="${color}"></div>
                    `).join('')}
                </div>
                ${this.options.showDescription ? `
                    <div class="scheme-description mt-2">
                        <small class="text-muted">
                            <i class="bi bi-info-circle me-1"></i>
                            ${scheme.description}
                        </small>
                    </div>
                ` : ''}
            </div>
        `;
    }

    getSchemeColors(schemeName) {
        const scheme = this.schemes.find(s => s.name === schemeName);
        return scheme ? scheme.colors : [];
    }

    getCurrentScheme() {
        return this.currentScheme;
    }

    setScheme(schemeName) {
        if (!this.schemes.find(s => s.name === schemeName)) {
            console.error('Scheme not found:', schemeName);
            return;
        }

        this.currentScheme = schemeName;

        const select = document.getElementById('colorSchemeSelect');
        if (select) {
            select.value = schemeName;
        }

        this.displayPreview(schemeName);
    }

    renderPreviewChart(colors) {
        // Create a simple bar chart preview
        const container = document.getElementById('colorPreviewContainer');
        if (!container) return;

        const barWidth = 100 / colors.length;

        container.innerHTML = `
            <div class="color-preview-chart">
                <div class="chart-bars" style="display: flex; height: 100px; align-items: flex-end;">
                    ${colors.map((color, index) => {
            const height = 30 + (index * 10) % 70; // Varying heights for visual interest
            return `
                            <div class="chart-bar" style="
                                background-color: ${color};
                                width: ${barWidth}%;
                                height: ${height}%;
                                margin: 0 1px;
                            "></div>
                        `;
        }).join('')}
                </div>
            </div>
        `;
    }

    showError(message) {
        this.container.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <i class="bi bi-exclamation-triangle me-2"></i>
                ${this.escapeHtml(message)}
            </div>
        `;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ColorSchemePreview;
}
