/**
 * Field Selector Module
 * Handles field selection and display for custom analysis mode
 */

class FieldSelector {
    constructor() {
        this.availableFields = [];
        this.selectedFields = [];
        this.fieldTypes = {};
    }

    /**
     * Set available fields from the uploaded file
     * @param {Array<string>} fields - Array of field names
     * @param {Object} fieldTypes - Optional mapping of field names to types
     */
    setAvailableFields(fields, fieldTypes = {}) {
        this.availableFields = fields || [];
        this.fieldTypes = fieldTypes;
        console.log(`Set ${this.availableFields.length} available fields`);
    }

    /**
     * Get all available fields
     * @returns {Array<string>} Array of field names
     */
    getAvailableFields() {
        return this.availableFields;
    }

    /**
     * Get selected fields
     * @returns {Array<string>} Array of selected field names
     */
    getSelectedFields() {
        return this.selectedFields;
    }

    /**
     * Select a field
     * @param {string} fieldName - The field name to select
     * @returns {boolean} True if successful
     */
    selectField(fieldName) {
        if (!this.availableFields.includes(fieldName)) {
            console.warn('Field not available:', fieldName);
            return false;
        }

        if (!this.selectedFields.includes(fieldName)) {
            this.selectedFields.push(fieldName);
            console.log('Selected field:', fieldName);
            return true;
        }

        return false;
    }

    /**
     * Deselect a field
     * @param {string} fieldName - The field name to deselect
     * @returns {boolean} True if successful
     */
    deselectField(fieldName) {
        const index = this.selectedFields.indexOf(fieldName);
        if (index > -1) {
            this.selectedFields.splice(index, 1);
            console.log('Deselected field:', fieldName);
            return true;
        }
        return false;
    }

    /**
     * Toggle field selection
     * @param {string} fieldName - The field name to toggle
     * @returns {boolean} True if now selected, false if deselected
     */
    toggleField(fieldName) {
        if (this.selectedFields.includes(fieldName)) {
            this.deselectField(fieldName);
            return false;
        } else {
            this.selectField(fieldName);
            return true;
        }
    }

    /**
     * Clear all selections
     */
    clearSelection() {
        this.selectedFields = [];
        console.log('Cleared all field selections');
    }

    /**
     * Select all fields
     */
    selectAll() {
        this.selectedFields = [...this.availableFields];
        console.log('Selected all fields');
    }

    /**
     * Check if a field is selected
     * @param {string} fieldName - The field name to check
     * @returns {boolean} True if selected
     */
    isFieldSelected(fieldName) {
        return this.selectedFields.includes(fieldName);
    }

    /**
     * Validate field selection
     * @returns {Object} Validation result with isValid and errors
     */
    validateSelection() {
        const errors = [];

        if (this.selectedFields.length === 0) {
            errors.push('请至少选择一个字段');
        }

        if (this.selectedFields.length > 50) {
            errors.push('选择的字段数量不能超过50个');
        }

        return {
            isValid: errors.length === 0,
            errors: errors
        };
    }

    /**
     * Render fields in a grid layout
     * @param {HTMLElement} container - The container element
     * @param {Function} onChangeCallback - Callback when selection changes
     */
    renderFields(container, onChangeCallback) {
        if (!container) {
            console.error('Container element not provided');
            return;
        }

        container.innerHTML = '';

        if (this.availableFields.length === 0) {
            container.innerHTML = `
                <div class="col-12">
                    <div class="alert alert-warning">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        没有可用的字段。请先上传文件。
                    </div>
                </div>
            `;
            return;
        }

        this.availableFields.forEach(field => {
            const fieldItem = this.createFieldItem(field, onChangeCallback);
            container.appendChild(fieldItem);
        });
    }

