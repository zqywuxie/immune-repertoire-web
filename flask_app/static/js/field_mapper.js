/**
 * Field Mapper Module
 * Handles automatic field mapping between file columns and scheme requirements
 */

class FieldMapper {
    constructor() {
        this.mappings = {};
        this.confidenceScores = {};
    }

    /**
     * Auto-map fields based on scheme requirements
     * @param {string} fileId - The uploaded file ID
     * @param {string} schemeId - The scheme ID
     * @returns {Promise<Object>} Mapping result with mappings and missing fields
     */
    async autoMapFields(fileId, schemeId) {
        try {
            const response = await fetch('/api/analysis/auto-map', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    file_id: fileId,
                    scheme_id: schemeId
                })
            });

            if (!response.ok) {
                throw new Error(`Auto-mapping failed: ${response.statusText}`);
            }

            const data = await response.json();
            this.mappings = data.mappings || {};
            this.extractConfidenceScores();

            console.log('Auto-mapped fields:', Object.keys(this.mappings).length);

            return {
                mappings: this.mappings,
                missingFields: data.missing_fields || [],
                success: true
            };

        } catch (error) {
            console.error('Error auto-mapping fields:', error);
            throw error;
        }
    }

    /**
     * Extract confidence scores from mappings
     */
    extractConfidenceScores() {
        this.confidenceScores = {};
        Object.entries(this.mappings).forEach(([targetField, mapping]) => {
            this.confidenceScores[targetField] = mapping.confidence || 0;
        });
    }

    /**
     * Get current mappings
     * @returns {Object} Current field mappings
     */
    getMappings() {
        return this.mappings;
    }

    /**
     * Get mapping for a specific target field
     * @param {string} targetField - The target field name
     * @returns {Object|null} Mapping object or null
     */
    getMapping(targetField) {
        return this.mappings[targetField] || null;
    }

    /**
     * Set mapping for a target field
     * @param {string} targetField - The target field name
     * @param {string} sourceColumn - The source column name
     * @param {number} confidence - Confidence score (0-1)
     */
    setMapping(targetField, sourceColumn, confidence = 1.0) {
        this.mappings[targetField] = {
            source_column: sourceColumn,
            confidence: confidence
        };
        this.confidenceScores[targetField] = confidence;
        console.log(`Set mapping: ${targetField} -> ${sourceColumn} (${Math.round(confidence * 100)}%)`);
    }

    /**
     * Remove mapping for a target field
     * @param {string} targetField - The target field name
     */
    removeMapping(targetField) {
        delete this.mappings[targetField];
        delete this.confidenceScores[targetField];
        console.log(`Removed mapping for: ${targetField}`);
    }

    /**
     * Clear all mappings
     */
    clearMappings() {
        this.mappings = {};
        this.confidenceScores = {};
        console.log('Cleared all mappings');
    }

    /**
     * Get confidence score for a target field
     * @param {string} targetField - The target field name
     * @returns {number} Confidence score (0-1)
     */
    getConfidence(targetField) {
        return this.confidenceScores[targetField] || 0;
    }

    /**
     * Check if mapping has high confidence
     * @param {string} targetField - The target field name
     * @param {number} threshold - Confidence threshold (default 0.8)
     * @returns {boolean} True if confidence is above threshold
     */
    hasHighConfidence(targetField, threshold = 0.8) {
        return this.getConfidence(targetField) >= threshold;
    }

    /**
     * Get fields with low confidence
     * @param {number} threshold - Confidence threshold (default 0.8)
     * @returns {Array<string>} Array of field names with low confidence
     */
    getLowConfidenceFields(threshold = 0.8) {
        return Object.keys(this.mappings).filter(field =>
            this.getConfidence(field) < threshold
        );
    }

    /**
     * Validate mappings
     * @param {Array<string>} requiredFields - Required target fields
     * @returns {Object} Validation result
     */
    validateMappings(requiredFields) {
        const errors = [];
        const warnings = [];
        const missingFields = [];

        requiredFields.forEach(field => {
            if (!this.mappings[field]) {
                missingFields.push(field);
                errors.push(`缺少必需字段的映射: ${field}`);
            } else if (!this.hasHighConfidence(field, 0.5)) {
                warnings.push(`字段 ${field} 的映射置信度较低`);
            }
        });

        return {
            isValid: errors.length === 0,
            errors: errors,
            warnings: warnings,
            missingFields: missingFields
        };
    }

    /**
     * Render field mapping table
     * @param {HTMLElement} container - Container element
     * @param {Array<string>} availableColumns - Available source columns
     * @param {Function} onChangeCallback - Callback when mapping changes
     */
    renderMappingTable(container, availableColumns, onChangeCallback) {
        if (!container) {
            console.error('Container element not provided');
            return;
        }

        const table = document.createElement('table');
        table.className = 'table table-sm table-hover';

        // Create header
        const thead = document.createElement('thead');
        thead.innerHTML = `
            <tr>
                <th>目标字段</th>
                <th>源列</th>
                <th>置信度</th>
                <th class="text-center">状态</th>
            </tr>
        `;
        table.appendChild(thead);

        // Create body
        const tbody = document.createElement('tbody');

        Object.entries(this.mappings).forEach(([targetField, mapping]) => {
            const row = this.createMappingRow(
                targetField,
                mapping,
                availableColumns,
                onChangeCallback
            );
            tbody.appendChild(row);
        });

        table.appendChild(tbody);
        container.innerHTML = '';
        container.appendChild(table);
    }

    /**
     * Create a mapping row
     * @param {string} targetField - Target field name
     * @param {Object} mapping - Mapping object
     * @param {Array<string>} availableColumns - Available source columns
     * @param {Function} onChangeCallback - Callback when mapping changes
     * @returns {HTMLElement} Table row element
     */
    createMappingRow(targetField, mapping, availableColumns, onChangeCallback) {
        const tr = document.createElement('tr');

        // Target field column
        const tdTarget = document.createElement('td');
        tdTarget.innerHTML = `<strong>${this.escapeHtml(targetField)}</strong>`;
        tr.appendChild(tdTarget);

        // Source column dropdown
        const tdSource = document.createElement('td');
        const select = document.createElement('select');
        select.className = 'form-select form-select-sm';
        select.dataset.targetField = targetField;

        // Add empty option
        const emptyOption = document.createElement('option');
        emptyOption.value = '';
        emptyOption.textContent = '-- 选择列 --';
        select.appendChild(emptyOption);

        // Add available columns
        availableColumns.forEach(col => {
            const option = document.createElement('option');
            option.value = col;
            option.textContent = col;
            if (col === mapping.source_column) {
                option.selected = true;
            }
            select.appendChild(option);
        });

        // Add change handler
        select.addEventListener('change', (e) => {
            const newSourceColumn = e.target.value;
            if (newSourceColumn) {
                this.setMapping(targetField, newSourceColumn, 1.0);
            } else {
                this.removeMapping(targetField);
            }

            if (onChangeCallback) {
                onChangeCallback(targetField, newSourceColumn);
            }

            // Update the row
            this.updateMappingRow(tr, targetField);
        });

        tdSource.appendChild(select);
        tr.appendChild(tdSource);

        // Confidence column
        const tdConfidence = document.createElement('td');
        const confidence = mapping.confidence || 0;
        const confidencePercent = Math.round(confidence * 100);
        let badgeClass = 'bg-danger';
        if (confidence >= 0.8) {
            badgeClass = 'bg-success';
        } else if (confidence >= 0.5) {
            badgeClass = 'bg-warning text-dark';
        }

        tdConfidence.innerHTML = `<span class="badge ${badgeClass}">${confidencePercent}%</span>`;
        tr.appendChild(tdConfidence);

        // Status column
        const tdStatus = document.createElement('td');
        tdStatus.className = 'text-center';
        if (confidence >= 0.8) {
            tdStatus.innerHTML = '<i class="bi bi-check-circle-fill text-success" title="高置信度"></i>';
        } else if (confidence >= 0.5) {
            tdStatus.innerHTML = '<i class="bi bi-exclamation-triangle-fill text-warning" title="中等置信度"></i>';
        } else {
            tdStatus.innerHTML = '<i class="bi bi-x-circle-fill text-danger" title="低置信度"></i>';
        }
        tr.appendChild(tdStatus);

        return tr;
    }

    /**
     * Update a mapping row after change
     * @param {HTMLElement} row - The row element
     * @param {string} targetField - Target field name
     */
    updateMappingRow(row, targetField) {
        const mapping = this.getMapping(targetField);
        if (!mapping) return;

        const confidence = mapping.confidence || 0;
        const confidencePercent = Math.round(confidence * 100);

        // Update confidence badge
        const confidenceTd = row.cells[2];
        let badgeClass = 'bg-danger';
        if (confidence >= 0.8) {
            badgeClass = 'bg-success';
        } else if (confidence >= 0.5) {
            badgeClass = 'bg-warning text-dark';
        }
        confidenceTd.innerHTML = `<span class="badge ${badgeClass}">${confidencePercent}%</span>`;

        // Update status icon
        const statusTd = row.cells[3];
        if (confidence >= 0.8) {
            statusTd.innerHTML = '<i class="bi bi-check-circle-fill text-success" title="高置信度"></i>';
        } else if (confidence >= 0.5) {
            statusTd.innerHTML = '<i class="bi bi-exclamation-triangle-fill text-warning" title="中等置信度"></i>';
        } else {
            statusTd.innerHTML = '<i class="bi bi-x-circle-fill text-danger" title="低置信度"></i>';
        }
    }

    /**
     * Show mapping summary
     * @param {HTMLElement} container - Container element
     */
    showSummary(container) {
        if (!container) return;

        const totalMappings = Object.keys(this.mappings).length;
        const highConfidence = Object.values(this.confidenceScores).filter(c => c >= 0.8).length;
        const mediumConfidence = Object.values(this.confidenceScores).filter(c => c >= 0.5 && c < 0.8).length;
        const lowConfidence = Object.values(this.confidenceScores).filter(c => c < 0.5).length;

        container.innerHTML = `
            <div class="alert alert-info">
                <h6 class="alert-heading">
                    <i class="bi bi-info-circle me-2"></i>
                    映射摘要
                </h6>
                <div class="row mt-3">
                    <div class="col-md-3">
                        <div class="text-center">
                            <div class="h4 mb-0">${totalMappings}</div>
                            <div class="small text-muted">总映射数</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="text-center">
                            <div class="h4 mb-0 text-success">${highConfidence}</div>
                            <div class="small text-muted">高置信度</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="text-center">
                            <div class="h4 mb-0 text-warning">${mediumConfidence}</div>
                            <div class="small text-muted">中等置信度</div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="text-center">
                            <div class="h4 mb-0 text-danger">${lowConfidence}</div>
                            <div class="small text-muted">低置信度</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Export mappings as simple object
     * @returns {Object} Simple mapping object (targetField -> sourceColumn)
     */
    exportSimpleMappings() {
        const simple = {};
        Object.entries(this.mappings).forEach(([targetField, mapping]) => {
            simple[targetField] = mapping.source_column;
        });
        return simple;
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
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = FieldMapper;
}
