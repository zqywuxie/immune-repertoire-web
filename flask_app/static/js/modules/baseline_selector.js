/**
 * Baseline Selector Module for Immune Repertoire Analysis Web Application
 * Provides functionality for selecting baseline samples or groups for percentage difference calculations.
 * 
 * Requirements: 17.1, 17.3
 */

const BaselineSelector = {
    baselineType: null,    // 'sample' or 'group'
    baselineId: null,      // Selected sample ID or group ID
    baselineName: null,    // Display name of the baseline
    samples: [],           // Available samples
    groups: [],            // Available groups
    fileId: null,          // Associated file ID
    metricFields: [],      // Metric fields for calculation
    sampleColumn: 'sample', // Sample column name

    // Cached baseline values
    baselineValues: {},

    // Previous baseline for change tracking
    previousBaseline: null,

    // Show baseline change notification
    showChangeNotification: true,

    // Callback for baseline changes
    onBaselineChangeCallback: null,

    // Quick switch history (last 5 baselines)
    baselineHistory: [],
    maxHistorySize: 5,

    /**
     * Initialize the module
     * @param {Object} options - Configuration options
     * @param {Array} options.samples - List of available sample identifiers
     * @param {Array} options.groups - List of available groups
     * @param {string} options.fileId - Associated file ID
     * @param {Array} options.metricFields - Metric fields for calculation
     * @param {string} options.sampleColumn - Sample column name (default: 'sample')
     */
    init(options) {
        this.samples = options.samples || [];
        this.groups = options.groups || [];
        this.fileId = options.fileId || null;
        this.metricFields = options.metricFields || [];
        this.sampleColumn = options.sampleColumn || 'sample';
        this.baselineType = null;
        this.baselineId = null;
        this.baselineName = null;
        this.baselineValues = {};
    },

    /**
     * Set the callback for baseline changes
     * @param {Function} callback - Callback function(baselineType, baselineId, baselineValues)
     */
    onBaselineChange(callback) {
        this.onBaselineChangeCallback = callback;
    },

    /**
     * Render the baseline selector UI
     * @param {string} containerId - Container element ID
     */
    renderBaselineSelector(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const html = `
            <div class="baseline-selector-container">
                <div class="mb-3">
                    <label class="form-label fw-semibold">Baseline Selection</label>
                    <p class="text-muted small mb-2">Select a sample or group as the baseline for percentage difference calculations.</p>
                </div>
                
                <div class="baseline-type-selector mb-3">
                    <div class="btn-group w-100" role="group">
                        <input type="radio" class="btn-check" name="baselineType" id="baselineTypeSample" 
                               value="sample" ${this.baselineType === 'sample' ? 'checked' : ''}
                               onchange="BaselineSelector.setBaselineType('sample')">
                        <label class="btn btn-outline-primary" for="baselineTypeSample">
                            <i class="bi bi-person"></i> Sample
                        </label>
                        
                        <input type="radio" class="btn-check" name="baselineType" id="baselineTypeGroup" 
                               value="group" ${this.baselineType === 'group' ? 'checked' : ''}
                               onchange="BaselineSelector.setBaselineType('group')">
                        <label class="btn btn-outline-primary" for="baselineTypeGroup">
                            <i class="bi bi-people"></i> Group
                        </label>
                    </div>
                </div>
                
                <div class="baseline-selection mb-3" id="baselineSelectionContainer">
                    ${this.renderSelectionDropdown()}
                </div>
                
                <div class="baseline-info" id="baselineInfoContainer">
                    ${this.renderBaselineInfo()}
                </div>
                
                <div class="baseline-quick-switch-container mt-3" id="baselineQuickSwitchContainer">
                    ${this.renderQuickSwitch()}
                </div>
            </div>
        `;

        container.innerHTML = html;
    },

    /**
     * Render quick switch buttons for recent baselines
     */
    renderQuickSwitch() {
        if (this.baselineHistory.length === 0) {
            return '';
        }

        return `
            <div class="quick-switch-section">
                <label class="form-label small text-muted mb-1">Quick Switch (Recent)</label>
                <div class="baseline-quick-switch">
                    ${this.baselineHistory.map(item => {
            const isActive = item.type === this.baselineType && item.id === this.baselineId;
            return `
                            <button type="button" 
                                    class="btn btn-sm btn-outline-secondary ${isActive ? 'active' : ''}"
                                    onclick="BaselineSelector.quickSwitchTo('${item.type}', '${item.id}')"
                                    title="${item.type === 'sample' ? 'Sample' : 'Group'}: ${this.escapeHtml(item.name)}">
                                <i class="bi bi-${item.type === 'sample' ? 'person' : 'people'}"></i>
                                ${this.escapeHtml(this.truncateName(item.name, 15))}
                            </button>
                        `;
        }).join('')}
                </div>
            </div>
        `;
    },

    /**
     * Truncate name for display
     * @param {string} name - Name to truncate
     * @param {number} maxLength - Maximum length
     * @returns {string} Truncated name
     */
    truncateName(name, maxLength) {
        if (!name || name.length <= maxLength) return name;
        return name.substring(0, maxLength - 3) + '...';
    },

    /**
     * Quick switch to a previous baseline
     * @param {string} type - Baseline type
     * @param {string} id - Baseline ID
     */
    async quickSwitchTo(type, id) {
        await this.setBaseline(type, id);
        this.refreshUI();
    },

    /**
     * Add current baseline to history
     */
    addToHistory() {
        if (!this.baselineType || !this.baselineId) return;

        const entry = {
            type: this.baselineType,
            id: this.baselineId,
            name: this.baselineName
        };

        // Remove if already exists
        this.baselineHistory = this.baselineHistory.filter(
            item => !(item.type === entry.type && item.id === entry.id)
        );

        // Add to front
        this.baselineHistory.unshift(entry);

        // Limit size
        if (this.baselineHistory.length > this.maxHistorySize) {
            this.baselineHistory = this.baselineHistory.slice(0, this.maxHistorySize);
        }
    },

    /**
     * Refresh the entire UI
     */
    refreshUI() {
        const selectionContainer = document.getElementById('baselineSelectionContainer');
        if (selectionContainer) {
            selectionContainer.innerHTML = this.renderSelectionDropdown();
        }

        const infoContainer = document.getElementById('baselineInfoContainer');
        if (infoContainer) {
            infoContainer.innerHTML = this.renderBaselineInfo();
        }

        const quickSwitchContainer = document.getElementById('baselineQuickSwitchContainer');
        if (quickSwitchContainer) {
            quickSwitchContainer.innerHTML = this.renderQuickSwitch();
        }

        // Update radio buttons
        const sampleRadio = document.getElementById('baselineTypeSample');
        const groupRadio = document.getElementById('baselineTypeGroup');
        if (sampleRadio) sampleRadio.checked = this.baselineType === 'sample';
        if (groupRadio) groupRadio.checked = this.baselineType === 'group';
    },

    /**
     * Render the selection dropdown based on baseline type
     */
    renderSelectionDropdown() {
        if (!this.baselineType) {
            return '<p class="text-muted small">Please select a baseline type first.</p>';
        }

        const items = this.baselineType === 'sample' ? this.samples : this.groups;

        if (items.length === 0) {
            const itemType = this.baselineType === 'sample' ? 'samples' : 'groups';
            return `<p class="text-muted small">No ${itemType} available.</p>`;
        }

        let options = '<option value="">-- Select Baseline --</option>';

        if (this.baselineType === 'sample') {
            options += this.samples.map(sample =>
                `<option value="${this.escapeHtml(sample)}" ${this.baselineId === sample ? 'selected' : ''}>
                    ${this.escapeHtml(sample)}
                </option>`
            ).join('');
        } else {
            options += this.groups.map(group =>
                `<option value="${group.id}" ${this.baselineId === group.id ? 'selected' : ''}>
                    ${this.escapeHtml(group.name)} (${group.sample_count || group.sample_ids?.length || 0} samples)
                </option>`
            ).join('');
        }

        return `
            <select class="form-select" id="baselineSelect" onchange="BaselineSelector.onSelectionChange(this.value)">
                ${options}
            </select>
        `;
    },

    /**
     * Render baseline info panel
     */
    renderBaselineInfo() {
        if (!this.baselineId) {
            return '';
        }

        const hasValues = Object.keys(this.baselineValues).length > 0;
        const hasChanged = this.previousBaseline &&
            (this.previousBaseline.type !== this.baselineType ||
                this.previousBaseline.id !== this.baselineId);

        let infoHtml = `
            <div class="alert alert-info py-2">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <strong>Current Baseline:</strong> 
                        <span class="badge bg-primary">${this.escapeHtml(this.baselineName || this.baselineId)}</span>
                        <span class="text-muted small ms-2">(${this.baselineType})</span>
                        ${hasChanged && this.showChangeNotification ? `
                            <span class="baseline-changed-indicator ms-2">
                                <i class="bi bi-arrow-repeat me-1"></i>Changed
                            </span>
                        ` : ''}
                    </div>
                    <button type="button" class="btn btn-sm btn-outline-secondary" onclick="BaselineSelector.clearBaseline()">
                        <i class="bi bi-x-lg"></i> Clear
                    </button>
                </div>
        `;

        if (hasValues) {
            infoHtml += `
                <hr class="my-2">
                <div class="baseline-values small">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <strong>Baseline Values Preview:</strong>
                        <button type="button" class="btn btn-sm btn-link p-0" onclick="BaselineSelector.toggleValueDetails()" title="Toggle details">
                            <i class="bi bi-chevron-down" id="valueToggleIcon"></i>
                        </button>
                    </div>
                    <div class="baseline-value-grid" id="baselineValueGrid">
                        ${this.renderBaselineValueGrid()}
                    </div>
                </div>
            `;
        }

        infoHtml += '</div>';
        return infoHtml;
    },

    /**
     * Render baseline value grid
     */
    renderBaselineValueGrid() {
        const entries = Object.entries(this.baselineValues);
        if (entries.length === 0) return '<p class="text-muted small mb-0">No values available</p>';

        // Show first 4 values, rest collapsed
        const visibleCount = 4;
        const visible = entries.slice(0, visibleCount);
        const hidden = entries.slice(visibleCount);

        let html = `
            <div class="row g-2">
                ${visible.map(([field, value]) => `
                    <div class="col-6 col-md-3">
                        <div class="baseline-value-item p-2 bg-white rounded border">
                            <div class="text-muted small text-truncate" title="${this.escapeHtml(field)}">${this.escapeHtml(field)}</div>
                            <div class="fw-semibold">${this.formatValue(value)}</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        if (hidden.length > 0) {
            html += `
                <div class="collapse mt-2" id="moreBaselineValues">
                    <div class="row g-2">
                        ${hidden.map(([field, value]) => `
                            <div class="col-6 col-md-3">
                                <div class="baseline-value-item p-2 bg-white rounded border">
                                    <div class="text-muted small text-truncate" title="${this.escapeHtml(field)}">${this.escapeHtml(field)}</div>
                                    <div class="fw-semibold">${this.formatValue(value)}</div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
                <button type="button" class="btn btn-sm btn-link p-0 mt-1" 
                        data-bs-toggle="collapse" data-bs-target="#moreBaselineValues">
                    Show ${hidden.length} more values
                </button>
            `;
        }

        return html;
    },

    /**
     * Format value for display
     * @param {any} value - Value to format
     * @returns {string} Formatted value
     */
    formatValue(value) {
        if (typeof value === 'number') {
            if (Number.isInteger(value)) {
                return value.toLocaleString();
            }
            return value.toFixed(4);
        }
        return String(value);
    },

    /**
     * Toggle value details visibility
     */
    toggleValueDetails() {
        const grid = document.getElementById('baselineValueGrid');
        const icon = document.getElementById('valueToggleIcon');

        if (grid && icon) {
            const isCollapsed = grid.style.display === 'none';
            grid.style.display = isCollapsed ? 'block' : 'none';
            icon.className = isCollapsed ? 'bi bi-chevron-down' : 'bi bi-chevron-up';
        }
    },

    /**
     * Set baseline type
     * @param {string} type - 'sample' or 'group'
     */
    setBaselineType(type) {
        if (type !== 'sample' && type !== 'group') {
            console.error('Invalid baseline type:', type);
            return;
        }

        this.baselineType = type;
        this.baselineId = null;
        this.baselineName = null;
        this.baselineValues = {};

        // Update selection dropdown
        const selectionContainer = document.getElementById('baselineSelectionContainer');
        if (selectionContainer) {
            selectionContainer.innerHTML = this.renderSelectionDropdown();
        }

        // Clear baseline info
        const infoContainer = document.getElementById('baselineInfoContainer');
        if (infoContainer) {
            infoContainer.innerHTML = this.renderBaselineInfo();
        }
    },

    /**
     * Handle selection change
     * @param {string} value - Selected value (sample ID or group ID)
     */
    async onSelectionChange(value) {
        if (!value) {
            this.clearBaseline();
            return;
        }

        // Store previous baseline for change tracking
        if (this.baselineId) {
            this.previousBaseline = {
                type: this.baselineType,
                id: this.baselineId,
                name: this.baselineName
            };
        }

        this.baselineId = value;

        // Set baseline name
        if (this.baselineType === 'sample') {
            this.baselineName = value;
        } else {
            const group = this.groups.find(g => g.id === value);
            this.baselineName = group ? group.name : value;
        }

        // Fetch baseline values if we have metric fields and file ID
        if (this.metricFields.length > 0 && this.fileId) {
            await this.fetchBaselineValues();
        }

        // Add to history
        this.addToHistory();

        // Update baseline info
        const infoContainer = document.getElementById('baselineInfoContainer');
        if (infoContainer) {
            infoContainer.innerHTML = this.renderBaselineInfo();
        }

        // Update quick switch
        const quickSwitchContainer = document.getElementById('baselineQuickSwitchContainer');
        if (quickSwitchContainer) {
            quickSwitchContainer.innerHTML = this.renderQuickSwitch();
        }

        // Trigger callback
        this.triggerBaselineChange();
    },

    /**
     * Set baseline directly
     * @param {string} type - 'sample' or 'group'
     * @param {string} id - Sample ID or group ID
     */
    async setBaseline(type, id) {
        if (type !== 'sample' && type !== 'group') {
            console.error('Invalid baseline type:', type);
            return;
        }

        this.baselineType = type;
        this.baselineId = id;

        // Set baseline name
        if (type === 'sample') {
            this.baselineName = id;
        } else {
            const group = this.groups.find(g => g.id === id);
            this.baselineName = group ? group.name : id;
        }

        // Fetch baseline values
        if (this.metricFields.length > 0 && this.fileId) {
            await this.fetchBaselineValues();
        }

        // Trigger callback
        this.triggerBaselineChange();
    },

    /**
     * Fetch baseline values from the server
     */
    async fetchBaselineValues() {
        if (!this.baselineType || !this.baselineId || !this.fileId) {
            return;
        }

        try {
            const response = await fetch('/api/baseline/value', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    baseline_type: this.baselineType,
                    baseline_id: this.baselineId,
                    metric_fields: this.metricFields,
                    file_id: this.fileId,
                    sample_column: this.sampleColumn
                })
            });

            if (response.ok) {
                const data = await response.json();
                this.baselineValues = data.baseline_values || {};
            } else {
                console.error('Failed to fetch baseline values');
                this.baselineValues = {};
            }
        } catch (error) {
            console.error('Error fetching baseline values:', error);
            this.baselineValues = {};
        }
    },

    /**
     * Get baseline value for a specific metric field
     * @param {string} metricField - Metric field name
     * @returns {number} Baseline value
     */
    getBaselineValue(metricField) {
        return this.baselineValues[metricField] || 0;
    },

    /**
     * Get all baseline values
     * @returns {Object} Baseline values object
     */
    getBaselineValues() {
        return { ...this.baselineValues };
    },

    /**
     * Calculate percentage difference for a value
     * @param {number} value - Value to compare
     * @param {string} metricField - Metric field name
     * @returns {number} Percentage difference
     */
    calculatePercentageDifference(value, metricField) {
        const baselineValue = this.baselineValues[metricField] || 0;

        if (baselineValue === 0) {
            return value === 0 ? 0 : Infinity;
        }

        return (value / baselineValue) * 100;
    },

    /**
     * Calculate percentage differences for multiple targets
     * @param {Array} targetIds - List of target IDs
     * @param {string} targetType - 'sample' or 'group'
     * @returns {Promise<Object>} Percentage differences result
     */
    async calculateBatchPercentageDifferences(targetIds, targetType) {
        if (!this.baselineType || !this.baselineId || !this.fileId) {
            throw new Error('Baseline not set');
        }

        try {
            const response = await fetch('/api/baseline/calculate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    baseline_type: this.baselineType,
                    baseline_id: this.baselineId,
                    target_ids: targetIds,
                    target_type: targetType,
                    metric_fields: this.metricFields,
                    file_id: this.fileId,
                    sample_column: this.sampleColumn
                })
            });

            if (response.ok) {
                return await response.json();
            } else {
                const error = await response.json();
                throw new Error(error.message || 'Failed to calculate percentage differences');
            }
        } catch (error) {
            console.error('Error calculating percentage differences:', error);
            throw error;
        }
    },

    /**
     * Clear baseline selection
     */
    clearBaseline() {
        this.baselineId = null;
        this.baselineName = null;
        this.baselineValues = {};

        // Reset dropdown
        const select = document.getElementById('baselineSelect');
        if (select) {
            select.value = '';
        }

        // Clear baseline info
        const infoContainer = document.getElementById('baselineInfoContainer');
        if (infoContainer) {
            infoContainer.innerHTML = this.renderBaselineInfo();
        }

        // Trigger callback
        this.triggerBaselineChange();
    },

    /**
     * Trigger baseline change callback
     */
    triggerBaselineChange() {
        if (this.onBaselineChangeCallback) {
            this.onBaselineChangeCallback(this.baselineType, this.baselineId, this.baselineValues);
        }

        // Also dispatch a custom event
        document.dispatchEvent(new CustomEvent('baselineChanged', {
            detail: {
                baselineType: this.baselineType,
                baselineId: this.baselineId,
                baselineName: this.baselineName,
                baselineValues: this.baselineValues
            }
        }));
    },

    /**
     * Update available groups
     * @param {Array} groups - List of group objects
     */
    updateGroups(groups) {
        this.groups = groups || [];

        // Re-render dropdown if currently showing groups
        if (this.baselineType === 'group') {
            const selectionContainer = document.getElementById('baselineSelectionContainer');
            if (selectionContainer) {
                selectionContainer.innerHTML = this.renderSelectionDropdown();
            }
        }
    },

    /**
     * Update available samples
     * @param {Array} samples - List of sample identifiers
     */
    updateSamples(samples) {
        this.samples = samples || [];

        // Re-render dropdown if currently showing samples
        if (this.baselineType === 'sample') {
            const selectionContainer = document.getElementById('baselineSelectionContainer');
            if (selectionContainer) {
                selectionContainer.innerHTML = this.renderSelectionDropdown();
            }
        }
    },

    /**
     * Update metric fields
     * @param {Array} metricFields - List of metric field names
     */
    updateMetricFields(metricFields) {
        this.metricFields = metricFields || [];
    },

    /**
     * Check if baseline is set
     * @returns {boolean} True if baseline is set
     */
    hasBaseline() {
        return this.baselineType !== null && this.baselineId !== null;
    },

    /**
     * Get current baseline info
     * @returns {Object} Baseline info object
     */
    getBaselineInfo() {
        return {
            type: this.baselineType,
            id: this.baselineId,
            name: this.baselineName,
            values: { ...this.baselineValues }
        };
    },

    /**
     * Escape HTML to prevent XSS
     * @param {string} str - String to escape
     * @returns {string} Escaped string
     */
    escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
};

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BaselineSelector;
}