    /**
     * Create a field item element
     * @param {string} fieldName - The field name
     * @param {Function} onChangeCallback - Callback when selection changes
     * @returns {HTMLElement} The field item element
     */
    createFieldItem(fieldName, onChangeCallback) {
        const col = document.createElement('div');
        col.className = 'col-md-4 mb-2';

        const fieldItem = document.createElement('div');
        fieldItem.className = 'field-item';
        fieldItem.dataset.fieldName = fieldName;

        const isSelected = this.isFieldSelected(fieldName);
        const fieldType = this.fieldTypes[fieldName] || 'string';

        fieldItem.innerHTML = `
            <div class="form-check">
                <input 
                    class="form-check-input field-checkbox" 
                    type="checkbox" 
                    id="field_${this.sanitizeId(fieldName)}" 
                    value="${this.escapeHtml(fieldName)}"
                    ${isSelected ? 'checked' : ''}
                >
                <label class="form-check-label w-100" for="field_${this.sanitizeId(fieldName)}">
                    <div class="d-flex justify-content-between align-items-center">
                        <span class="field-name">${this.escapeHtml(fieldName)}</span>
                        <span class="badge bg-secondary field-type-badge">${fieldType}</span>
                    </div>
                </label>
            </div>
        `;

        // Add change handler
        const checkbox = fieldItem.querySelector('.field-checkbox');
        checkbox.addEventListener('change', (e) => {
            const isNowSelected = this.toggleField(fieldName);
            if (onChangeCallback) {
                onChangeCallback(fieldName, isNowSelected);
            }
        });

        col.appendChild(fieldItem);
        return col;
    }

    /**
     * Render selection summary
     * @param {HTMLElement} container - The container element
     */
    renderSummary(container) {
        if (!container) {
            console.error('Container element not provided');
            return;
        }

        if (this.selectedFields.length === 0) {
            container.innerHTML = `
                <div class="alert alert-info">
                    <i class="bi bi-info-circle me-2"></i>
                    尚未选择任何字段
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="alert alert-success">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <i class="bi bi-check-circle me-2"></i>
                        <strong>已选择 ${this.selectedFields.length} 个字段</strong>
                    </div>
                    <button class="btn btn-sm btn-outline-secondary clear-selection-btn">
                        <i class="bi bi-x-circle me-1"></i>
                        清除选择
                    </button>
                </div>
                <div class="mt-2 small">
                    ${this.selectedFields.map(f => `<span class="badge bg-light text-dark me-1">${this.escapeHtml(f)}</span>`).join('')}
                </div>
            </div>
        `;

        // Add clear button handler
        const clearBtn = container.querySelector('.clear-selection-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                this.clearSelection();
                this.renderSummary(container);
                // Trigger re-render of fields if needed
                const event = new CustomEvent('fieldSelectionCleared');
                container.dispatchEvent(event);
            });
        }
    }

    /**
     * Get field statistics
     * @returns {Object} Statistics about field selection
     */
    getStatistics() {
        return {
            totalFields: this.availableFields.length,
            selectedFields: this.selectedFields.length,
            unselectedFields: this.availableFields.length - this.selectedFields.length,
            selectionPercentage: this.availableFields.length > 0
                ? Math.round((this.selectedFields.length / this.availableFields.length) * 100)
                : 0
        };
    }

    /**
     * Export selection as configuration
     * @returns {Object} Configuration object
     */
    exportConfiguration() {
        return {
            selectedFields: [...this.selectedFields],
            fieldTypes: { ...this.fieldTypes },
            timestamp: new Date().toISOString()
        };
    }

    /**
     * Import selection from configuration
     * @param {Object} config - Configuration object
     */
    importConfiguration(config) {
        if (config.selectedFields) {
            this.selectedFields = config.selectedFields.filter(f =>
                this.availableFields.includes(f)
            );
        }
        if (config.fieldTypes) {
            this.fieldTypes = { ...this.fieldTypes, ...config.fieldTypes };
        }
        console.log('Imported field configuration');
    }

    /**
     * Sanitize ID for use in HTML
     * @param {string} text - Text to sanitize
     * @returns {string} Sanitized text
     */
    sanitizeId(text) {
        return text.replace(/[^a-zA-Z0-9_-]/g, '_');
    }

    /**
     * Escape HTML to prevent XSS
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Filter fields by search term
     * @param {string} searchTerm - The search term
     * @returns {Array<string>} Filtered field names
     */
    filterFields(searchTerm) {
        if (!searchTerm) {
            return this.availableFields;
        }

        const term = searchTerm.toLowerCase();
        return this.availableFields.filter(field =>
            field.toLowerCase().includes(term)
        );
    }

    /**
     * Group fields by prefix (e.g., "sample_", "v_gene_")
     * @returns {Object} Grouped fields
     */
    groupFieldsByPrefix() {
        const groups = {};

        this.availableFields.forEach(field => {
            const parts = field.split('_');
            const prefix = parts.length > 1 ? parts[0] : 'other';

            if (!groups[prefix]) {
                groups[prefix] = [];
            }
            groups[prefix].push(field);
        });

        return groups;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FieldSelector;
}
