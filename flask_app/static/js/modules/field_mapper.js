/**
 * Field Mapper Module
 * Handles field mapping UI and interactions.
 * Requirements: 11.2, 11.4, 11.5, 6.5 - No inline scripts
 * Enhanced: Support for showing all fields with add/remove functionality
 */
const FieldMapper = {
    // Current state
    columns: [],
    analysisType: null,
    requiredFields: [],
    currentMapping: {},
    fieldScores: {},
    viewMode: 'required', // 'required' or 'all'
    selectedAvailableField: null,
    selectedMappedField: null,
    showAllFieldsMode: false, // Enable enhanced mode when true

    /**
     * Initialize the field mapper with available columns.
     * @param {string[]} columns - Available column names from the data file
     * @param {boolean} showAllFields - Enable all fields view mode
     */
    init(columns, showAllFields = false) {
        this.columns = columns;
        this.currentMapping = {};
        this.fieldScores = {};
        this.showAllFieldsMode = showAllFields;
        this.viewMode = showAllFields ? 'all' : 'required';

        // Reset UI - with null checks
        const analysisTypeEl = document.getElementById('analysisType');
        const requiredViewEl = document.getElementById('requiredFieldsView');
        const allFieldsViewEl = document.getElementById('allFieldsView');
        const viewModeToggleEl = document.getElementById('viewModeToggle');
        const templateActionsEl = document.getElementById('templateActions');
        const validationResultEl = document.getElementById('validationResult');
        const mappingStatusEl = document.getElementById('mappingStatus');

        if (analysisTypeEl) analysisTypeEl.value = '';
        if (requiredViewEl) requiredViewEl.classList.add('d-none');
        if (allFieldsViewEl) allFieldsViewEl.classList.add('d-none');
        if (templateActionsEl) templateActionsEl.classList.add('d-none');
        if (validationResultEl) validationResultEl.classList.add('d-none');
        if (mappingStatusEl) mappingStatusEl.classList.add('d-none');

        // Show view mode toggle if in enhanced mode
        if (viewModeToggleEl) {
            viewModeToggleEl.style.display = showAllFields ? 'block' : 'none';
        }
    },

    /**
     * Handle analysis type change.
     */
    async onAnalysisTypeChange() {
        const select = document.getElementById('analysisType');
        this.analysisType = select.value;

        if (!this.analysisType) {
            document.getElementById('requiredFieldsView').classList.add('d-none');
            document.getElementById('allFieldsView').classList.add('d-none');
            document.getElementById('templateActions').classList.add('d-none');
            return;
        }

        // Get required fields and suggestions
        await this.loadRequiredFields();
        await this.getSuggestions();
        await this.loadSavedTemplates();

        // Show appropriate view
        this.showCurrentView();
        document.getElementById('templateActions').classList.remove('d-none');
    },

    /**
     * Handle view mode change.
     * @param {string} mode - 'required' or 'all'
     */
    onViewModeChange(mode) {
        this.viewMode = mode;
        this.showCurrentView();
    },

    /**
     * Show the current view based on mode.
     */
    showCurrentView() {
        const requiredView = document.getElementById('requiredFieldsView');
        const allFieldsView = document.getElementById('allFieldsView');

        if (this.viewMode === 'all' && this.showAllFieldsMode) {
            requiredView.classList.add('d-none');
            allFieldsView.classList.remove('d-none');
            this.renderAllFieldsView();
        } else {
            requiredView.classList.remove('d-none');
            allFieldsView.classList.add('d-none');
            this.renderMappingTable();
        }
    },

    /**
     * Render the all fields view.
     */
    renderAllFieldsView() {
        this.renderAvailableFields();
        this.renderMappedFields();
        this.updateMappedCount();
    },

    /**
     * Render available fields list.
     */
    renderAvailableFields() {
        const container = document.getElementById('availableFieldsList');
        container.innerHTML = '';

        // Group fields by mapped status
        const mappedFields = Object.keys(this.currentMapping);
        const unmappedFields = this.columns.filter(col => !mappedFields.includes(col));

        // Show unmapped fields first
        if (unmappedFields.length > 0) {
            const group = this.createFieldGroup('未映射字段', unmappedFields, false);
            container.appendChild(group);
        }

        // Show mapped fields
        if (mappedFields.length > 0) {
            const group = this.createFieldGroup('已映射字段', mappedFields, true);
            container.appendChild(group);
        }
    },

    /**
     * Create a field group element.
     */
    createFieldGroup(title, fields, isMapped) {
        const group = document.createElement('div');
        group.className = 'field-group';

        const header = document.createElement('div');
        header.className = 'field-group-header p-2 bg-light';
        header.innerHTML = `<strong>${title} (${fields.length})</strong>`;
        group.appendChild(header);

        const list = document.createElement('div');
        list.className = 'field-group-list';

        fields.forEach(field => {
            const item = document.createElement('div');
            item.className = `field-item p-2 border-bottom ${isMapped ? 'text-muted' : ''} ${this.selectedAvailableField === field ? 'selected' : ''}`;
            item.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <span>${field}</span>
                    ${isMapped ? '<i class="bi bi-link text-muted"></i>' : '<i class="bi bi-plus-circle text-success"></i>'}
                </div>
            `;
            item.onclick = () => this.selectAvailableField(field);
            list.appendChild(item);
        });

        group.appendChild(list);
        return group;
    },

    /**
     * Render mapped fields list.
     */
    renderMappedFields() {
        const container = document.getElementById('mappedFieldsList');
        container.innerHTML = '';

        if (Object.keys(this.currentMapping).length === 0) {
            container.innerHTML = '<div class="p-4 text-center text-muted">暂无映射字段</div>';
            return;
        }

        Object.entries(this.currentMapping).forEach(([targetField, sourceField]) => {
            const item = document.createElement('div');
            item.className = `mapped-field-item p-3 border-bottom ${this.selectedMappedField === targetField ? 'selected' : ''}`;

            const requiredField = this.requiredFields.find(f => f.name === targetField);
            const isRequired = requiredField !== undefined;

            item.innerHTML = `
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <strong>${sourceField}</strong>
                        <br>
                        <small class="text-muted">→ ${targetField}</small>
                        ${isRequired ? '<br><small class="text-primary"><i class="bi bi-star-fill"></i> 必需字段</small>' : ''}
                    </div>
                    <button class="btn btn-sm btn-outline-danger" onclick="FieldMapper.removeMapping('${targetField}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            `;
            item.onclick = (e) => {
                if (!e.target.closest('button')) {
                    this.selectMappedField(targetField);
                }
            };
            container.appendChild(item);
        });
    },

    /**
     * Select an available field.
     */
    selectAvailableField(field) {
        this.selectedAvailableField = field;
        this.renderAvailableFields();

        // Enable add button if field is not mapped
        const addBtn = document.getElementById('addFieldBtn');
        if (addBtn) {
            addBtn.disabled = Object.values(this.currentMapping).includes(field);
        }
    },

    /**
     * Select a mapped field.
     */
    selectMappedField(field) {
        this.selectedMappedField = field;
        this.renderMappedFields();

        // Enable remove button
        const removeBtn = document.getElementById('removeFieldBtn');
        if (removeBtn) {
            removeBtn.disabled = false;
        }
    },

    /**
     * Add selected field to mappings.
     */
    addSelectedField() {
        if (!this.selectedAvailableField) return;

        // Check if field is already mapped
        if (Object.values(this.currentMapping).includes(this.selectedAvailableField)) {
            return;
        }

        // Create a simple mapping using the field name as target
        const targetField = this.selectedAvailableField;
        this.currentMapping[targetField] = this.selectedAvailableField;

        // Refresh views
        this.renderAllFieldsView();

        // Reset selection
        this.selectedAvailableField = null;
        document.getElementById('addFieldBtn').disabled = true;
    },

    /**
     * Remove selected mapping.
     */
    removeSelectedField() {
        if (!this.selectedMappedField) return;

        this.removeMapping(this.selectedMappedField);
    },

    /**
     * Remove a field mapping.
     */
    removeMapping(targetField) {
        delete this.currentMapping[targetField];

        // Refresh views
        this.renderAllFieldsView();

        // Reset selection
        this.selectedMappedField = null;
        document.getElementById('removeFieldBtn').disabled = true;
    },

    /**
     * Update mapped count display.
     */
    updateMappedCount() {
        const countEl = document.getElementById('mappedCount');
        if (countEl) {
            countEl.textContent = Object.keys(this.currentMapping).length;
        }
    },

    /**
     * Filter fields in search.
     */
    filterFields(searchTerm) {
        const items = document.querySelectorAll('.field-item');
        const term = searchTerm.toLowerCase();

        items.forEach(item => {
            const text = item.textContent.toLowerCase();
            item.style.display = text.includes(term) ? 'block' : 'none';
        });
    },

    /**
     * Load required fields for the selected analysis type.
     */
    async loadRequiredFields() {
        try {
            const response = await fetch(`/api/mappings/fields/${this.analysisType}`);
            const data = await response.json();

            if (response.ok) {
                this.requiredFields = data.required_fields;
            } else {
                console.error('Failed to load required fields:', data);
            }
        } catch (error) {
            console.error('Error loading required fields:', error);
        }
    },

    /**
     * Get mapping suggestions from the server.
     */
    async getSuggestions() {
        try {
            const response = await fetch('/api/mappings/suggest', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    columns: this.columns,
                    analysis_type: this.analysisType
                })
            });

            const data = await response.json();

            if (response.ok) {
                this.currentMapping = data.suggested_mapping;
                this.fieldScores = data.field_scores;

                // Show confidence status
                const statusEl = document.getElementById('mappingStatus');
                const statusText = document.getElementById('mappingStatusText');
                statusEl.classList.remove('d-none');

                if (data.matched_template_id) {
                    statusText.textContent = `已匹配到保存的模板，置信度: ${(data.confidence * 100).toFixed(0)}%`;
                    statusEl.className = 'alert alert-success';
                } else if (data.confidence > 0.7) {
                    statusText.textContent = `自动匹配成功，置信度: ${(data.confidence * 100).toFixed(0)}%`;
                    statusEl.className = 'alert alert-success';
                } else if (data.confidence > 0.3) {
                    statusText.textContent = `部分字段已匹配，请检查并完成映射`;
                    statusEl.className = 'alert alert-warning';
                } else {
                    statusText.textContent = `无法自动匹配，请手动选择列映射`;
                    statusEl.className = 'alert alert-info';
                }

                this.renderMappingTable();
            }
        } catch (error) {
            console.error('Error getting suggestions:', error);
        }
    },

    /**
     * Render the mapping table.
     */
    renderMappingTable() {
        const tbody = document.getElementById('mappingTableBody');
        tbody.innerHTML = '';

        for (const field of this.requiredFields) {
            const row = document.createElement('tr');
            const mappedColumn = this.currentMapping[field.name] || '';
            const score = this.fieldScores[field.name] || 0;
            const isMapped = mappedColumn !== '';

            row.innerHTML = `
                <td>
                    <strong>${field.name}</strong>
                    <br><small class="text-muted">${field.description}</small>
                </td>
                <td>
                    <select class="form-select form-select-sm" 
                            id="mapping_${field.name}"
                            onchange="FieldMapper.onMappingChange('${field.name}', this.value)">
                        <option value="">-- 请选择 --</option>
                        ${this.columns.map(col => `
                            <option value="${col}" ${col === mappedColumn ? 'selected' : ''}>
                                ${col}
                            </option>
                        `).join('')}
                    </select>
                </td>
                <td>
                    <div class="progress progress-20">
                        <div class="progress-bar ${this.getScoreClass(score)}" 
                             role="progressbar" 
                             data-width="${score * 100}"
                             aria-valuenow="${score * 100}" 
                             aria-valuemin="0" 
                             aria-valuemax="100">
                            ${(score * 100).toFixed(0)}%
                        </div>
                    </div>
                </td>
                <td class="text-center">
                    ${isMapped
                    ? '<i class="bi bi-check-circle-fill text-success"></i>'
                    : '<i class="bi bi-x-circle-fill text-danger"></i>'}
                </td>
            `;

            tbody.appendChild(row);

            // Set progress bar width after adding to DOM
            const progressBar = row.querySelector('.progress-bar');
            if (progressBar) {
                progressBar.style.width = `${score * 100}%`;
            }
        }
    },

    /**
     * Get Bootstrap class for score progress bar.
     */
    getScoreClass(score) {
        if (score >= 0.8) return 'bg-success';
        if (score >= 0.5) return 'bg-warning';
        return 'bg-danger';
    },

    /**
     * Display suggested mappings with confidence scores.
     * @param {Object} mappings - Suggested field mappings
     * @param {string[]} columns - Available columns
     */
    displaySuggestedMappings(mappings, columns) {
        this.currentMapping = mappings || {};
        this.columns = columns || [];

        // Render the mapping table with suggestions
        this.renderMappingTable();
    },

    /**
     * Update a single field mapping.
     * @param {string} targetField - Target field name
     * @param {string} sourceColumn - Source column name
     */
    updateMapping(targetField, sourceColumn) {
        if (sourceColumn) {
            this.currentMapping[targetField] = sourceColumn;
            this.fieldScores[targetField] = 1.0; // Manual selection = 100% confidence
        } else {
            delete this.currentMapping[targetField];
            this.fieldScores[targetField] = 0;
        }

        this.renderMappingTable();
        this.validateMapping();
    },

    /**
     * Add a new field mapping.
     * @param {string} targetField - Target field name
     * @param {string} sourceColumn - Source column name
     */
    addMapping(targetField, sourceColumn) {
        if (!targetField || !sourceColumn) {
            console.warn('Both targetField and sourceColumn are required');
            return;
        }

        this.currentMapping[targetField] = sourceColumn;
        this.fieldScores[targetField] = 1.0;

        this.renderMappingTable();
        this.validateMapping();
    },

    /**
     * Remove a field mapping.
     * @param {string} targetField - Target field name to remove
     */
    removeMapping(targetField) {
        delete this.currentMapping[targetField];
        delete this.fieldScores[targetField];

        this.renderMappingTable();
        this.validateMapping();
    },

    /**
     * Validate the current mapping.
     * @returns {Object} Validation result with isValid and missingFields
     */
    async validate() {
        if (!this.analysisType) {
            return {
                isValid: false,
                missingFields: [],
                message: '请先选择分析类型'
            };
        }

        try {
            const response = await fetch('/api/mappings/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    mapping: this.currentMapping,
                    analysis_type: this.analysisType,
                    columns: this.columns
                })
            });

            const data = await response.json();

            // Update UI with validation result
            const resultEl = document.getElementById('validationResult');
            const alertEl = document.getElementById('validationAlert');
            const iconEl = document.getElementById('validationIcon');
            const messageEl = document.getElementById('validationMessage');

            if (resultEl && alertEl && iconEl && messageEl) {
                resultEl.classList.remove('d-none');

                if (data.is_valid) {
                    alertEl.className = 'alert alert-success';
                    iconEl.className = 'bi bi-check-circle-fill me-2';
                    messageEl.textContent = '所有必需字段已映射，可以开始分析';
                } else {
                    alertEl.className = 'alert alert-danger';
                    iconEl.className = 'bi bi-exclamation-triangle-fill me-2';
                    messageEl.textContent = `缺少必需字段: ${data.missing_fields.join(', ')}`;
                }
            }

            return {
                isValid: data.is_valid,
                missingFields: data.missing_fields || [],
                message: data.message || ''
            };
        } catch (error) {
            console.error('Error validating mapping:', error);
            return {
                isValid: false,
                missingFields: [],
                message: '验证失败，请重试'
            };
        }
    },

    /**
     * Save current mapping as a template.
     * @param {string} name - Template name
     * @returns {Promise<boolean>} Success status
     */
    async saveAsTemplate(name) {
        if (!name || !name.trim()) {
            alert('请输入模板名称');
            return false;
        }

        if (Object.keys(this.currentMapping).length === 0) {
            alert('请先配置字段映射');
            return false;
        }

        if (!this.analysisType) {
            alert('请先选择分析类型');
            return false;
        }

        try {
            const response = await fetch('/api/mappings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name.trim(),
                    mapping: this.currentMapping,
                    analysis_type: this.analysisType
                })
            });

            const data = await response.json();

            if (response.ok) {
                alert('模板保存成功');

                // Clear template name input if it exists
                const nameInput = document.getElementById('templateName');
                if (nameInput) {
                    nameInput.value = '';
                }

                // Reload templates list
                await this.loadSavedTemplates();

                return true;
            } else {
                alert(`保存失败: ${data.message || '未知错误'}`);
                return false;
            }
        } catch (error) {
            console.error('Error saving template:', error);
            alert('保存模板时发生错误');
            return false;
        }
    },

    /**
     * Handle mapping change.
     */
    onMappingChange(fieldName, columnName) {
        this.updateMapping(fieldName, columnName);
    },

    /**
     * Validate the current mapping.
     */
    async validateMapping() {
        try {
            const response = await fetch('/api/mappings/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    mapping: this.currentMapping,
                    analysis_type: this.analysisType,
                    columns: this.columns
                })
            });

            const data = await response.json();

            const resultEl = document.getElementById('validationResult');
            const alertEl = document.getElementById('validationAlert');
            const iconEl = document.getElementById('validationIcon');
            const messageEl = document.getElementById('validationMessage');

            resultEl.classList.remove('d-none');

            if (data.is_valid) {
                alertEl.className = 'alert alert-success';
                iconEl.className = 'bi bi-check-circle-fill me-2';
                messageEl.textContent = '所有必需字段已映射，可以开始分析';
            } else {
                alertEl.className = 'alert alert-danger';
                iconEl.className = 'bi bi-exclamation-triangle-fill me-2';
                messageEl.textContent = `缺少必需字段: ${data.missing_fields.join(', ')}`;
            }

            return data.is_valid;
        } catch (error) {
            console.error('Error validating mapping:', error);
            return false;
        }
    },

    /**
     * Save current mapping as a template.
     */
    async saveTemplate() {
        const nameInput = document.getElementById('templateName');
        const name = nameInput.value.trim();

        if (!name) {
            alert('请输入模板名称');
            return;
        }

        if (Object.keys(this.currentMapping).length === 0) {
            alert('请先配置字段映射');
            return;
        }

        try {
            const response = await fetch('/api/mappings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    mapping: this.currentMapping,
                    analysis_type: this.analysisType
                })
            });

            const data = await response.json();

            if (response.ok) {
                alert('模板保存成功');
                nameInput.value = '';
                await this.loadSavedTemplates();
            } else {
                alert(`保存失败: ${data.message}`);
            }
        } catch (error) {
            console.error('Error saving template:', error);
            alert('保存模板时发生错误');
        }
    },

    /**
     * Load saved templates for the current analysis type.
     */
    async loadSavedTemplates() {
        try {
            const response = await fetch(`/api/mappings?analysis_type=${this.analysisType}`);
            const data = await response.json();

            const select = document.getElementById('savedTemplates');
            select.innerHTML = '<option value="">加载已保存的模板...</option>';

            if (response.ok && data.templates) {
                for (const template of data.templates) {
                    const option = document.createElement('option');
                    option.value = template.id;
                    option.textContent = template.name;
                    select.appendChild(option);
                }
            }
        } catch (error) {
            console.error('Error loading templates:', error);
        }
    },

    /**
     * Load a saved template.
     */
    async loadTemplate() {
        const select = document.getElementById('savedTemplates');
        const templateId = select.value;

        if (!templateId) return;

        try {
            const response = await fetch(`/api/mappings/${templateId}`);
            const data = await response.json();

            if (response.ok) {
                this.currentMapping = data.mapping;

                // Update field scores for loaded template
                for (const field of Object.keys(this.currentMapping)) {
                    this.fieldScores[field] = 1.0;
                }

                this.renderMappingTable();
                this.validateMapping();

                // Update status
                const statusEl = document.getElementById('mappingStatus');
                const statusText = document.getElementById('mappingStatusText');
                statusEl.classList.remove('d-none');
                statusEl.className = 'alert alert-success';
                statusText.textContent = `已加载模板: ${data.name}`;
            }
        } catch (error) {
            console.error('Error loading template:', error);
        }
    },

    /**
     * Get the current mapping.
     * @returns {Object} Current field mapping
     */
    getMapping() {
        return this.currentMapping;
    },

    /**
     * Check if mapping is valid.
     * @returns {boolean} True if all required fields are mapped
     */
    isValid() {
        for (const field of this.requiredFields) {
            if (!this.currentMapping[field.name]) {
                return false;
            }
        }
        return true;
    }
};
