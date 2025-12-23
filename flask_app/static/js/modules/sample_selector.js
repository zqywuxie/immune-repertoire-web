/**
 * Sample Selector Module
 * Handles sample selection UI and interactions.
 * Requirements: 5.3, 5.4, 5.6, 5.7
 */
const SampleSelector = {
    // Current state
    samples: [],
    selectedSamples: new Set(),
    fileId: null,
    sampleColumn: null,

    /**
     * Initialize the sample selector.
     * @param {string} fileId - File ID
     * @param {string} sampleColumn - Sample column name
     */
    init(fileId, sampleColumn) {
        this.fileId = fileId;
        this.sampleColumn = sampleColumn;
        this.samples = [];
        this.selectedSamples = new Set();
    },

    /**
     * Load samples from the server.
     * @returns {Promise<boolean>} Success status
     */
    async loadSamples() {
        if (!this.fileId || !this.sampleColumn) {
            console.error('File ID and sample column are required');
            return false;
        }

        try {
            const response = await fetch(
                `/api/files/${this.fileId}/column-values?column=${encodeURIComponent(this.sampleColumn)}`
            );

            if (!response.ok) {
                const error = await response.json();
                console.error('Failed to load samples:', error);
                return false;
            }

            const data = await response.json();
            this.samples = data.values || [];

            // Select all samples by default (Requirement 5.7)
            this.selectedSamples = new Set(this.samples);

            return true;
        } catch (error) {
            console.error('Error loading samples:', error);
            return false;
        }
    },

    /**
     * Display samples in the UI.
     * @param {string[]} samples - Array of sample names
     */
    displaySamples(samples) {
        if (samples) {
            this.samples = samples;
            // Select all by default
            this.selectedSamples = new Set(samples);
        }

        const container = document.getElementById('sampleListContainer');
        if (!container) {
            console.error('Sample list container not found');
            return;
        }

        // Clear existing content
        container.innerHTML = '';

        // Create header with select all checkbox
        const header = document.createElement('div');
        header.className = 'sample-selector-header mb-3';
        header.innerHTML = `
            <div class="form-check">
                <input class="form-check-input" type="checkbox" id="selectAllSamples" 
                       ${this.selectedSamples.size === this.samples.length ? 'checked' : ''}>
                <label class="form-check-label fw-bold" for="selectAllSamples">
                    全选 / 取消全选
                </label>
            </div>
        `;
        container.appendChild(header);

        // Add event listener for select all
        const selectAllCheckbox = document.getElementById('selectAllSamples');
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', () => {
                this.toggleSelectAll();
            });
        }

        // Create sample list
        const listContainer = document.createElement('div');
        listContainer.className = 'sample-list';
        listContainer.style.maxHeight = '400px';
        listContainer.style.overflowY = 'auto';
        listContainer.style.border = '1px solid #dee2e6';
        listContainer.style.borderRadius = '0.25rem';
        listContainer.style.padding = '0.5rem';

        if (this.samples.length === 0) {
            listContainer.innerHTML = '<p class="text-muted text-center">没有找到样本</p>';
        } else {
            this.samples.forEach((sample, index) => {
                const sampleItem = document.createElement('div');
                sampleItem.className = 'form-check mb-2';
                sampleItem.innerHTML = `
                    <input class="form-check-input sample-checkbox" type="checkbox" 
                           id="sample_${index}" value="${sample}"
                           ${this.selectedSamples.has(sample) ? 'checked' : ''}>
                    <label class="form-check-label" for="sample_${index}">
                        ${sample}
                    </label>
                `;
                listContainer.appendChild(sampleItem);

                // Add event listener for individual checkbox
                const checkbox = sampleItem.querySelector('.sample-checkbox');
                if (checkbox) {
                    checkbox.addEventListener('change', (e) => {
                        if (e.target.checked) {
                            this.selectedSamples.add(sample);
                        } else {
                            this.selectedSamples.delete(sample);
                        }
                        this.updateSelectionStats();
                        this.updateSelectAllCheckbox();

                        // Notify FieldAnalyzer to update baseline select if it exists
                        if (typeof FieldAnalyzer !== 'undefined' && FieldAnalyzer.populateBaselineSelect) {
                            FieldAnalyzer.populateBaselineSelect(this.samples);
                        }
                    });
                }
            });
        }

        container.appendChild(listContainer);

        // Create stats footer
        const footer = document.createElement('div');
        footer.className = 'sample-selector-footer mt-3';
        footer.innerHTML = `
            <div class="alert alert-info mb-0" id="sampleSelectionStats">
                已选择: <strong>${this.selectedSamples.size}</strong> / ${this.samples.length} 个样本
            </div>
        `;
        container.appendChild(footer);
    },

    /**
     * Get selected samples.
     * @returns {string[]} Array of selected sample names
     */
    getSelectedSamples() {
        return Array.from(this.selectedSamples);
    },

    /**
     * Toggle select all / deselect all.
     */
    toggleSelectAll() {
        const selectAllCheckbox = document.getElementById('selectAllSamples');
        const isChecked = selectAllCheckbox ? selectAllCheckbox.checked : false;

        if (isChecked) {
            // Select all
            this.selectedSamples = new Set(this.samples);
        } else {
            // Deselect all
            this.selectedSamples.clear();
        }

        // Update all checkboxes
        const checkboxes = document.querySelectorAll('.sample-checkbox');
        checkboxes.forEach(checkbox => {
            checkbox.checked = isChecked;
        });

        this.updateSelectionStats();

        // Notify FieldAnalyzer to update baseline select if it exists
        if (typeof FieldAnalyzer !== 'undefined' && FieldAnalyzer.populateBaselineSelect) {
            FieldAnalyzer.populateBaselineSelect(this.samples);
        }
    },

    /**
     * Update the select all checkbox state based on individual selections.
     */
    updateSelectAllCheckbox() {
        const selectAllCheckbox = document.getElementById('selectAllSamples');
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = this.selectedSamples.size === this.samples.length;
            selectAllCheckbox.indeterminate =
                this.selectedSamples.size > 0 && this.selectedSamples.size < this.samples.length;
        }
    },

    /**
     * Update selection statistics display.
     */
    updateSelectionStats() {
        const statsEl = document.getElementById('sampleSelectionStats');
        if (statsEl) {
            statsEl.innerHTML = `
                已选择: <strong>${this.selectedSamples.size}</strong> / ${this.samples.length} 个样本
            `;
        }
    },

    /**
     * Validate that at least one sample is selected.
     * @returns {boolean} True if validation passes
     */
    validate() {
        if (this.selectedSamples.size === 0) {
            // Show validation error
            const container = document.getElementById('sampleListContainer');
            if (container) {
                // Check if error message already exists
                let errorEl = document.getElementById('sampleValidationError');
                if (!errorEl) {
                    errorEl = document.createElement('div');
                    errorEl.id = 'sampleValidationError';
                    errorEl.className = 'alert alert-danger mt-2';
                    errorEl.innerHTML = `
                        <i class="bi bi-exclamation-triangle-fill me-2"></i>
                        请至少选择一个样本进行分析
                    `;
                    container.appendChild(errorEl);
                }
            }
            return false;
        } else {
            // Remove validation error if it exists
            const errorEl = document.getElementById('sampleValidationError');
            if (errorEl) {
                errorEl.remove();
            }
            return true;
        }
    },

    /**
     * Select specific samples.
     * @param {string[]} samples - Array of sample names to select
     */
    selectSamples(samples) {
        this.selectedSamples = new Set(samples.filter(s => this.samples.includes(s)));
        this.displaySamples();
    },

    /**
     * Clear all selections.
     */
    clearSelection() {
        this.selectedSamples.clear();
        this.displaySamples();
    },

    /**
     * Get sample count.
     * @returns {number} Total number of samples
     */
    getSampleCount() {
        return this.samples.length;
    },

    /**
     * Get selected sample count.
     * @returns {number} Number of selected samples
     */
    getSelectedCount() {
        return this.selectedSamples.size;
    },

    /**
     * Check if a sample is selected.
     * @param {string} sample - Sample name
     * @returns {boolean} True if sample is selected
     */
    isSampleSelected(sample) {
        return this.selectedSamples.has(sample);
    }
};
