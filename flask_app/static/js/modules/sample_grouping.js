/**
 * Sample Grouping Module for Immune Repertoire Analysis Web Application
 * Provides functionality for managing sample groups and multi-group selection.
 * 
 * Requirements: 16.1, 16.3
 */

const SampleGrouping = {
    groups: [],           // All defined groups
    selectedGroups: [],   // Currently selected groups (multi-select)
    samples: [],          // Available samples
    fileId: null,         // Associated file ID
    draggedItem: null,    // Currently dragged item for reordering

    // Predefined color palette for group identification
    colorPalette: [
        '#3498db', // Blue
        '#27ae60', // Green
        '#e74c3c', // Red
        '#9b59b6', // Purple
        '#f39c12', // Orange
        '#1abc9c', // Teal
        '#e91e63', // Pink
        '#00bcd4', // Cyan
        '#ff5722', // Deep Orange
        '#607d8b'  // Blue Grey
    ],

    /**
     * Initialize the module with available samples
     * @param {Array} samples - List of available sample identifiers
     * @param {string} fileId - Associated file ID
     */
    init(samples, fileId) {
        this.samples = samples || [];
        this.fileId = fileId;
        this.selectedGroups = [];
        this.loadGroups();
    },

    /**
     * Get color for a group based on its index
     * @param {number} index - Group index
     * @returns {string} Color hex code
     */
    getGroupColor(index) {
        return this.colorPalette[index % this.colorPalette.length];
    },

    /**
     * Get color for a group by ID
     * @param {string} groupId - Group ID
     * @returns {string} Color hex code
     */
    getGroupColorById(groupId) {
        const index = this.groups.findIndex(g => g.id === groupId);
        return index >= 0 ? this.getGroupColor(index) : this.colorPalette[0];
    },

    /**
     * Load existing groups from the server
     */
    async loadGroups() {
        try {
            const params = this.fileId ? `?file_id=${this.fileId}` : '';
            const response = await fetch(`/api/groups${params}`);
            if (response.ok) {
                const data = await response.json();
                this.groups = data.groups || [];
            }
        } catch (error) {
            console.error('Failed to load groups:', error);
        }
    },

    /**
     * Render the group selector UI (multi-select mode)
     * @param {string} containerId - Container element ID
     */
    renderGroupSelector(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;

        let html = `
            <div class="sample-grouping-container">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h6 class="mb-0">Sample Groups</h6>
                    <div class="btn-group btn-group-sm">
                        <button type="button" class="btn btn-outline-secondary" onclick="SampleGrouping.selectAllGroups()" title="Select All">
                            <i class="bi bi-check-all"></i>
                        </button>
                        <button type="button" class="btn btn-outline-secondary" onclick="SampleGrouping.deselectAllGroups()" title="Deselect All">
                            <i class="bi bi-x-lg"></i>
                        </button>
                        <button type="button" class="btn btn-outline-primary" onclick="SampleGrouping.showCreateDialog()">
                            <i class="bi bi-plus-lg"></i> New
                        </button>
                    </div>
                </div>
                
                <p class="text-muted small mb-2">
                    <i class="bi bi-grip-vertical"></i> Drag to reorder groups
                </p>
                
                <div class="group-list" id="groupList">
                    ${this.renderGroupList()}
                </div>
                
                <div class="selected-groups-summary mt-3" id="selectedGroupsSummary">
                    ${this.renderSelectedSummary()}
                </div>
            </div>
        `;

        container.innerHTML = html;

        // Initialize drag and drop
        this.initDragAndDrop();
    },

    /**
     * Initialize drag and drop functionality for group reordering
     */
    initDragAndDrop() {
        const groupList = document.getElementById('groupList');
        if (!groupList) return;

        const items = groupList.querySelectorAll('.group-item');

        items.forEach(item => {
            item.addEventListener('dragstart', (e) => this.handleDragStart(e));
            item.addEventListener('dragend', (e) => this.handleDragEnd(e));
            item.addEventListener('dragover', (e) => this.handleDragOver(e));
            item.addEventListener('dragenter', (e) => this.handleDragEnter(e));
            item.addEventListener('dragleave', (e) => this.handleDragLeave(e));
            item.addEventListener('drop', (e) => this.handleDrop(e));
        });
    },

    /**
     * Handle drag start event
     */
    handleDragStart(e) {
        this.draggedItem = e.target.closest('.group-item');
        if (this.draggedItem) {
            this.draggedItem.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', this.draggedItem.dataset.groupId);
        }
    },

    /**
     * Handle drag end event
     */
    handleDragEnd(e) {
        if (this.draggedItem) {
            this.draggedItem.classList.remove('dragging');
        }

        // Remove drag-over class from all items
        document.querySelectorAll('.group-item').forEach(item => {
            item.classList.remove('drag-over');
        });

        this.draggedItem = null;
    },

    /**
     * Handle drag over event
     */
    handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
    },

    /**
     * Handle drag enter event
     */
    handleDragEnter(e) {
        e.preventDefault();
        const item = e.target.closest('.group-item');
        if (item && item !== this.draggedItem) {
            item.classList.add('drag-over');
        }
    },

    /**
     * Handle drag leave event
     */
    handleDragLeave(e) {
        const item = e.target.closest('.group-item');
        if (item) {
            item.classList.remove('drag-over');
        }
    },

    /**
     * Handle drop event
     */
    handleDrop(e) {
        e.preventDefault();
        const targetItem = e.target.closest('.group-item');

        if (targetItem && this.draggedItem && targetItem !== this.draggedItem) {
            const draggedId = this.draggedItem.dataset.groupId;
            const targetId = targetItem.dataset.groupId;

            // Reorder groups array
            const draggedIndex = this.groups.findIndex(g => g.id === draggedId);
            const targetIndex = this.groups.findIndex(g => g.id === targetId);

            if (draggedIndex !== -1 && targetIndex !== -1) {
                const [removed] = this.groups.splice(draggedIndex, 1);
                this.groups.splice(targetIndex, 0, removed);

                // Re-render the list
                const groupList = document.getElementById('groupList');
                if (groupList) {
                    groupList.innerHTML = this.renderGroupList();
                    this.initDragAndDrop();
                }

                // Trigger reorder event
                this.onGroupReorder();
            }
        }

        targetItem?.classList.remove('drag-over');
    },

    /**
     * Select all groups
     */
    selectAllGroups() {
        this.selectedGroups = this.groups.map(g => g.id);

        // Update checkboxes
        this.groups.forEach(group => {
            const checkbox = document.getElementById(`group_${group.id}`);
            if (checkbox) checkbox.checked = true;
        });

        // Update summary
        const summaryEl = document.getElementById('selectedGroupsSummary');
        if (summaryEl) {
            summaryEl.innerHTML = this.renderSelectedSummary();
        }

        this.onSelectionChange();
    },

    /**
     * Deselect all groups
     */
    deselectAllGroups() {
        this.selectedGroups = [];

        // Update checkboxes
        this.groups.forEach(group => {
            const checkbox = document.getElementById(`group_${group.id}`);
            if (checkbox) checkbox.checked = false;
        });

        // Update summary
        const summaryEl = document.getElementById('selectedGroupsSummary');
        if (summaryEl) {
            summaryEl.innerHTML = this.renderSelectedSummary();
        }

        this.onSelectionChange();
    },

    /**
     * Callback for group reorder - override this to handle reorder events
     */
    onGroupReorder() {
        // Override this method to handle group reorder events
        document.dispatchEvent(new CustomEvent('groupReordered', { detail: this.groups }));
    },

    /**
     * Render the list of groups with checkboxes
     */
    renderGroupList() {
        if (this.groups.length === 0) {
            return '<p class="text-muted small">No groups defined. Create a new group to get started.</p>';
        }

        return this.groups.map((group, index) => {
            const color = this.getGroupColor(index);
            const isSelected = this.selectedGroups.includes(group.id);

            return `
            <div class="group-item d-flex align-items-center p-2 border-bottom ${isSelected ? 'selected' : ''}" 
                 draggable="true" 
                 data-group-id="${group.id}"
                 data-group-index="${index}">
                <div class="drag-handle me-2" title="Drag to reorder">
                    <i class="bi bi-grip-vertical text-muted"></i>
                </div>
                <div class="group-color-indicator me-2" style="background-color: ${color};" title="Group color"></div>
                <div class="form-check flex-grow-1">
                    <input class="form-check-input" type="checkbox" 
                           id="group_${group.id}" 
                           value="${group.id}"
                           ${isSelected ? 'checked' : ''}
                           onchange="SampleGrouping.toggleGroupSelection('${group.id}', this.checked)">
                    <label class="form-check-label" for="group_${group.id}">
                        <strong>${this.escapeHtml(group.name)}</strong>
                        <span class="text-muted small ms-2">(${group.sample_count || group.sample_ids?.length || 0} samples)</span>
                    </label>
                </div>
                <div class="group-actions">
                    <button type="button" class="btn btn-sm btn-link text-primary p-0 me-2" 
                            onclick="SampleGrouping.showEditDialog('${group.id}')" title="Edit">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-link text-danger p-0" 
                            onclick="SampleGrouping.deleteGroup('${group.id}')" title="Delete">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </div>
        `}).join('');
    },

    /**
     * Render summary of selected groups
     */
    renderSelectedSummary() {
        if (this.selectedGroups.length === 0) {
            return '<p class="text-muted small mb-0">No groups selected</p>';
        }

        const selectedGroupInfo = this.selectedGroups.map(id => {
            const index = this.groups.findIndex(g => g.id === id);
            const group = this.groups[index];
            return {
                name: group ? group.name : id,
                color: index >= 0 ? this.getGroupColor(index) : this.colorPalette[0]
            };
        });

        return `
            <div class="alert alert-info py-2 mb-0">
                <div class="d-flex align-items-center flex-wrap">
                    <strong class="me-2">${this.selectedGroups.length}</strong> group(s) selected: 
                    ${selectedGroupInfo.map(info => `
                        <span class="badge me-1 mb-1" style="background-color: ${info.color}; color: white;">
                            ${this.escapeHtml(info.name)}
                        </span>
                    `).join('')}
                </div>
            </div>
        `;
    },

    /**
     * Toggle group selection
     * @param {string} groupId - Group ID
     * @param {boolean} selected - Whether the group is selected
     */
    toggleGroupSelection(groupId, selected) {
        if (selected) {
            if (!this.selectedGroups.includes(groupId)) {
                this.selectedGroups.push(groupId);
            }
        } else {
            this.selectedGroups = this.selectedGroups.filter(id => id !== groupId);
        }

        // Update summary
        const summaryEl = document.getElementById('selectedGroupsSummary');
        if (summaryEl) {
            summaryEl.innerHTML = this.renderSelectedSummary();
        }

        // Trigger change event
        this.onSelectionChange();
    },

    /**
     * Get all selected groups
     * @returns {Array} List of selected group objects
     */
    getSelectedGroups() {
        return this.selectedGroups.map(id => this.groups.find(g => g.id === id)).filter(g => g);
    },

    /**
     * Get selected group IDs
     * @returns {Array} List of selected group IDs
     */
    getSelectedGroupIds() {
        return [...this.selectedGroups];
    },

    /**
     * Show create group dialog
     */
    showCreateDialog() {
        this.showGroupDialog(null);
    },

    /**
     * Show edit group dialog
     * @param {string} groupId - Group ID to edit
     */
    showEditDialog(groupId) {
        const group = this.groups.find(g => g.id === groupId);
        if (group) {
            this.showGroupDialog(group);
        }
    },

    /**
     * Show group create/edit dialog
     * @param {Object|null} group - Group to edit, or null for new group
     */
    showGroupDialog(group) {
        const isEdit = group !== null;
        const title = isEdit ? 'Edit Group' : 'Create New Group';

        // Create modal HTML
        const modalHtml = `
            <div class="modal fade" id="groupModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">${title}</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <form id="groupForm">
                                <div class="mb-3">
                                    <label for="groupName" class="form-label">Group Name</label>
                                    <input type="text" class="form-control" id="groupName" 
                                           value="${isEdit ? this.escapeHtml(group.name) : ''}" required>
                                </div>
                                <div class="mb-3">
                                    <label for="groupDescription" class="form-label">Description (optional)</label>
                                    <textarea class="form-control" id="groupDescription" rows="2">${isEdit ? this.escapeHtml(group.description || '') : ''}</textarea>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">Select Samples</label>
                                    <div class="sample-selection-list border rounded p-2" style="max-height: 200px; overflow-y: auto;">
                                        ${this.renderSampleCheckboxes(isEdit ? group.sample_ids : [])}
                                    </div>
                                    <div class="mt-2">
                                        <button type="button" class="btn btn-sm btn-outline-secondary me-1" onclick="SampleGrouping.selectAllSamples()">Select All</button>
                                        <button type="button" class="btn btn-sm btn-outline-secondary" onclick="SampleGrouping.deselectAllSamples()">Deselect All</button>
                                    </div>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                            <button type="button" class="btn btn-primary" onclick="SampleGrouping.saveGroup('${isEdit ? group.id : ''}')">
                                ${isEdit ? 'Update' : 'Create'}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if any
        const existingModal = document.getElementById('groupModal');
        if (existingModal) {
            existingModal.remove();
        }

        // Add modal to body
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('groupModal'));
        modal.show();
    },

    /**
     * Render sample checkboxes for group dialog
     * @param {Array} selectedSamples - List of pre-selected sample IDs
     */
    renderSampleCheckboxes(selectedSamples) {
        if (this.samples.length === 0) {
            return '<p class="text-muted small mb-0">No samples available</p>';
        }

        return this.samples.map(sample => `
            <div class="form-check">
                <input class="form-check-input sample-checkbox" type="checkbox" 
                       id="sample_${this.escapeHtml(sample)}" 
                       value="${this.escapeHtml(sample)}"
                       ${selectedSamples.includes(sample) ? 'checked' : ''}>
                <label class="form-check-label" for="sample_${this.escapeHtml(sample)}">
                    ${this.escapeHtml(sample)}
                </label>
            </div>
        `).join('');
    },

    /**
     * Select all samples in the dialog
     */
    selectAllSamples() {
        document.querySelectorAll('.sample-checkbox').forEach(cb => cb.checked = true);
    },

    /**
     * Deselect all samples in the dialog
     */
    deselectAllSamples() {
        document.querySelectorAll('.sample-checkbox').forEach(cb => cb.checked = false);
    },

    /**
     * Save group (create or update)
     * @param {string} groupId - Group ID for update, empty for create
     */
    async saveGroup(groupId) {
        const name = document.getElementById('groupName').value.trim();
        const description = document.getElementById('groupDescription').value.trim();
        const sampleIds = Array.from(document.querySelectorAll('.sample-checkbox:checked'))
            .map(cb => cb.value);

        if (!name) {
            alert('请输入分组名称');
            return;
        }

        if (sampleIds.length === 0) {
            alert('请至少选择一个样本');
            return;
        }

        const data = {
            name: name,
            sample_ids: sampleIds,
            description: description || null,
            file_id: this.fileId
        };

        try {
            const url = groupId ? `/api/groups/${groupId}` : '/api/groups';
            const method = groupId ? 'PUT' : 'POST';

            const response = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });

            if (response.ok) {
                // Close modal
                const modal = bootstrap.Modal.getInstance(document.getElementById('groupModal'));
                modal.hide();

                // Reload groups and refresh UI
                await this.loadGroups();
                const groupList = document.getElementById('groupList');
                if (groupList) {
                    groupList.innerHTML = this.renderGroupList();
                }

                // Show success message
                if (typeof Utils !== 'undefined' && Utils.showToast) {
                    Utils.showToast(groupId ? '分组更新成功' : '分组创建成功', 'success');
                }
            } else {
                const error = await response.json();
                alert(error.message || '保存分组失败');
            }
        } catch (error) {
            console.error('Failed to save group:', error);
            alert('保存分组失败');
        }
    },

    /**
     * Delete a group
     * @param {string} groupId - Group ID to delete
     */
    async deleteGroup(groupId) {
        const group = this.groups.find(g => g.id === groupId);
        if (!group) return;

        if (!confirm(`确定要删除分组"${group.name}"吗？`)) {
            return;
        }

        try {
            const response = await fetch(`/api/groups/${groupId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                // Remove from selected if selected
                this.selectedGroups = this.selectedGroups.filter(id => id !== groupId);

                // Reload groups and refresh UI
                await this.loadGroups();
                const groupList = document.getElementById('groupList');
                if (groupList) {
                    groupList.innerHTML = this.renderGroupList();
                }

                const summaryEl = document.getElementById('selectedGroupsSummary');
                if (summaryEl) {
                    summaryEl.innerHTML = this.renderSelectedSummary();
                }

                // Show success message
                if (typeof Utils !== 'undefined' && Utils.showToast) {
                    Utils.showToast('分组删除成功', 'success');
                }
            } else {
                const error = await response.json();
                alert(error.message || '删除分组失败');
            }
        } catch (error) {
            console.error('Failed to delete group:', error);
            alert('删除分组失败');
        }
    },

    /**
     * Calculate averages for selected groups
     * @param {Array} metricFields - List of metric field names
     * @param {string} sampleColumn - Name of the sample column
     * @returns {Promise<Object>} Averages result
     */
    async calculateGroupAverages(metricFields, sampleColumn = 'sample') {
        if (this.selectedGroups.length === 0) {
            return { averages: {}, group_info: {} };
        }

        if (!this.fileId) {
            throw new Error('No file associated with groups');
        }

        try {
            const response = await fetch('/api/groups/averages', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    group_ids: this.selectedGroups,
                    metric_fields: metricFields,
                    file_id: this.fileId,
                    sample_column: sampleColumn
                })
            });

            if (response.ok) {
                return await response.json();
            } else {
                const error = await response.json();
                throw new Error(error.message || 'Failed to calculate averages');
            }
        } catch (error) {
            console.error('Failed to calculate group averages:', error);
            throw error;
        }
    },

    /**
     * Callback for selection changes - override this to handle selection changes
     */
    onSelectionChange() {
        // Override this method to handle selection changes
        // Example: document.dispatchEvent(new CustomEvent('groupSelectionChanged', { detail: this.getSelectedGroups() }));
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
    module.exports = SampleGrouping;
}
