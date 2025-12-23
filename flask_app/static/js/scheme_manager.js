/**
 * Scheme Manager Module
 * Handles loading, selecting, and managing analysis schemes
 */

class SchemeManager {
    constructor() {
        this.schemes = [];
        this.selectedScheme = null;
    }

    /**
     * Load all available schemes from the server
     * @returns {Promise<Array>} Array of scheme objects
     */
    async loadSchemes() {
        try {
            const response = await fetch('/api/analysis/schemes');
            if (!response.ok) {
                throw new Error(`Failed to load schemes: ${response.statusText}`);
            }
            const data = await response.json();
            this.schemes = data.schemes || [];
            console.log(`Loaded ${this.schemes.length} schemes`);
            return this.schemes;
        } catch (error) {
            console.error('Error loading schemes:', error);
            throw error;
        }
    }

    /**
     * Get all loaded schemes
     * @returns {Array} Array of scheme objects
     */
    getAllSchemes() {
        return this.schemes;
    }

    /**
     * Get a specific scheme by ID
     * @param {string} schemeId - The scheme ID
     * @returns {Object|null} The scheme object or null if not found
     */
    getSchemeById(schemeId) {
        return this.schemes.find(s => s.id === schemeId) || null;
    }

    /**
     * Select a scheme
     * @param {string} schemeId - The scheme ID to select
     * @returns {Object|null} The selected scheme or null if not found
     */
    selectScheme(schemeId) {
        this.selectedScheme = this.getSchemeById(schemeId);
        if (this.selectedScheme) {
            console.log('Selected scheme:', this.selectedScheme.name);
        } else {
            console.warn('Scheme not found:', schemeId);
        }
        return this.selectedScheme;
    }

    /**
     * Get the currently selected scheme
     * @returns {Object|null} The selected scheme or null
     */
    getSelectedScheme() {
        return this.selectedScheme;
    }

    /**
     * Clear the selected scheme
     */
    clearSelection() {
        this.selectedScheme = null;
    }

    /**
     * Create a custom scheme
     * @param {Object} schemeData - The scheme data
     * @param {string} schemeData.name - Scheme name
     * @param {string} schemeData.description - Scheme description
     * @param {Array<string>} schemeData.fields - Selected fields
     * @param {Object} schemeData.parameters - Analysis parameters
     * @returns {Promise<Object>} The created scheme
     */
    async createCustomScheme(schemeData) {
        try {
            const response = await fetch('/api/analysis/schemes/custom', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(schemeData)
            });

            if (!response.ok) {
                throw new Error(`Failed to create custom scheme: ${response.statusText}`);
            }

            const result = await response.json();
            console.log('Created custom scheme:', result.scheme_id);

            // Reload schemes to include the new one
            await this.loadSchemes();

            return result;
        } catch (error) {
            console.error('Error creating custom scheme:', error);
            throw error;
        }
    }

    /**
     * Delete a custom scheme
     * @param {string} schemeId - The scheme ID to delete
     * @returns {Promise<boolean>} True if successful
     */
    async deleteCustomScheme(schemeId) {
        try {
            const response = await fetch(`/api/analysis/schemes/custom/${schemeId}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error(`Failed to delete custom scheme: ${response.statusText}`);
            }

            const result = await response.json();
            console.log('Deleted custom scheme:', schemeId);

            // Reload schemes to reflect the deletion
            await this.loadSchemes();

            // Clear selection if the deleted scheme was selected
            if (this.selectedScheme && this.selectedScheme.id === schemeId) {
                this.clearSelection();
            }

            return result.success;
        } catch (error) {
            console.error('Error deleting custom scheme:', error);
            throw error;
        }
    }

    /**
     * Render schemes in a grid layout
     * @param {HTMLElement} container - The container element
     * @param {Function} onSelectCallback - Callback when a scheme is selected
     */
    renderSchemes(container, onSelectCallback) {
        if (!container) {
            console.error('Container element not provided');
            return;
        }

        container.innerHTML = '';

        if (this.schemes.length === 0) {
            container.innerHTML = `
                <div class="col-12">
                    <div class="alert alert-info">
                        <i class="bi bi-info-circle me-2"></i>
                        暂无可用的分析方案
                    </div>
                </div>
            `;
            return;
        }

        this.schemes.forEach(scheme => {
            const schemeCard = this.createSchemeCard(scheme, onSelectCallback);
            container.appendChild(schemeCard);
        });
    }

    /**
     * Create a scheme card element
     * @param {Object} scheme - The scheme object
     * @param {Function} onSelectCallback - Callback when the scheme is selected
     * @returns {HTMLElement} The scheme card element
     */
    createSchemeCard(scheme, onSelectCallback) {
        const col = document.createElement('div');
        col.className = 'col-md-4 mb-3';

        const card = document.createElement('div');
        card.className = 'card scheme-card h-100';
        card.dataset.schemeId = scheme.id;

        // Add selected class if this is the selected scheme
        if (this.selectedScheme && this.selectedScheme.id === scheme.id) {
            card.classList.add('selected');
        }

        card.innerHTML = `
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="scheme-icon ${scheme.icon || 'bi bi-graph-up'}"></div>
                    <span class="badge ${scheme.is_custom ? 'bg-info' : 'bg-primary'} scheme-badge">
                        ${scheme.is_custom ? '自定义' : '预设'}
                    </span>
                </div>
                <h5 class="card-title scheme-name">${this.escapeHtml(scheme.name)}</h5>
                <p class="card-text scheme-description text-muted small">
                    ${this.escapeHtml(scheme.description)}
                </p>
            </div>
            <div class="card-footer bg-transparent">
                <button class="btn btn-sm btn-outline-primary w-100 select-scheme-btn">
                    <i class="bi bi-check-circle me-1"></i>
                    选择此方案
                </button>
            </div>
        `;

        // Add click handler
        const selectBtn = card.querySelector('.select-scheme-btn');
        selectBtn.addEventListener('click', () => {
            this.selectScheme(scheme.id);
            if (onSelectCallback) {
                onSelectCallback(scheme);
            }
        });

        col.appendChild(card);
        return col;
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
     * Get required fields for a scheme
     * @param {string} schemeId - The scheme ID
     * @returns {Array} Array of required field definitions
     */
    getRequiredFields(schemeId) {
        const scheme = this.getSchemeById(schemeId);
        return scheme ? (scheme.required_fields || []) : [];
    }

    /**
     * Get optional fields for a scheme
     * @param {string} schemeId - The scheme ID
     * @returns {Array} Array of optional field definitions
     */
    getOptionalFields(schemeId) {
        const scheme = this.getSchemeById(schemeId);
        return scheme ? (scheme.optional_fields || []) : [];
    }

    /**
     * Get default parameters for a scheme
     * @param {string} schemeId - The scheme ID
     * @returns {Object} Default parameters object
     */
    getDefaultParameters(schemeId) {
        const scheme = this.getSchemeById(schemeId);
        return scheme ? (scheme.default_parameters || {}) : {};
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SchemeManager;
}
