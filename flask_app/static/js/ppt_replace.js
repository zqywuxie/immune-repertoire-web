/**
 * PPT Image Replacement Module
 * Handles PPT upload, analysis, and image replacement for various types:
 * - Sharing Analysis heatmaps
 * - Network Plots
 * - Isotype Upset Plots
 * - Tree Maps
 * 
 * Requirements: 9.2, 9.7 - Tab management and state persistence
 */
const PPTReplace = {
    sessionId: null,
    pptFile: null,
    slideData: [],
    mappings: [],
    availableImages: {},
    currentTab: 'sharing_analysis',
    tabManager: null,
    tabStates: {},  // Store state for each tab
    operationHistory: [],  // Store operation history for deduplication
    maxHistoryItems: 20,  // Maximum history items to keep

    // Multi-module session management (Requirement 1, 2)
    session: {
        id: null,
        filename: null,
        uploadTime: null,
        moduleStatus: {
            'sharing_analysis': { replaced: false, count: 0, timestamp: null, mappings: [] },
            'network_plots': { replaced: false, count: 0, timestamp: null, mappings: [] },
            'isotype_upset': { replaced: false, count: 0, timestamp: null, mappings: [] },
            'tree_maps': { replaced: false, count: 0, timestamp: null, mappings: [] }
        },
        replacementHistory: [],
        totalReplaced: 0
    },

    // PPT Preview state (Requirement 4, 5)
    preview: {
        slides: [],
        currentSlide: 0,
        zoomLevel: 1,
        isLoading: false
    },

    // Image type constants
    IMAGE_TYPES: {
        SHARING_ANALYSIS: 'sharing_analysis',
        NETWORK_PLOTS: 'network_plots',
        ISOTYPE_UPSET: 'isotype_upset',
        TREE_MAPS: 'tree_maps'
    },

    // Tab to image type mapping
    TAB_TO_IMAGE_TYPE: {
        'sharing-analysis': 'sharing_analysis',
        'network-plots': 'network_plots',
        'isotype-upset': 'isotype_upset',
        'tree-maps': 'tree_maps'
    },

    // Image type to tab ID mapping (reverse)
    IMAGE_TYPE_TO_TAB: {
        'sharing_analysis': 'sharing-analysis',
        'network_plots': 'network-plots',
        'isotype_upset': 'isotype-upset',
        'tree_maps': 'tree-maps'
    },

    // Image type display names
    IMAGE_TYPE_NAMES: {
        'sharing_analysis': 'Sharing Analysis 热图',
        'network_plots': 'Network Plots 网络图',
        'isotype_upset': 'Isotype Upset Plots',
        'tree_maps': 'Tree Maps 树图'
    },

    // Tab configuration with keywords and descriptions
    TAB_CONFIG: {
        'sharing-analysis': {
            id: 'sharing-analysis',
            title: 'Sharing Analysis',
            icon: 'bi-grid-3x3',
            keywords: [
                'Sharing Analysis - IGH',
                'Sharing Analysis - IGK',
                'Sharing Analysis - IGL',
                'Sharing Analysis - TRA',
                'Sharing Analysis - TRB',
                'Sharing Analysis - TRD',
                'Sharing Analysis - TRG'
            ],
            description: '相似度热图替换，每条链2个页面，每页3个热图。第一页：Expression、R² Outer、R² Inner；第二页：Morisita-Horn、uCDR3、Sorensen',
            badgeClass: 'bg-primary',
            folderHint: '需要 IGH/IGK/IGL/TRA/TRB/TRD/TRG 子目录，每个目录包含热图PNG文件'
        },
        'network-plots': {
            id: 'network-plots',
            title: 'Network Plots',
            icon: 'bi-diagram-3',
            keywords: ['Network Plots'],
            description: 'CDR3序列网络图替换，根据样本数量动态布局，每页最多6个样本图片',
            badgeClass: 'bg-warning text-dark',
            folderHint: '文件格式: {样本名}_cdr3_network.png 或 network_plots/ 子目录'
        },
        'isotype-upset': {
            id: 'isotype-upset',
            title: 'Isotype Upset Plots',
            icon: 'bi-bar-chart-steps',
            keywords: ['Isotype Upset Plots'],
            description: '同型体UpSet图替换，支持多样本布局，根据样本数量自动调整行列',
            badgeClass: 'bg-success',
            folderHint: '文件格式: {样本名}_isotype_upset.png 或 isotype_upset/ 子目录'
        },
        'tree-maps': {
            id: 'tree-maps',
            title: 'Tree Maps',
            icon: 'bi-diagram-2',
            keywords: ['Multi-chain Tree Maps'],
            description: '树图替换，支持层次化数据展示',
            badgeClass: 'bg-info',
            folderHint: '文件格式: {样本名}_treemap.png 或 individual_treemaps/ 子目录'
        }
    },

    // Per-tab image source storage
    tabImageSources: {
        'sharing-analysis': { type: null, value: null, scannedImages: null },
        'network-plots': { type: null, value: null, scannedImages: null },
        'isotype-upset': { type: null, value: null, scannedImages: null },
        'tree-maps': { type: null, value: null, scannedImages: null }
    },

    // Current tab's layout configuration (for drag-drop)
    currentLayoutConfig: null,

    // Comparison mode state
    comparisonMode: {
        enabled: false,
        sources: [],  // Array of { path: string, projectName: string, scannedImages: object }
        nextId: 1
    },

    /**
     * Initialize the PPT Replace module
     * Requirements: 9.2, 9.7
     */
    init() {
        this.initializeTabStates();
        this.initializeTabImageSources();
        this.initializeSession();  // New: Initialize session management
        this.initializeBorderConfig();  // New: Initialize border configuration
        this.initializeComparisonMode();  // New: Initialize comparison mode
        this.bindEvents();
        this.bindTabEvents();
        this.bindBorderConfigEvents();  // New: Bind border config events
        this.bindComparisonModeEvents();  // New: Bind comparison mode events
        this.loadAnalysisList();
        this.restoreTabState();
        this.restoreSession();  // New: Restore session from storage
        this.updateTabBadges();
        this.renderReplacementHistoryPanel();  // New: Render history panel
        console.log('PPTReplace initialized with multi-module and comparison support');
    },

    /**
     * Initialize comparison mode
     */
    initializeComparisonMode() {
        this.comparisonMode = {
            enabled: false,
            sources: [],
            nextId: 1
        };
    },

    /**
     * Bind comparison mode events
     */
    bindComparisonModeEvents() {
        // Mode selection radio buttons
        const modeReplace = document.getElementById('modeReplace');
        const modeComparison = document.getElementById('modeComparison');
        const addSourceBtn = document.getElementById('addComparisonSourceBtn');

        if (modeReplace) {
            modeReplace.addEventListener('change', () => this.setComparisonMode(false));
        }
        if (modeComparison) {
            modeComparison.addEventListener('change', () => this.setComparisonMode(true));
        }
        if (addSourceBtn) {
            addSourceBtn.addEventListener('click', () => this.addComparisonSource());
        }
    },

    /**
     * Set comparison mode on/off
     * @param {boolean} enabled - Whether comparison mode is enabled
     */
    setComparisonMode(enabled) {
        this.comparisonMode.enabled = enabled;
        
        const singleSourceInput = document.getElementById('singleSourceInput');
        const multiSourceInput = document.getElementById('multiSourceInput');
        const comparisonModeBadge = document.getElementById('comparisonModeBadge');
        const modeDescription = document.getElementById('modeDescription');
        
        if (enabled) {
            // Switch to comparison mode
            if (singleSourceInput) singleSourceInput.style.display = 'none';
            if (multiSourceInput) multiSourceInput.style.display = 'block';
            if (comparisonModeBadge) comparisonModeBadge.style.display = 'inline-block';
            if (modeDescription) {
                modeDescription.textContent = '多图对比：在同一指标下并排展示多个项目的热图，便于比较';
            }
            
            // Add initial comparison sources if empty
            if (this.comparisonMode.sources.length === 0) {
                this.addComparisonSource();
                this.addComparisonSource();
            }
        } else {
            // Switch to replace mode
            if (singleSourceInput) singleSourceInput.style.display = 'block';
            if (multiSourceInput) multiSourceInput.style.display = 'none';
            if (comparisonModeBadge) comparisonModeBadge.style.display = 'none';
            if (modeDescription) {
                modeDescription.textContent = '单图替换：将PPT中的图片替换为新图片';
            }
        }
        
        this.updateScanButton();
        console.log('Comparison mode:', enabled);
    },

    /**
     * Add a comparison source item
     */
    addComparisonSource() {
        const sourceId = this.comparisonMode.nextId++;
        const source = {
            id: sourceId,
            path: '',
            projectName: `项目${sourceId}`,
            scannedImages: null
        };
        
        this.comparisonMode.sources.push(source);
        this.renderComparisonSourcesList();
        this.updateScanButton();
    },

    /**
     * Remove a comparison source item
     * @param {number} sourceId - ID of the source to remove
     */
    removeComparisonSource(sourceId) {
        this.comparisonMode.sources = this.comparisonMode.sources.filter(s => s.id !== sourceId);
        this.renderComparisonSourcesList();
        this.updateScanButton();
    },

    /**
     * Update a comparison source
     * @param {number} sourceId - ID of the source to update
     * @param {string} field - Field to update ('path' or 'projectName')
     * @param {string} value - New value
     */
    updateComparisonSource(sourceId, field, value) {
        const source = this.comparisonMode.sources.find(s => s.id === sourceId);
        if (source) {
            source[field] = value;
            this.updateScanButton();
        }
    },

    /**
     * Render the comparison sources list
     */
    renderComparisonSourcesList() {
        const container = document.getElementById('comparisonSourcesList');
        if (!container) return;
        
        let html = '';
        this.comparisonMode.sources.forEach((source, index) => {
            html += `
                <div class="comparison-source-item" data-source-id="${source.id}">
                    <span class="source-number">${index + 1}</span>
                    ${this.comparisonMode.sources.length > 2 ? `
                        <button type="button" class="btn btn-outline-danger btn-sm remove-source-btn" 
                            onclick="PPTReplace.removeComparisonSource(${source.id})" title="移除">
                            <i class="bi bi-x"></i>
                        </button>
                    ` : ''}
                    <div class="row g-2">
                        <div class="col-md-7">
                            <input type="text" class="form-control form-control-sm" 
                                placeholder="输入图片文件夹路径" 
                                value="${source.path}"
                                onchange="PPTReplace.updateComparisonSource(${source.id}, 'path', this.value)">
                        </div>
                        <div class="col-md-5">
                            <input type="text" class="form-control form-control-sm" 
                                placeholder="项目名称" 
                                value="${source.projectName}"
                                onchange="PPTReplace.updateComparisonSource(${source.id}, 'projectName', this.value)">
                        </div>
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html;
    },

    /**
     * Initialize session management
     * Requirements: Req 1, 2
     */
    initializeSession() {
        this.session = {
            id: null,
            filename: null,
            uploadTime: null,
            moduleStatus: {
                'sharing_analysis': { replaced: false, count: 0, timestamp: null, mappings: [] },
                'network_plots': { replaced: false, count: 0, timestamp: null, mappings: [] },
                'isotype_upset': { replaced: false, count: 0, timestamp: null, mappings: [] },
                'tree_maps': { replaced: false, count: 0, timestamp: null, mappings: [] }
            },
            replacementHistory: [],
            totalReplaced: 0
        };
    },

    /**
     * Save session to localStorage
     * Requirements: Req 6
     */
    saveSession() {
        try {
            const sessionData = {
                id: this.sessionId,
                filename: this.pptFile ? this.pptFile.name : null,
                uploadTime: this.session.uploadTime,
                moduleStatus: this.session.moduleStatus,
                replacementHistory: this.session.replacementHistory,
                totalReplaced: this.session.totalReplaced
            };
            localStorage.setItem('pptReplace_session', JSON.stringify(sessionData));
            console.log('Session saved to localStorage');
        } catch (error) {
            console.error('Failed to save session:', error);
        }
    },

    /**
     * Restore session from localStorage
     * Requirements: Req 6
     */
    restoreSession() {
        try {
            const savedSession = localStorage.getItem('pptReplace_session');
            if (savedSession) {
                const sessionData = JSON.parse(savedSession);

                // Only restore if session ID matches or we have a valid session
                if (sessionData.id && sessionData.filename) {
                    this.session.moduleStatus = sessionData.moduleStatus || this.session.moduleStatus;
                    this.session.replacementHistory = sessionData.replacementHistory || [];
                    this.session.totalReplaced = sessionData.totalReplaced || 0;
                    this.session.uploadTime = sessionData.uploadTime;

                    // Update UI to reflect restored session
                    this.updateTabBadgesWithStatus();
                    this.renderReplacementHistoryPanel();

                    console.log('Session restored from localStorage');
                }
            }
        } catch (error) {
            console.error('Failed to restore session:', error);
        }
    },

    /**
     * Clear session and reset all states
     * Requirements: Req 6
     */
    clearSession(showConfirm = true) {
        if (showConfirm) {
            if (!confirm('确定要清除当前会话吗？所有替换历史将被清除。')) {
                return false;
            }
        }

        this.initializeSession();
        this.sessionId = null;
        this.pptFile = null;
        this.slideData = [];

        // Clear localStorage
        try {
            localStorage.removeItem('pptReplace_session');
        } catch (error) {
            console.error('Failed to clear session from localStorage:', error);
        }

        // Reset UI
        this.clearPPT();
        this.updateTabBadgesWithStatus();
        this.renderReplacementHistoryPanel();

        this.showInfo('会话已清除');
        return true;
    },

    /**
     * Initialize border configuration
     * Requirements: Req 11.8
     */
    initializeBorderConfig() {
        this.borderConfig = {
            enabled: true,
            width_pt: 1.0,
            color_rgb: [0, 0, 0]  // Black
        };

        // Restore from localStorage if available
        try {
            const saved = localStorage.getItem('pptReplace_borderConfig');
            if (saved) {
                const savedConfig = JSON.parse(saved);
                this.borderConfig = { ...this.borderConfig, ...savedConfig };
            }
        } catch (error) {
            console.error('Failed to restore border config:', error);
        }
    },

    /**
     * Bind border configuration events
     * Requirements: Req 11.8
     */
    bindBorderConfigEvents() {
        const enableToggle = document.getElementById('enableBorderToggle');
        const widthInput = document.getElementById('borderWidthInput');
        const widthDisplay = document.getElementById('borderWidthDisplay');
        const borderOptions = document.getElementById('borderOptions');
        const previewImage = document.querySelector('.preview-image');

        if (enableToggle) {
            // Set initial state
            enableToggle.checked = this.borderConfig.enabled;
            if (borderOptions) {
                borderOptions.style.display = this.borderConfig.enabled ? 'block' : 'none';
            }

            enableToggle.addEventListener('change', (e) => {
                this.borderConfig.enabled = e.target.checked;
                if (borderOptions) {
                    borderOptions.style.display = e.target.checked ? 'block' : 'none';
                }
                this.saveBorderConfig();
                console.log('Border enabled:', this.borderConfig.enabled);
            });
        }

        if (widthInput && widthDisplay && previewImage) {
            // Set initial value
            widthInput.value = this.borderConfig.width_pt;
            widthDisplay.textContent = `${this.borderConfig.width_pt} pt`;
            previewImage.style.borderWidth = `${this.borderConfig.width_pt}pt`;

            widthInput.addEventListener('input', (e) => {
                const width = parseFloat(e.target.value);
                this.borderConfig.width_pt = width;
                widthDisplay.textContent = `${width} pt`;

                // Update preview
                previewImage.style.borderWidth = `${width}pt`;

                this.saveBorderConfig();
                console.log('Border width:', width);
            });
        }
    },

    /**
     * Save border configuration to localStorage
     * Requirements: Req 11.8
     */
    saveBorderConfig() {
        try {
            localStorage.setItem('pptReplace_borderConfig', JSON.stringify(this.borderConfig));
        } catch (error) {
            console.error('Failed to save border config:', error);
        }
    },

    /**
     * Get current border configuration for API request
     * Requirements: Req 11.8
     * @returns {Object|null} Border configuration or null if disabled
     */
    getBorderConfig() {
        if (!this.borderConfig.enabled) {
            return null;
        }

        return {
            width_pt: this.borderConfig.width_pt,
            color_rgb: this.borderConfig.color_rgb
        };
    },

    /**
     * Update module status after replacement
     * Requirements: Req 2, 3
     * @param {string} module - Module name
     * @param {number} count - Number of images replaced
     * @param {Array} mappings - Mapping details
     */
    updateModuleStatus(module, count, mappings = []) {
        if (!this.session.moduleStatus[module]) {
            this.session.moduleStatus[module] = { replaced: false, count: 0, timestamp: null, mappings: [] };
        }

        this.session.moduleStatus[module] = {
            replaced: count > 0,
            count: count,
            timestamp: new Date().toISOString(),
            mappings: mappings
        };

        // Update total replaced count
        this.session.totalReplaced = Object.values(this.session.moduleStatus)
            .reduce((sum, status) => sum + (status.count || 0), 0);

        // Add to replacement history
        this.addReplacementRecord(module, count, mappings);

        // Save session
        this.saveSession();

        // Update UI
        this.updateTabBadgesWithStatus();
        this.renderReplacementHistoryPanel();
    },

    /**
     * Add a replacement record to history
     * Requirements: Req 2
     * @param {string} module - Module name
     * @param {number} count - Number of images replaced
     * @param {Array} mappings - Mapping details
     */
    addReplacementRecord(module, count, mappings = []) {
        const record = {
            id: `${module}_${Date.now()}`,
            module: module,
            timestamp: new Date().toISOString(),
            count: count,
            mappings: mappings,
            imageSource: this.imageSource || {}
        };

        // Remove existing record for same module (keep only latest)
        this.session.replacementHistory = this.session.replacementHistory.filter(r => r.module !== module);

        // Add new record
        this.session.replacementHistory.push(record);

        // Sort by timestamp
        this.session.replacementHistory.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    },

    /**
     * Get completed modules count
     * Requirements: Req 3
     * @returns {Object} { completed: number, total: number }
     */
    getModulesProgress() {
        const modules = Object.values(this.session.moduleStatus);
        const completed = modules.filter(m => m.replaced).length;
        return { completed, total: modules.length };
    },

    /**
     * Update tab badges with replacement status
     * Requirements: Req 3
     */
    updateTabBadgesWithStatus() {
        Object.keys(this.TAB_TO_IMAGE_TYPE).forEach(tabId => {
            const imageType = this.TAB_TO_IMAGE_TYPE[tabId];
            const moduleStatus = this.session.moduleStatus[imageType];
            const slideCount = this.slideData.filter(slide => {
                const slideImageType = slide.image_type || 'sharing_analysis';
                return slideImageType === imageType;
            }).length;

            const tabButton = document.querySelector(`#imageTypeTabs button[data-bs-target="#${tabId}"]`);
            if (!tabButton) return;

            // Remove existing badges
            const existingBadges = tabButton.querySelectorAll('.tab-count-badge, .tab-status-badge');
            existingBadges.forEach(b => b.remove());

            // Add status badge (checkmark or pending)
            if (moduleStatus && moduleStatus.replaced) {
                const statusBadge = document.createElement('span');
                statusBadge.className = 'badge bg-success ms-1 tab-status-badge';
                statusBadge.innerHTML = `<i class="bi bi-check-lg"></i> ${moduleStatus.count}`;
                statusBadge.title = `已替换 ${moduleStatus.count} 张图片 (${this.formatTimestamp(moduleStatus.timestamp)})`;
                tabButton.appendChild(statusBadge);
            } else if (slideCount > 0) {
                // Has slides but not replaced yet
                const countBadge = document.createElement('span');
                countBadge.className = 'badge bg-warning text-dark ms-1 tab-count-badge';
                countBadge.textContent = slideCount;
                countBadge.title = `${slideCount} 张幻灯片待替换`;
                tabButton.appendChild(countBadge);
            }

            // Update tab state
            if (this.tabStates[tabId]) {
                this.tabStates[tabId].slideCount = slideCount;
            }
        });
    },

    /**
     * Render replacement history panel
     * Requirements: Req 2, 3
     */
    renderReplacementHistoryPanel() {
        const container = document.getElementById('replacementHistoryPanel');
        if (!container) return;

        const progress = this.getModulesProgress();
        const history = this.session.replacementHistory;

        let html = `
            <div class="card-header d-flex justify-content-between align-items-center py-2">
                <h6 class="mb-0"><i class="bi bi-clock-history"></i> 替换历史</h6>
                <button class="btn btn-sm btn-outline-secondary" onclick="PPTReplace.clearSession()" title="清除会话">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
            <div class="card-body py-2">
        `;

        // Progress indicator
        html += `
            <div class="progress-section mb-2">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <small class="text-muted">进度</small>
                    <span class="badge ${progress.completed === progress.total ? 'bg-success' : 'bg-primary'}">
                        ${progress.completed}/${progress.total} 模块
                    </span>
                </div>
                <div class="progress" style="height: 6px;">
                    <div class="progress-bar ${progress.completed === progress.total ? 'bg-success' : ''}" 
                         style="width: ${(progress.completed / progress.total) * 100}%"></div>
                </div>
            </div>
        `;

        // Module status list
        html += '<div class="module-status-list">';
        Object.entries(this.session.moduleStatus).forEach(([module, status]) => {
            const displayName = this.IMAGE_TYPE_NAMES[module] || module;
            const statusIcon = status.replaced
                ? '<i class="bi bi-check-circle-fill text-success"></i>'
                : '<i class="bi bi-circle text-muted"></i>';
            const statusText = status.replaced
                ? `${status.count} 张 · ${this.formatTimestamp(status.timestamp)}`
                : '未替换';

            html += `
                <div class="d-flex align-items-center py-1 border-bottom">
                    <span class="me-2">${statusIcon}</span>
                    <span class="flex-grow-1 small">${displayName}</span>
                    <small class="text-muted">${statusText}</small>
                </div>
            `;
        });
        html += '</div>';

        // Total count
        if (this.session.totalReplaced > 0) {
            html += `
                <div class="mt-2 pt-2 border-top">
                    <div class="d-flex justify-content-between">
                        <span class="fw-bold">总计</span>
                        <span class="badge bg-primary">${this.session.totalReplaced} 张图片</span>
                    </div>
                </div>
            `;
        }

        html += '</div>';
        container.innerHTML = html;
        container.style.display = 'block';
    },

    /**
     * Format timestamp for display
     * @param {string} timestamp - ISO timestamp
     * @returns {string} Formatted time
     */
    formatTimestamp(timestamp) {
        if (!timestamp) return '';
        try {
            const date = new Date(timestamp);
            return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        } catch {
            return '';
        }
    },

    /**
     * Initialize per-tab image source storage
     */
    initializeTabImageSources() {
        // Load saved image sources from session storage
        try {
            const saved = sessionStorage.getItem('pptReplace_tabImageSources');
            if (saved) {
                this.tabImageSources = JSON.parse(saved);
            }
        } catch (e) {
            console.error('Failed to load tab image sources:', e);
        }
    },

    /**
     * Initialize state storage for each tab
     * Requirements: 9.7 - Tab state management
     */
    initializeTabStates() {
        Object.keys(this.TAB_TO_IMAGE_TYPE).forEach(tabId => {
            this.tabStates[tabId] = {
                slideCount: 0,
                slides: [],
                lastUpdated: null,
                isActive: tabId === 'sharing-analysis'
            };
        });
    },

    /**
     * Bind tab switching events with state management
     * Requirements: 9.2, 9.7
     */
    bindTabEvents() {
        const tabButtons = document.querySelectorAll('#imageTypeTabs button[data-bs-toggle="tab"]');

        tabButtons.forEach(button => {
            // Before tab is shown - save current tab state
            button.addEventListener('hide.bs.tab', (event) => {
                const currentTabId = event.target.getAttribute('data-bs-target').replace('#', '');
                this.saveTabState(currentTabId);
            });

            // After tab is shown - restore new tab state and update content
            button.addEventListener('shown.bs.tab', (event) => {
                const newTabId = event.target.getAttribute('data-bs-target').replace('#', '');
                const previousTabId = event.relatedTarget ?
                    event.relatedTarget.getAttribute('data-bs-target').replace('#', '') : null;

                this.onTabSwitch(newTabId, previousTabId);
            });
        });

        // Initialize with the active tab
        const activeTab = document.querySelector('#imageTypeTabs button.active');
        if (activeTab) {
            const tabId = activeTab.getAttribute('data-bs-target').replace('#', '');
            this.currentTab = this.TAB_TO_IMAGE_TYPE[tabId] || 'sharing_analysis';
        }
    },

    /**
     * Handle tab switch event
     * Requirements: 9.2, 9.7
     * @param {string} newTabId - The ID of the newly active tab
     * @param {string} previousTabId - The ID of the previously active tab
     */
    onTabSwitch(newTabId, previousTabId) {
        // Save current tab's image source before switching
        if (previousTabId) {
            this.saveCurrentTabImageSource(previousTabId);
        }

        // Update current tab
        this.currentTab = this.TAB_TO_IMAGE_TYPE[newTabId] || 'sharing_analysis';

        // Update tab states
        if (previousTabId && this.tabStates[previousTabId]) {
            this.tabStates[previousTabId].isActive = false;
        }
        if (this.tabStates[newTabId]) {
            this.tabStates[newTabId].isActive = true;
        }

        // Save active tab to session storage
        this.saveActiveTab(newTabId);

        // Re-render slide analysis if we have data
        if (this.slideData.length > 0) {
            this.filterSlidesByTab();
        }

        // Update tab badges
        this.updateTabBadges();

        // Update folder hint for current tab
        this.updateFolderHint(newTabId);

        // Restore image source for new tab
        this.restoreTabImageSource(newTabId);

        // Dispatch custom event for other components
        this.dispatchTabChangeEvent(newTabId, previousTabId);

        console.log(`Tab switched from ${previousTabId} to ${newTabId}`);
    },

    /**
     * Save current tab's image source
     * @param {string} tabId - Tab ID to save
     */
    saveCurrentTabImageSource(tabId) {
        const imageDirInput = document.getElementById('imageDirInput');
        const analysisSelect = document.getElementById('analysisSelect');

        const dirValue = imageDirInput ? imageDirInput.value.trim() : '';
        const analysisValue = analysisSelect ? analysisSelect.value : '';

        // Determine source type
        let sourceType = null;
        let sourceValue = null;

        if (dirValue) {
            sourceType = 'folder';
            sourceValue = dirValue;
        } else if (analysisValue) {
            sourceType = 'analysis';
            sourceValue = analysisValue;
        }

        if (this.tabImageSources[tabId]) {
            this.tabImageSources[tabId].type = sourceType;
            this.tabImageSources[tabId].value = sourceValue;
        }

        // Save to session storage
        try {
            sessionStorage.setItem('pptReplace_tabImageSources', JSON.stringify(this.tabImageSources));
        } catch (e) {
            console.error('Failed to save tab image sources:', e);
        }
    },

    /**
     * Restore image source for a tab
     * @param {string} tabId - Tab ID to restore
     */
    restoreTabImageSource(tabId) {
        const source = this.tabImageSources[tabId];
        const imageDirInput = document.getElementById('imageDirInput');
        const analysisSelect = document.getElementById('analysisSelect');

        // Clear current values first
        if (imageDirInput) imageDirInput.value = '';
        if (analysisSelect) analysisSelect.value = '';

        if (source && source.type && source.value) {
            if (source.type === 'folder' && imageDirInput) {
                imageDirInput.value = source.value;
            } else if (source.type === 'analysis' && analysisSelect) {
                analysisSelect.value = source.value;
            }
        }

        // Update scan button state
        this.updateScanButton();

        // If this tab has scanned images, show them
        if (source && source.scannedImages) {
            this.showTabMappingPreview(tabId);
        }
    },

    /**
     * Save current tab state
     * Requirements: 9.7
     * @param {string} tabId - The tab ID to save state for
     */
    saveTabState(tabId) {
        if (!this.tabStates[tabId]) return;

        const imageType = this.TAB_TO_IMAGE_TYPE[tabId];
        const filteredSlides = this.slideData.filter(slide => {
            const slideImageType = slide.image_type || 'sharing_analysis';
            return slideImageType === imageType;
        });

        this.tabStates[tabId] = {
            ...this.tabStates[tabId],
            slideCount: filteredSlides.length,
            slides: filteredSlides,
            lastUpdated: new Date().toISOString()
        };

        // Save to session storage
        try {
            sessionStorage.setItem('pptReplace_tabStates', JSON.stringify(this.tabStates));
        } catch (error) {
            console.error('Failed to save tab state:', error);
        }
    },

    /**
     * Restore tab state from session storage
     * Requirements: 9.7
     */
    restoreTabState() {
        try {
            const savedStates = sessionStorage.getItem('pptReplace_tabStates');
            if (savedStates) {
                this.tabStates = JSON.parse(savedStates);
            }

            // Restore active tab
            const activeTabId = sessionStorage.getItem('pptReplace_activeTab');
            if (activeTabId) {
                this.switchToTab(activeTabId);
            }
        } catch (error) {
            console.error('Failed to restore tab state:', error);
        }
    },

    /**
     * Save active tab to session storage
     * Requirements: 9.7
     * @param {string} tabId - The active tab ID
     */
    saveActiveTab(tabId) {
        try {
            sessionStorage.setItem('pptReplace_activeTab', tabId);
        } catch (error) {
            console.error('Failed to save active tab:', error);
        }
    },

    /**
     * Switch to a specific tab programmatically
     * Requirements: 9.2
     * @param {string} tabId - The tab ID to switch to
     */
    switchToTab(tabId) {
        const tabButton = document.querySelector(`#imageTypeTabs button[data-bs-target="#${tabId}"]`);
        if (tabButton && typeof bootstrap !== 'undefined') {
            const tab = new bootstrap.Tab(tabButton);
            tab.show();
        }
    },

    /**
     * Update tab badges with slide counts
     * Requirements: 9.2
     */
    updateTabBadges() {
        // Use the enhanced version that includes replacement status
        this.updateTabBadgesWithStatus();
    },

    /**
     * Dispatch custom tab change event
     * Requirements: 9.7
     * @param {string} newTabId - The new tab ID
     * @param {string} previousTabId - The previous tab ID
     */
    dispatchTabChangeEvent(newTabId, previousTabId) {
        const event = new CustomEvent('pptTabChange', {
            detail: {
                newTab: newTabId,
                previousTab: previousTabId,
                imageType: this.TAB_TO_IMAGE_TYPE[newTabId],
                slideCount: this.tabStates[newTabId]?.slideCount || 0
            }
        });
        document.dispatchEvent(event);
    },

    /**
     * Get current tab configuration
     * Requirements: 9.2
     * @returns {Object} Current tab configuration
     */
    getCurrentTabConfig() {
        const tabId = this.IMAGE_TYPE_TO_TAB[this.currentTab] || 'sharing-analysis';
        return this.TAB_CONFIG[tabId] || this.TAB_CONFIG['sharing-analysis'];
    },

    /**
     * Get tab state by tab ID
     * Requirements: 9.7
     * @param {string} tabId - The tab ID
     * @returns {Object} Tab state
     */
    getTabState(tabId) {
        return this.tabStates[tabId] || null;
    },

    /**
     * Clear all tab states
     * Requirements: 9.7
     */
    clearTabStates() {
        this.initializeTabStates();
        try {
            sessionStorage.removeItem('pptReplace_tabStates');
            sessionStorage.removeItem('pptReplace_activeTab');
        } catch (error) {
            console.error('Failed to clear tab states:', error);
        }
    },

    /**
     * Filter and display slides based on current tab
     * Requirements: 9.2, 9.7
     */
    filterSlidesByTab() {
        const tabConfig = this.getCurrentTabConfig();
        const imageType = this.currentTab;

        // Filter slides for current tab
        const filteredSlides = this.slideData.filter(slide => {
            const slideImageType = slide.image_type || 'sharing_analysis';
            return slideImageType === imageType;
        });

        const list = document.getElementById('slideList');
        const countBadge = document.getElementById('slideCount');

        if (!list || !countBadge) return;

        // Update count badge
        const countText = filteredSlides.length === 0
            ? `未找到 ${tabConfig.title} 类型的幻灯片`
            : `${filteredSlides.length} 张 ${tabConfig.title} 幻灯片`;
        countBadge.textContent = countText;

        // Update tab state
        const tabId = this.IMAGE_TYPE_TO_TAB[imageType];
        if (this.tabStates[tabId]) {
            this.tabStates[tabId].slides = filteredSlides;
            this.tabStates[tabId].slideCount = filteredSlides.length;
        }

        // Render slides
        if (filteredSlides.length === 0) {
            list.innerHTML = this.renderEmptyState(tabConfig);
        } else {
            this.renderFilteredSlides(filteredSlides);
        }

        // Update tab badges
        this.updateTabBadges();
    },

    /**
     * Render empty state for a tab
     * Requirements: 9.2
     * @param {Object} tabConfig - Tab configuration
     * @returns {string} HTML string for empty state
     */
    renderEmptyState(tabConfig) {
        return `
            <div class="text-center py-4">
                <i class="bi ${tabConfig.icon} fs-1 text-muted"></i>
                <p class="text-muted mt-3">未找到 ${tabConfig.title} 类型的幻灯片</p>
                <p class="text-muted small">
                    请确保PPT模板中包含标题匹配以下关键词的页面：
                </p>
                <div class="keywords-list justify-content-center">
                    ${tabConfig.keywords.map(kw =>
            `<span class="badge ${tabConfig.badgeClass} keyword-badge m-1">${kw}</span>`
        ).join('')}
                </div>
            </div>
        `;
    },

    /**
     * Render filtered slides for the current tab
     * Requirements: 9.2
     * @param {Array} slides - Array of slide objects to render
     */
    renderFilteredSlides(slides) {
        const list = document.getElementById('slideList');
        if (!list) return;

        const tabConfig = this.getCurrentTabConfig();
        let html = '';

        slides.forEach((slide, idx) => {
            const imageType = slide.image_type || 'sharing_analysis';
            const imageTypeDisplay = this.IMAGE_TYPE_NAMES[imageType] || imageType;

            if (imageType === 'sharing_analysis') {
                // Sharing Analysis slide
                html += this.renderSharingAnalysisSlide(slide, imageTypeDisplay);
            } else {
                // Sample-based slides (Network Plots, Isotype Upset, Tree Maps)
                html += this.renderSampleBasedSlide(slide, imageTypeDisplay, tabConfig);
            }
        });

        list.innerHTML = html || this.renderEmptyState(tabConfig);
    },

    /**
     * Remove a slide from the analysis
     * @param {number} slideIndex - Index of slide to remove
     */
    removeSlide(slideIndex) {
        // Remove from slideData
        this.slideData = this.slideData.filter(s => s.slide_index !== slideIndex);

        // Re-render the analysis
        this.renderSlideAnalysis({ image_slides: this.slideData, heatmap_slides: this.slideData });

        // Update mapping preview if shown
        if (document.getElementById('mappingCard').style.display !== 'none') {
            this.showMappingPreview();
        }

        this.showInfo(`已移除幻灯片 ${slideIndex + 1}`);
    },

    /**
     * Render a Sharing Analysis slide card
     * Requirements: 9.2
     * @param {Object} slide - Slide data
     * @param {string} imageTypeDisplay - Display name for image type
     * @returns {string} HTML string
     */
    renderSharingAnalysisSlide(slide, imageTypeDisplay) {
        const chainColor = this.getChainColor(slide.chain_type);
        const slideTypeDisplay = slide.slide_type_display || (
            slide.metric_type === 'expression_r2' ? 'Expression/R² 类型' : 'Morisita/Sorensen 类型'
        );
        const slideNum = slide.slide_number_for_chain || (slide.metric_type === 'expression_r2' ? 1 : 2);

        return `
            <div class="slide-card mb-3" data-slide-index="${slide.slide_index}" data-image-type="sharing_analysis">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div>
                        <span class="badge bg-info image-type-badge">${imageTypeDisplay}</span>
                        <span class="badge ${chainColor} chain-badge ms-1">${slide.chain_type}</span>
                        <span class="ms-2 text-muted">幻灯片 ${slide.slide_index + 1}</span>
                        <span class="ms-2 badge bg-light text-dark">${slideTypeDisplay}</span>
                        <span class="ms-1 badge bg-outline-secondary">(${slideNum}/2)</span>
                    </div>
                    <div>
                        <span class="badge bg-secondary">${slide.image_count} 张图片</span>
                        <button type="button" class="btn btn-sm btn-outline-danger ms-2" onclick="PPTReplace.removeSlide(${slide.slide_index})" title="移除此页">
                            <i class="bi bi-x-lg"></i>
                        </button>
                    </div>
                </div>
                <div class="image-preview-row">
                    ${this.renderImagePreviews(slide)}
                </div>
            </div>
        `;
    },

    /**
     * Render a sample-based slide card (Network Plots, Isotype Upset, Tree Maps)
     * Requirements: 9.2
     * @param {Object} slide - Slide data
     * @param {string} imageTypeDisplay - Display name for image type
     * @param {Object} tabConfig - Tab configuration
     * @returns {string} HTML string
     */
    renderSampleBasedSlide(slide, imageTypeDisplay, tabConfig) {
        const sampleCount = slide.sample_count || (slide.sample_names ? slide.sample_names.length : 0);
        const sampleNames = slide.sample_names || [];
        const imageType = slide.image_type || 'sharing_analysis';
        const imagePositions = slide.image_positions || [];
        const slideIdx = slide.slide_index;

        // Build sample name display for each image
        let imagesHtml = '<div class="row g-2">';
        imagePositions.forEach((img, idx) => {
            const sampleName = sampleNames[idx] || img.sample_name || `样本 ${idx + 1}`;
            const hasImage = img.data_url && img.data_url.length > 0;
            const imageInfo = `幻灯片 ${slide.slide_index + 1} - ${sampleName}`;

            imagesHtml += `
                <div class="col-4 col-md-3 col-lg-2">
                    <div class="image-preview-card text-center">
                        <div class="image-preview-container" style="cursor: ${hasImage ? 'pointer' : 'default'};"
                             ${hasImage ? `data-slide-idx="${slideIdx}" data-img-idx="${idx}" data-img-info="${imageInfo}" onclick="PPTReplace.showSlideImagePreview(this)"` : ''}>
                            ${hasImage
                    ? `<img src="${img.data_url}" class="heatmap-thumbnail" alt="${sampleName}" title="点击放大: ${sampleName}">`
                    : `<div class="no-image-placeholder"><i class="bi bi-image text-muted"></i></div>`
                }
                            ${hasImage ? '<div class="image-zoom-hint"><i class="bi bi-zoom-in"></i></div>' : ''}
                        </div>
                        <div class="sample-label mt-1">
                            <span class="badge bg-warning text-dark text-truncate" style="max-width: 100%;" title="${sampleName}">${sampleName}</span>
                        </div>
                        <div class="position-info text-muted small">
                            ${img.position || ''}
                        </div>
                    </div>
                </div>
            `;
        });
        imagesHtml += '</div>';

        return `
            <div class="slide-card mb-3" data-slide-index="${slide.slide_index}" data-image-type="${imageType}">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div>
                        <span class="badge ${tabConfig.badgeClass} image-type-badge">${imageTypeDisplay}</span>
                        <span class="ms-2 text-muted">幻灯片 ${slide.slide_index + 1}</span>
                    </div>
                    <div>
                        <span class="badge bg-secondary">${sampleCount > 0 ? sampleCount : imagePositions.length} 个样本</span>
                        <span class="badge bg-secondary ms-1">${slide.image_count} 张图片</span>
                        <button type="button" class="btn btn-sm btn-outline-danger ms-2" onclick="PPTReplace.removeSlide(${slide.slide_index})" title="移除此页">
                            <i class="bi bi-x-lg"></i>
                        </button>
                    </div>
                </div>
                ${sampleNames.length > 0 ? `
                    <div class="sample-list mb-2">
                        <small><i class="bi bi-people"></i> 样本: ${sampleNames.slice(0, 10).join(', ')}${sampleNames.length > 10 ? ` 等${sampleNames.length}个` : ''}</small>
                    </div>
                ` : ''}
                <div class="image-preview-row">
                    ${imagesHtml}
                </div>
            </div>
        `;
    },

    bindEvents() {
        const uploadZone = document.getElementById('pptUploadZone');
        const fileInput = document.getElementById('pptFileInput');
        const imageDirInput = document.getElementById('imageDirInput');
        const analysisSelect = document.getElementById('analysisSelect');
        const scanBtn = document.getElementById('scanImagesBtn');
        const replaceBtn = document.getElementById('replaceBtn');
        const browseBtn = document.getElementById('browseImageBtn');

        // Upload zone click
        if (uploadZone) {
            uploadZone.addEventListener('click', () => fileInput.click());
            uploadZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadZone.classList.add('drag-over');
            });
            uploadZone.addEventListener('dragleave', () => {
                uploadZone.classList.remove('drag-over');
            });
            uploadZone.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadZone.classList.remove('drag-over');
                if (e.dataTransfer.files.length > 0) {
                    this.handlePPTFile(e.dataTransfer.files[0]);
                }
            });
        }

        // File input change
        if (fileInput) {
            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.handlePPTFile(e.target.files[0]);
                }
            });
        }

        // Image directory input
        if (imageDirInput) {
            imageDirInput.addEventListener('input', () => {
                this.updateScanButton();
            });
        }

        // Browse button - show folder input hint
        if (browseBtn) {
            browseBtn.addEventListener('click', () => {
                this.showFolderInputHint();
            });
        }

        // Analysis select
        if (analysisSelect) {
            analysisSelect.addEventListener('change', () => {
                this.updateScanButton();
                // Auto-fill image directory if analysis has results_path
                const selectedOption = analysisSelect.options[analysisSelect.selectedIndex];
                if (selectedOption && selectedOption.dataset.resultsPath) {
                    imageDirInput.value = selectedOption.dataset.resultsPath;
                }
            });
        }

        // Scan button
        if (scanBtn) {
            scanBtn.addEventListener('click', () => this.scanImages());
        }

        // Replace button
        if (replaceBtn) {
            replaceBtn.addEventListener('click', () => this.replaceImages());
        }
    },

    showFolderInputHint() {
        // Try to use the modern File System Access API if available
        if ('showDirectoryPicker' in window) {
            this.openFolderPicker();
        } else {
            // Fallback: show input hint for manual path entry
            const imageDirInput = document.getElementById('imageDirInput');
            if (imageDirInput) {
                imageDirInput.focus();
                imageDirInput.placeholder = '例如: E:\\analysis_results 或 /home/user/results';

                // Show a more helpful message
                const helpText = document.createElement('div');
                helpText.className = 'form-text text-info mt-1';
                helpText.id = 'folderHelpText';
                helpText.innerHTML = `
                    <i class="bi bi-info-circle"></i> 
                    请手动输入包含图片文件的文件夹路径。图片文件应按类型组织，例如：
                    <br><code>E:\\analysis_results\\</code> 目录下包含 <code>IGH/</code>, <code>TRA/</code>（热图）, <code>network_plots/</code>（网络图）等子目录
                `;

                // Remove existing help text if any
                const existingHelp = document.getElementById('folderHelpText');
                if (existingHelp) existingHelp.remove();

                // Add help text after input
                imageDirInput.parentNode.appendChild(helpText);
            }
        }
    },

    async openFolderPicker() {
        try {
            // Use the File System Access API to pick a directory
            const dirHandle = await window.showDirectoryPicker({
                mode: 'read'
            });

            // Get the directory name/path
            const dirName = dirHandle.name;
            const imageDirInput = document.getElementById('imageDirInput');

            // Store the directory handle for later use
            this.selectedDirHandle = dirHandle;

            // Update the input field with the directory name
            // Note: Browser security prevents getting the full path
            imageDirInput.value = dirName;

            // Show warning that user needs to enter full path
            this.showWarning(`已选择文件夹: ${dirName}\n\n⚠️ 由于浏览器安全限制，无法获取完整路径。\n请在输入框中手动输入完整路径，例如:\nE:\\Desktop\\${dirName}`);

            // Scan the directory structure (for preview purposes)
            await this.scanDirectoryStructure(dirHandle);

            this.updateScanButton();
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('Error opening folder picker:', error);
                // Fallback to manual input
                const imageDirInput = document.getElementById('imageDirInput');
                if (imageDirInput) {
                    imageDirInput.focus();
                    this.showInfo('请手动输入文件夹路径');
                }
            }
        }
    },

    async scanDirectoryStructure(dirHandle) {
        // Scan the directory to find chain subdirectories and image type directories
        const chains = ['IGH', 'IGK', 'IGL', 'TRA', 'TRB', 'TRD', 'TRG'];
        const imageTypeDirs = ['network_plots', 'isotype_upset', 'tree_maps'];
        const foundChains = [];
        const foundImageTypes = [];

        try {
            for await (const entry of dirHandle.values()) {
                if (entry.kind === 'directory') {
                    const upperName = entry.name.toUpperCase();
                    if (chains.includes(upperName)) {
                        foundChains.push(entry.name);
                    }
                    if (imageTypeDirs.includes(entry.name.toLowerCase())) {
                        foundImageTypes.push(entry.name);
                    }
                }
            }

            let message = '';
            if (foundChains.length > 0) {
                message += `找到 ${foundChains.length} 个链类型目录: ${foundChains.join(', ')}`;
            }
            if (foundImageTypes.length > 0) {
                if (message) message += '; ';
                message += `找到图片类型目录: ${foundImageTypes.join(', ')}`;
            }
            if (!message) {
                message = '未找到预期的子目录结构';
            }

            this.showInfo(message);
        } catch (error) {
            console.error('Error scanning directory:', error);
        }
    },

    async loadAnalysisList() {
        try {
            // Load from analysis list endpoint
            const response = await fetch('/api/analysis/list?limit=20&status=completed');

            if (!response.ok) return;

            const data = await response.json();
            const select = document.getElementById('analysisSelect');
            if (!select) return;

            // Handle both response formats
            const analyses = data.analyses || data.items || [];

            analyses.forEach(analysis => {
                if (analysis.status === 'completed' || !analysis.status) {
                    const option = document.createElement('option');
                    option.value = analysis.id;
                    option.textContent = `${analysis.name || analysis.file_name || analysis.id} (${this.formatDate(analysis.created_at)})`;
                    if (analysis.results_path) {
                        option.dataset.resultsPath = analysis.results_path;
                    }
                    select.appendChild(option);
                }
            });
        } catch (error) {
            console.error('Error loading analysis list:', error);
        }
    },

    formatDate(dateStr) {
        if (!dateStr) return '未知日期';
        try {
            const date = new Date(dateStr);
            return date.toLocaleDateString('zh-CN') + ' ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
        } catch {
            return dateStr;
        }
    },

    async handlePPTFile(file) {
        if (!file.name.toLowerCase().endsWith('.pptx') && !file.name.toLowerCase().endsWith('.ppt')) {
            this.showError('请上传 .pptx 或 .ppt 格式的文件');
            return;
        }

        this.pptFile = file;

        // Update UI
        document.getElementById('pptUploadZone').classList.add('has-file');
        document.getElementById('pptFileInfo').style.display = 'block';
        document.getElementById('pptFileName').textContent = file.name;

        // Upload and analyze
        await this.analyzePPT(file);
    },

    async analyzePPT(file) {
        const formData = new FormData();
        formData.append('file', file);

        // Show loading state
        this.showAnalyzeLoading(true);

        try {
            const response = await fetch('/api/ppt/analyze', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            // Hide loading state
            this.showAnalyzeLoading(false);

            if (!data.success) {
                this.showError(data.error || '分析PPT失败');
                return;
            }

            this.sessionId = data.session_id;
            this.slideData = data.image_slides || data.heatmap_slides || [];

            // Initialize session for multi-module support
            this.session.uploadTime = new Date().toISOString();
            this.initializeSession();  // Reset module status for new PPT
            this.session.uploadTime = new Date().toISOString();
            this.saveSession();

            // Debug logging
            console.log('analyzePPT - slideData count:', this.slideData.length);
            if (this.slideData.length > 0 && this.slideData[0].image_positions?.length > 0) {
                console.log('First slide first image has data_url:', !!this.slideData[0].image_positions[0].data_url);
            }

            // Update step indicator
            this.setStep(2);

            // Show analysis results
            this.renderSlideAnalysis(data);

            // Show image source card
            document.getElementById('imageSourceCard').style.display = 'block';
            document.getElementById('borderConfigCard').style.display = 'block';  // Show border config
            document.getElementById('replaceCard').style.display = 'block';

            // Show replacement history panel
            const historyPanel = document.getElementById('replacementHistoryPanel');
            if (historyPanel) {
                historyPanel.style.display = 'block';
            }
            this.renderReplacementHistoryPanel();

            // Update tab badges with status
            this.updateTabBadgesWithStatus();

        } catch (error) {
            console.error('Error analyzing PPT:', error);
            this.showAnalyzeLoading(false);
            this.showError('分析PPT时发生错误');
        }
    },

    /**
     * Show/hide loading state during PPT analysis
     * @param {boolean} show - Whether to show loading
     */
    showAnalyzeLoading(show) {
        const uploadZone = document.getElementById('pptUploadZone');
        const pptFileInfo = document.getElementById('pptFileInfo');

        if (show) {
            // Add loading indicator to upload zone
            if (uploadZone) {
                uploadZone.innerHTML = `
                    <div class="text-center">
                        <div class="spinner-border text-primary mb-2" role="status">
                            <span class="visually-hidden">分析中...</span>
                        </div>
                        <p class="mb-0">正在分析PPT结构...</p>
                        <small class="text-muted">识别图片位置和类型</small>
                    </div>
                `;
            }
        } else {
            // Restore upload zone
            if (uploadZone) {
                uploadZone.innerHTML = `
                    <i class="bi bi-file-earmark-ppt fs-1 text-danger"></i>
                    <p class="mt-2 mb-1">点击或拖放PPT文件到此处</p>
                    <small class="text-muted">支持 .pptx 格式</small>
                `;
            }
        }
    },

    /**
     * Render slide analysis results with tab integration
     * Requirements: 9.2, 9.7
     * @param {Object} data - Analysis data from API
     */
    renderSlideAnalysis(data) {
        const card = document.getElementById('slideAnalysisCard');
        const list = document.getElementById('slideList');
        const countBadge = document.getElementById('slideCount');

        if (!card || !list || !countBadge) return;

        card.style.display = 'block';
        const slides = data.image_slides || data.heatmap_slides || [];

        // Store all slides for filtering
        this.slideData = slides;

        // Update tab states with slide counts
        this.updateAllTabStates();

        // Show total count
        countBadge.textContent = `${slides.length} 张图片幻灯片`;

        // Update tab badges
        this.updateTabBadges();

        // Filter by current tab
        this.filterSlidesByTab();

        // Auto-switch to tab with most slides if current tab is empty
        this.autoSwitchToPopulatedTab();
    },

    /**
     * Update all tab states with current slide data
     * Requirements: 9.7
     */
    updateAllTabStates() {
        Object.keys(this.TAB_TO_IMAGE_TYPE).forEach(tabId => {
            const imageType = this.TAB_TO_IMAGE_TYPE[tabId];
            const filteredSlides = this.slideData.filter(slide => {
                const slideImageType = slide.image_type || 'sharing_analysis';
                return slideImageType === imageType;
            });

            // Store only metadata, not full slide data with base64 images
            const slideMetadata = filteredSlides.map(slide => ({
                slide_index: slide.slide_index,
                image_type: slide.image_type,
                chain_type: slide.chain_type,
                image_count: slide.image_count
            }));

            this.tabStates[tabId] = {
                ...this.tabStates[tabId],
                slideCount: filteredSlides.length,
                slides: slideMetadata,  // Store lightweight metadata only
                lastUpdated: new Date().toISOString()
            };
        });

        // Save to session storage (now much smaller without base64 data)
        try {
            sessionStorage.setItem('pptReplace_tabStates', JSON.stringify(this.tabStates));
        } catch (error) {
            console.error('Failed to save tab states:', error);
        }
    },

    /**
     * Auto-switch to a tab that has slides if current tab is empty
     * Requirements: 9.2
     */
    autoSwitchToPopulatedTab() {
        const currentTabId = this.IMAGE_TYPE_TO_TAB[this.currentTab];
        const currentTabState = this.tabStates[currentTabId];

        // If current tab has slides, stay on it
        if (currentTabState && currentTabState.slideCount > 0) {
            return;
        }

        // Find a tab with slides
        for (const [tabId, state] of Object.entries(this.tabStates)) {
            if (state.slideCount > 0) {
                this.switchToTab(tabId);
                this.showInfo(`已自动切换到 ${this.TAB_CONFIG[tabId]?.title || tabId} 标签页`);
                break;
            }
        }
    },

    renderImagePreviews(slide) {
        if (!slide.image_positions || slide.image_positions.length === 0) {
            return '<p class="text-muted small">无图片</p>';
        }

        let html = '<div class="row g-2">';
        slide.image_positions.forEach((img, idx) => {
            const metricDisplay = img.metric_display || this.formatMetricName(img.metric || 'unknown');
            const hasImage = img.data_url && img.data_url.length > 0;
            const imageInfo = `幻灯片 ${slide.slide_index + 1} - ${metricDisplay}`;
            // Use data attribute to store image info for click handler (fixes issue #1: image zoom not working)
            const slideIdx = slide.slide_index;
            const imgIdx = idx;

            html += `
                <div class="col-4">
                    <div class="image-preview-card text-center">
                        <div class="image-preview-container" style="cursor: ${hasImage ? 'pointer' : 'default'};"
                             ${hasImage ? `data-slide-idx="${slideIdx}" data-img-idx="${imgIdx}" data-img-info="${imageInfo}" onclick="PPTReplace.showSlideImagePreview(this)"` : ''}>
                            ${hasImage
                    ? `<img src="${img.data_url}" class="heatmap-thumbnail" alt="${metricDisplay}" title="点击放大: ${metricDisplay}">`
                    : `<div class="no-image-placeholder"><i class="bi bi-image text-muted"></i></div>`
                }
                            ${hasImage ? '<div class="image-zoom-hint"><i class="bi bi-zoom-in"></i></div>' : ''}
                        </div>
                        <div class="metric-label mt-1">
                            <span class="badge bg-primary">${metricDisplay}</span>
                        </div>
                        <div class="position-info text-muted small">
                            ${img.position || ''} | ${img.size || ''}
                        </div>
                    </div>
                </div>
            `;
        });
        html += '</div>';
        return html;
    },

    getChainColor(chain) {
        const colors = {
            'IGH': 'bg-primary',
            'IGK': 'bg-info',
            'IGL': 'bg-success',
            'TRA': 'bg-warning',
            'TRB': 'bg-danger',
            'TRD': 'bg-secondary',
            'TRG': 'bg-dark'
        };
        return colors[chain] || 'bg-secondary';
    },

    /**
     * Update folder hint based on current tab
     * @param {string} tabId - Current tab ID
     */
    updateFolderHint(tabId) {
        const config = this.TAB_CONFIG[tabId];
        if (!config) return;

        const moduleSpan = document.getElementById('folderHintModule');
        const pathSpan = document.getElementById('folderHintPath');
        const tabBadge = document.getElementById('currentTabBadge');

        if (moduleSpan) moduleSpan.textContent = config.title;
        if (pathSpan) pathSpan.textContent = config.folderHint || '';
        if (tabBadge) {
            tabBadge.textContent = config.title;
            tabBadge.className = `badge ${config.badgeClass}`;
        }
    },

    updateScanButton() {
        const imageDir = document.getElementById('imageDirInput');
        const analysisId = document.getElementById('analysisSelect').value;
        const scanBtn = document.getElementById('scanImagesBtn');

        let canScan = false;
        
        if (this.comparisonMode.enabled) {
            // In comparison mode, need at least 2 sources with paths
            const validSources = this.comparisonMode.sources.filter(s => s.path && s.path.trim());
            canScan = validSources.length >= 2;
        } else {
            // In replace mode, need either directory or analysis ID
            const dirValue = imageDir ? imageDir.value.trim() : '';
            canScan = !!(dirValue || analysisId);
        }
        
        if (scanBtn) {
            scanBtn.disabled = !canScan;
        }
    },

    async scanImages() {
        // Check if comparison mode is enabled
        if (this.comparisonMode.enabled) {
            return this.scanComparisonImages();
        }
        
        const imageDirInput = document.getElementById('imageDirInput');
        const imageDir = imageDirInput ? imageDirInput.value.trim() : '';
        const analysisId = document.getElementById('analysisSelect').value;

        if (!imageDir && !analysisId) {
            this.showError('请输入图片目录或选择分析结果');
            return;
        }

        // Show loading state
        this.showScanLoading(true);

        try {
            // Get current tab to determine which module-specific directory to use
            const currentTab = this.currentTab || 'sharing_analysis';

            const requestData = {
                session_id: this.sessionId,
                image_type: currentTab  // Tell backend which type to scan
            };

            // Set module-specific directory based on current tab
            if (imageDir) {
                // Map tab ID to directory parameter name
                const dirParamMap = {
                    'sharing_analysis': 'sharing_analysis_dir',
                    'network_plots': 'network_plots_dir',
                    'isotype_upset': 'isotype_upset_dir',
                    'tree_maps': 'tree_maps_dir'
                };

                const dirParam = dirParamMap[currentTab] || 'image_dir';
                requestData[dirParam] = imageDir;
                requestData.image_dir = imageDir; // Backward compatibility
            }
            if (analysisId) {
                requestData.analysis_id = analysisId;
            }

            // Call backend to scan images and get mappings
            const response = await fetch('/api/ppt/scan-images', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

            const data = await response.json();

            // Hide loading state
            this.showScanLoading(false);

            if (data.success) {
                // Store scan results - include both request params and scanned images
                this.imageSource = {
                    ...requestData,
                    images: data.images,  // Include scanned images for backend
                    mappings: data.mappings  // Include mappings
                };
                this.scannedImages = data.images || {};
                this.imageMappings = data.mappings || [];

                // Store scan results for current tab
                const activeTab = document.querySelector('#imageTypeTabs button.active');
                if (activeTab) {
                    const tabId = activeTab.getAttribute('data-bs-target').replace('#', '');
                    if (this.tabImageSources[tabId]) {
                        this.tabImageSources[tabId].scannedImages = data;
                        this.tabImageSources[tabId].imageSource = this.imageSource;
                        sessionStorage.setItem('pptReplace_tabImageSources', JSON.stringify(this.tabImageSources));
                    }
                }

                // Enable replace button
                document.getElementById('replaceBtn').disabled = false;

                // Show mapping preview based on current tab type
                this.showMappingPreviewForCurrentTab(data);
            } else {
                // Fallback to client-side preview
                this.imageSource = requestData;
                document.getElementById('replaceBtn').disabled = false;
                this.showMappingPreview();
            }

        } catch (error) {
            console.error('Error scanning images:', error);
            this.showScanLoading(false);

            // Fallback: still allow replace with basic preview
            this.imageSource = {
                session_id: this.sessionId,
                image_dir: imageDir,
                heatmap_dir: imageDir,
                analysis_id: analysisId
            };
            document.getElementById('replaceBtn').disabled = false;
            this.showMappingPreview();
        }
    },

    /**
     * Scan images for comparison mode
     * Scans multiple source directories and prepares comparison data
     */
    async scanComparisonImages() {
        const validSources = this.comparisonMode.sources.filter(s => s.path && s.path.trim());
        
        if (validSources.length < 2) {
            this.showError('对比模式需要至少2个有效的图片来源');
            return;
        }
        
        this.showScanLoading(true);
        
        try {
            // Scan each source directory
            const scanPromises = validSources.map(async (source) => {
                const response = await fetch('/api/ppt-comparison/scan-heatmaps', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: source.path })
                });
                
                const data = await response.json();
                return {
                    ...source,
                    scannedImages: data.success ? data.heatmaps : [],
                    scanSuccess: data.success,
                    scanError: data.error
                };
            });
            
            const scanResults = await Promise.all(scanPromises);
            
            // Update sources with scan results
            scanResults.forEach(result => {
                const source = this.comparisonMode.sources.find(s => s.id === result.id);
                if (source) {
                    source.scannedImages = result.scannedImages;
                    source.scanSuccess = result.scanSuccess;
                    source.scanError = result.scanError;
                }
            });
            
            this.showScanLoading(false);
            
            // Check if all sources scanned successfully
            const successfulSources = scanResults.filter(s => s.scanSuccess);
            if (successfulSources.length < 2) {
                this.showError('扫描失败，至少需要2个有效的图片来源');
                return;
            }
            
            // Enable replace button
            document.getElementById('replaceBtn').disabled = false;
            
            // Show comparison preview
            this.showComparisonPreview(successfulSources);
            
            this.showSuccess(`成功扫描 ${successfulSources.length} 个项目的热图`);
            
        } catch (error) {
            console.error('Error scanning comparison images:', error);
            this.showScanLoading(false);
            this.showError('扫描图片时发生错误');
        }
    },

    /**
     * Show comparison preview with scanned images from multiple sources
     * @param {Array} sources - Array of sources with scanned images
     */
    showComparisonPreview(sources) {
        const card = document.getElementById('mappingCard');
        const list = document.getElementById('mappingList');
        const countBadge = document.getElementById('mappingCount');
        
        if (!card || !list) return;
        
        card.style.display = 'block';
        
        // Collect all metrics from all sources
        const allMetrics = new Set();
        sources.forEach(source => {
            (source.scannedImages || []).forEach(img => {
                if (img.metric) allMetrics.add(img.metric);
            });
        });
        
        const metricOrder = ['expression', 'morisita', 'cdr3', 'r2_inner', 'r2_outer', 'sorensen'];
        const sortedMetrics = Array.from(allMetrics).sort((a, b) => {
            const idxA = metricOrder.indexOf(a);
            const idxB = metricOrder.indexOf(b);
            return (idxA === -1 ? 999 : idxA) - (idxB === -1 ? 999 : idxB);
        });
        
        countBadge.textContent = `${sources.length} 个项目 × ${sortedMetrics.length} 个指标`;
        countBadge.className = 'badge bg-warning text-dark';
        
        // Build comparison preview HTML
        let html = `
            <div class="alert alert-warning mb-3 py-2">
                <small>
                    <i class="bi bi-columns-gap"></i>
                    <strong>对比模式:</strong> 将为每个指标生成包含 ${sources.length} 个项目热图的对比页面
                </small>
            </div>
        `;
        
        // Show each metric with images from all sources
        sortedMetrics.forEach(metric => {
            const metricDisplay = this.getMetricDisplayName(metric);
            
            html += `
                <div class="comparison-metric-group mb-3">
                    <div class="d-flex align-items-center mb-2">
                        <span class="badge bg-info me-2">${metricDisplay}</span>
                    </div>
                    <div class="comparison-preview-grid" style="grid-template-columns: repeat(${sources.length}, 1fr);">
            `;
            
            sources.forEach(source => {
                const img = (source.scannedImages || []).find(i => i.metric === metric);
                html += `
                    <div class="comparison-preview-item">
                        ${img ? `
                            <img src="data:image/png;base64,${img.image_data}" alt="${source.projectName}" 
                                 style="max-width: 100%; max-height: 80px; object-fit: contain;">
                        ` : `
                            <div class="text-muted small py-3">
                                <i class="bi bi-image"></i><br>无数据
                            </div>
                        `}
                        <div class="project-name">${source.projectName}</div>
                    </div>
                `;
            });
            
            html += `
                    </div>
                </div>
            `;
        });
        
        list.innerHTML = html;
    },

    /**
     * Get display name for a metric
     * @param {string} metric - Metric key
     * @returns {string} Display name
     */
    getMetricDisplayName(metric) {
        const names = {
            'expression': 'Expression Sharing',
            'morisita': 'Morisita-Horn Index',
            'cdr3': 'Unique CDR3 Sharing',
            'r2_inner': 'R² Inner',
            'r2_outer': 'R² Outer',
            'sorensen': 'Sorensen-Dice Index'
        };
        return names[metric] || metric;
    },

    /**
     * Replace images with comparison layout
     * Generates PPT with multiple project heatmaps side by side
     */
    async replaceWithComparison() {
        if (!this.sessionId) {
            this.showError('请先上传PPT模板');
            return;
        }
        
        // Get valid sources with scanned images
        const validSources = this.comparisonMode.sources.filter(s => s.scanSuccess && s.scannedImages?.length > 0);
        
        if (validSources.length < 2) {
            this.showError('对比模式需要至少2个有效的图片来源');
            return;
        }
        
        // Show progress
        document.getElementById('replaceProgress').style.display = 'block';
        document.getElementById('replaceBtn').disabled = true;
        
        try {
            // Build methods array for backend
            const methods = validSources.map(source => ({
                name: source.projectName,
                heatmaps: source.scannedImages
            }));
            
            // Call comparison API
            const response = await fetch('/api/ppt-comparison/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    methods: methods
                })
            });
            
            // Hide progress
            document.getElementById('replaceProgress').style.display = 'none';
            
            if (!response.ok) {
                const errorData = await response.json();
                this.showError(errorData.error || '生成对比PPT失败');
                document.getElementById('replaceBtn').disabled = false;
                return;
            }
            
            // Download the file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `comparison_heatmap_${new Date().toISOString().slice(0,10)}.pptx`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();
            
            // Update step indicator
            this.setStep(3);
            
            // Show success result
            const card = document.getElementById('resultCard');
            const message = document.getElementById('resultMessage');
            card.style.display = 'block';
            message.textContent = `已生成包含 ${validSources.length} 个项目对比的PPT`;
            
            this.showSuccess('对比PPT已生成并开始下载');
            
        } catch (error) {
            console.error('Error generating comparison PPT:', error);
            document.getElementById('replaceProgress').style.display = 'none';
            document.getElementById('replaceBtn').disabled = false;
            this.showError('生成对比PPT时发生错误');
        }
    },

    /**
     * Show/hide loading state during image scanning
     * @param {boolean} show - Whether to show loading
     */
    showScanLoading(show) {
        const scanBtn = document.getElementById('scanImagesBtn');

        if (show) {
            if (scanBtn) {
                scanBtn.disabled = true;
                scanBtn.innerHTML = `
                    <span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>
                    扫描中...
                `;
            }
        } else {
            if (scanBtn) {
                scanBtn.disabled = false;
                scanBtn.innerHTML = '<i class="bi bi-search"></i> 扫描图片文件';
            }
        }
    },

    /**
     * Show mapping preview for a specific tab from stored data
     * @param {string} tabId - Tab ID to show mapping for
     */
    showTabMappingPreview(tabId) {
        const source = this.tabImageSources[tabId];
        if (source && source.scannedImages) {
            this.showMappingPreviewForCurrentTab(source.scannedImages);
        }
    },

    /**
     * Show mapping preview based on current tab type
     * @param {Object} data - Scan results from backend
     */
    showMappingPreviewForCurrentTab(data) {
        const currentTab = this.currentTab || 'sharing_analysis';

        if (currentTab === 'sharing_analysis') {
            // For sharing analysis: show fixed layout replacement mapping
            this.showSharingAnalysisMappingPreview(data);
        } else {
            // For other modules: show layout preview with drag-drop
            this.showSampleBasedLayoutPreview(data);
        }
    },

    /**
     * Show sharing analysis mapping preview (fixed layout)
     * @param {Object} data - Scan results
     */
    showSharingAnalysisMappingPreview(data) {
        const card = document.getElementById('mappingCard');
        const list = document.getElementById('mappingList');
        const countBadge = document.getElementById('mappingCount');

        card.style.display = 'block';

        const mappings = (data.mappings || []).filter(m =>
            m.image_type === 'sharing_analysis' || m.chain
        );
        this.currentMappings = mappings;

        // Debug logging to understand data structure
        console.log('showSharingAnalysisMappingPreview - slideData count:', this.slideData.length);
        console.log('showSharingAnalysisMappingPreview - mappings count:', mappings.length);
        if (this.slideData.length > 0 && this.slideData[0].image_positions?.length > 0) {
            const firstImg = this.slideData[0].image_positions[0];
            console.log('First slide first image - metric:', firstImg.metric, 'has data_url:', !!firstImg.data_url);
        }

        countBadge.textContent = `${mappings.length} 个热图映射`;
        countBadge.classList.remove('bg-success', 'bg-warning');
        countBadge.classList.add(mappings.length > 0 ? 'bg-success' : 'bg-warning');

        let html = `
            <div class="alert alert-info mb-2 py-2">
                <small>
                    <i class="bi bi-info-circle"></i>
                    相似度热图替换 - 固定布局，每条链2页，每页3个热图
                </small>
            </div>
        `;

        // Metric to slide type mapping
        const slideType1Metrics = ['expression', 'r2_outer', 'r2_inner'];
        const slideType2Metrics = ['morisita_horn', 'ucdr3', 'sorensen'];

        // Store image paths to load after DOM update
        const imagesToLoad = [];

        mappings.forEach((mapping, idx) => {
            const hasFile = mapping.has_file || (mapping.image_path && mapping.image_path.length > 0);
            const statusIcon = hasFile
                ? '<i class="bi bi-check-circle text-success"></i>'
                : '<i class="bi bi-x-circle text-danger"></i>';
            const fileName = mapping.image_file || (mapping.image_path ? mapping.image_path.split(/[\\/]/).pop() : '未找到');

            // Find matching slide from slideData based on chain and metric
            let pptImageDataUrl = '';
            let slideIndex = 0;
            let positionIndex = 0;

            // Determine which slide type this metric belongs to
            const isSlideType1 = slideType1Metrics.includes(mapping.metric);
            const slideNumber = isSlideType1 ? 1 : 2;

            // Find the slide for this chain and slide type
            const matchingSlide = this.slideData.find(s =>
                s.chain_type === mapping.chain &&
                s.slide_number_for_chain === slideNumber
            );

            console.log(`Mapping ${idx}: chain=${mapping.chain}, metric=${mapping.metric}, slideNumber=${slideNumber}, matchingSlide found: ${!!matchingSlide}`);

            if (matchingSlide) {
                slideIndex = matchingSlide.slide_index;
                console.log(`  matchingSlide.slide_index=${slideIndex}, image_positions count=${matchingSlide.image_positions?.length}`);

                // Find the image by metric name instead of position index
                // This is more robust as it doesn't depend on sorting order
                const matchingImage = matchingSlide.image_positions?.find(img =>
                    img.metric === mapping.metric
                );

                console.log(`  Looking for metric=${mapping.metric}, matchingImage found: ${!!matchingImage}, has data_url: ${!!matchingImage?.data_url}`);
                if (matchingImage?.data_url) {
                    console.log(`  data_url length: ${matchingImage.data_url.length}, starts with: ${matchingImage.data_url.substring(0, 30)}`);
                }

                if (matchingImage) {
                    pptImageDataUrl = matchingImage.data_url || '';
                    positionIndex = matchingImage.index || 0;
                } else {
                    // Fallback to position index if metric matching fails
                    const metricsInSlide = isSlideType1 ? slideType1Metrics : slideType2Metrics;
                    positionIndex = metricsInSlide.indexOf(mapping.metric);
                    console.log(`  Fallback to position index: ${positionIndex}`);

                    if (matchingSlide.image_positions && matchingSlide.image_positions[positionIndex]) {
                        pptImageDataUrl = matchingSlide.image_positions[positionIndex].data_url || '';
                        console.log(`  Fallback data_url found: ${!!pptImageDataUrl}, length: ${pptImageDataUrl.length}`);
                    }
                }

                // CRITICAL FIX: Add slide_index and position_index to mapping object
                // so they're available in showMappingDetail
                mapping.slide_index = slideIndex;
                mapping.position_index = positionIndex;
            } else {
                console.warn(`  No matching slide found for chain=${mapping.chain}, slideNumber=${slideNumber}`);
            }

            // Fix issue #1 & #2: Mapping direction should be: Source image (folder) → PPT slide image
            // Left side: source image from folder (load asynchronously)
            // Right side: PPT slide image (current image in PPT)
            const sourceImageId = `source-img-${idx}`;
            html += `
                <div class="mapping-item-visual" onclick="PPTReplace.showMappingDetail(${idx})" title="点击查看详情">
                    <div class="d-flex align-items-center flex-grow-1">
                        <div id="${sourceImageId}" class="mapping-image-preview me-2 bg-light d-flex align-items-center justify-content-center" style="width:60px;height:60px;border-radius:4px;border:1px solid #dee2e6;">
                            ${hasFile ? '<i class="bi bi-file-image text-success"></i>' : '<i class="bi bi-x-circle text-danger"></i>'}
                        </div>
                        <span class="mapping-arrow"><i class="bi bi-arrow-right"></i></span>
                        ${pptImageDataUrl ? `<img src="${pptImageDataUrl}" class="mapping-image-preview me-2" alt="PPT图片" style="width:60px;height:60px;object-fit:cover;border-radius:4px;border:1px solid #dee2e6;">` : '<div class="mapping-image-preview me-2 bg-light d-flex align-items-center justify-content-center" style="width:60px;height:60px;border-radius:4px;border:1px solid #dee2e6;"><i class="bi bi-image text-muted"></i></div>'}
                        <div class="mapping-info">
                            <div>
                                <span class="badge ${this.getChainColor(mapping.chain)} me-1">${mapping.chain || 'N/A'}</span>
                                <strong>${this.formatMetricName(mapping.metric)}</strong>
                            </div>
                            <small class="text-muted">${hasFile ? fileName : '未找到图片文件'}</small>
                        </div>
                    </div>
                    <div class="mapping-status">
                        ${statusIcon}
                        <small class="ms-1 text-muted">幻灯片 ${slideIndex + 1}</small>
                    </div>
                </div>
            `;

            // Store image info for loading after DOM update
            if (hasFile && mapping.image_path) {
                imagesToLoad.push({
                    path: mapping.image_path,
                    elementId: sourceImageId
                });
            }
        });

        list.innerHTML = html || '<p class="text-muted text-center">未找到匹配的热图</p>';

        // Load source images asynchronously AFTER DOM is updated
        imagesToLoad.forEach(img => {
            this.loadSourceImageThumbnail(img.path, img.elementId);
        });
    },

    /**
     * Show slide-based layout editor for sample-based modules (Network Plots, Isotype Upset, Tree Maps)
     * Instead of image mapping, users select slides and customize layout
     * @param {Object} data - Scan results
     */
    showSampleBasedLayoutPreview(data) {
        const card = document.getElementById('mappingCard');
        const list = document.getElementById('mappingList');
        const countBadge = document.getElementById('mappingCount');

        card.style.display = 'block';

        const currentTab = this.currentTab || 'network_plots';
        const typeDisplay = this.IMAGE_TYPE_NAMES[currentTab] || currentTab;

        // Get slides for current module type
        const moduleSlides = this.slideData.filter(slide => {
            const slideType = slide.image_type || 'sharing_analysis';
            return slideType === currentTab;
        });

        // Get scanned images for this module
        const images = data.images || {};
        const typeImages = images[currentTab] || {};
        const samples = Object.keys(typeImages);
        const imageCount = samples.length;

        // Store layout config
        this.currentLayoutConfig = {
            type: currentTab,
            images: typeImages,
            samples: samples,
            slides: moduleSlides,
            itemsPerRow: this.getDefaultItemsPerRow(imageCount),
            sampleOrder: [...samples]  // Default order
        };

        countBadge.textContent = `${moduleSlides.length} 个幻灯片`;
        countBadge.classList.remove('bg-success', 'bg-warning');
        countBadge.classList.add(moduleSlides.length > 0 ? 'bg-success' : 'bg-warning');

        let html = '';

        // Show slide selection and layout controls
        html += `
            <div class="slide-layout-editor">
                <!-- Header with module info -->
                <div class="alert alert-info mb-3 py-2">
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <i class="bi bi-file-earmark-slides"></i>
                            <strong>${typeDisplay}</strong> - 识别到 ${moduleSlides.length} 个幻灯片页，${imageCount} 个样本图片
                        </div>
                    </div>
                </div>

                <!-- Layout Controls -->
                <div class="layout-controls mb-3 p-3 bg-light rounded">
                    <div class="row align-items-center">
                        <div class="col-md-4">
                            <label class="form-label mb-1"><i class="bi bi-grid"></i> 每行显示数量</label>
                            <select class="form-select form-select-sm" id="itemsPerRowSelect" onchange="PPTReplace.updateLayoutItemsPerRow(this.value)">
                                <option value="2" ${this.currentLayoutConfig.itemsPerRow === 2 ? 'selected' : ''}>2 个/行</option>
                                <option value="3" ${this.currentLayoutConfig.itemsPerRow === 3 ? 'selected' : ''}>3 个/行</option>
                                <option value="4" ${this.currentLayoutConfig.itemsPerRow === 4 ? 'selected' : ''}>4 个/行</option>
                                <option value="5" ${this.currentLayoutConfig.itemsPerRow === 5 ? 'selected' : ''}>5 个/行</option>
                                <option value="6" ${this.currentLayoutConfig.itemsPerRow === 6 ? 'selected' : ''}>6 个/行</option>
                            </select>
                        </div>
                        <div class="col-md-4">
                            <label class="form-label mb-1"><i class="bi bi-calculator"></i> 预计页数</label>
                            <div class="form-control-plaintext">
                                <span class="badge bg-primary" id="estimatedPages">${this.calculateEstimatedPages(imageCount, this.currentLayoutConfig.itemsPerRow)}</span> 页
                            </div>
                        </div>
                        <div class="col-md-4 text-end">
                            <button class="btn btn-sm btn-outline-secondary" onclick="PPTReplace.resetSampleOrder()">
                                <i class="bi bi-arrow-counterclockwise"></i> 重置顺序
                            </button>
                        </div>
                    </div>
                </div>
        `;

        // Show slide preview if slides exist
        if (moduleSlides.length > 0) {
            html += this.renderSlidePreviewSection(moduleSlides);
        }

        // Show sample list with drag-drop reordering
        if (imageCount > 0) {
            html += this.renderSampleOrderSection(samples, typeImages);
        } else {
            html += `
                <div class="alert alert-warning">
                    <i class="bi bi-exclamation-triangle"></i> 未找到 ${typeDisplay} 图片文件
                </div>
            `;
        }

        // Show PPT page layout preview
        html += this.renderPPTLayoutPreview();

        html += '</div>';  // Close slide-layout-editor

        list.innerHTML = html;

        // Initialize drag-drop for sample reordering
        this.initSampleDragDrop();
    },

    /**
     * Get default items per row based on sample count
     */
    getDefaultItemsPerRow(count) {
        if (count <= 4) return 2;
        if (count <= 9) return 3;
        if (count <= 16) return 4;
        return 5;
    },

    /**
     * Calculate estimated pages based on sample count and items per row
     */
    calculateEstimatedPages(sampleCount, itemsPerRow) {
        const itemsPerPage = itemsPerRow * 2;  // Assume 2 rows per page
        return Math.ceil(sampleCount / itemsPerPage);
    },

    buildLayoutConfig() {
        if (!this.currentLayoutConfig) {
            return null;
        }

        const itemsPerRow = Math.max(1, parseInt(this.currentLayoutConfig.itemsPerRow || 3, 10));
        const rowsPerPage = 2;
        const sampleOrder = this.currentLayoutConfig.sampleOrder || this.currentLayoutConfig.samples || [];
        const itemsPerPage = itemsPerRow * rowsPerPage;
        const pages = [];

        for (let pageIndex = 0; pageIndex * itemsPerPage < sampleOrder.length; pageIndex++) {
            const pageSamples = sampleOrder.slice(pageIndex * itemsPerPage, (pageIndex + 1) * itemsPerPage);
            const slots = pageSamples.map((sampleName, idx) => ({
                sample_name: sampleName,
                row: Math.floor(idx / itemsPerRow),
                col: idx % itemsPerRow
            }));
            pages.push({ page_index: pageIndex, slots: slots });
        }

        return {
            image_type: this.currentLayoutConfig.type,
            strategy: 'near_square',
            items_per_row: itemsPerRow,
            rows_per_page: rowsPerPage,
            sample_order: sampleOrder,
            pages: pages
        };
    },

    /**
     * Update layout items per row
     */
    updateLayoutItemsPerRow(value) {
        if (!this.currentLayoutConfig) return;

        this.currentLayoutConfig.itemsPerRow = parseInt(value);

        // Update estimated pages display
        const estimatedPages = this.calculateEstimatedPages(
            this.currentLayoutConfig.samples.length,
            this.currentLayoutConfig.itemsPerRow
        );
        const badge = document.getElementById('estimatedPages');
        if (badge) badge.textContent = estimatedPages;

        // Re-render PPT layout preview
        const previewContainer = document.getElementById('pptLayoutPreview');
        if (previewContainer) {
            previewContainer.innerHTML = this.renderPPTPageGrid();
        }
    },

    /**
     * Render slide preview section showing identified slides
     */
    renderSlidePreviewSection(slides) {
        let html = `
            <div class="slide-preview-section mb-3">
                <h6 class="mb-2"><i class="bi bi-collection"></i> 识别的幻灯片页</h6>
                <div class="slide-thumbnails d-flex flex-wrap gap-2">
        `;

        slides.forEach((slide, idx) => {
            const slideNum = slide.slide_index + 1;
            const hasPreview = slide.image_positions?.length > 0 && slide.image_positions[0].data_url;

            html += `
                <div class="slide-thumbnail-card" data-slide-index="${slide.slide_index}">
                    <div class="slide-thumb-preview">
                        ${hasPreview
                    ? `<img src="${slide.image_positions[0].data_url}" alt="幻灯片 ${slideNum}" class="slide-thumb-img">`
                    : `<div class="slide-thumb-placeholder"><i class="bi bi-file-earmark-slides"></i></div>`
                }
                    </div>
                    <div class="slide-thumb-label">第 ${slideNum} 页</div>
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;

        return html;
    },

    /**
     * Render sample order section with drag-drop support
     */
    renderSampleOrderSection(samples, images) {
        let html = `
            <div class="sample-order-section mb-3">
                <h6 class="mb-2"><i class="bi bi-list-ol"></i> 样本顺序 <small class="text-muted">(拖拽调整顺序)</small></h6>
                <div class="sample-order-list" id="sampleOrderList">
        `;

        const sampleOrder = this.currentLayoutConfig?.sampleOrder || samples;

        sampleOrder.forEach((sample, idx) => {
            html += `
                <div class="sample-order-item" draggable="true" data-sample="${sample}" data-index="${idx}">
                    <div class="sample-drag-handle">
                        <i class="bi bi-grip-vertical"></i>
                    </div>
                    <div class="sample-order-number">${idx + 1}</div>
                    <div class="sample-order-name">${sample}</div>
                    <div class="sample-order-preview">
                        <i class="bi bi-image text-muted"></i>
                    </div>
                </div>
            `;
        });

        html += `
                </div>
            </div>
        `;

        return html;
    },

    /**
     * Render PPT page layout preview
     */
    renderPPTLayoutPreview() {
        return `
            <div class="ppt-layout-preview-section">
                <h6 class="mb-2"><i class="bi bi-easel"></i> PPT布局预览</h6>
                <div id="pptLayoutPreview" class="ppt-layout-preview">
                    ${this.renderPPTPageGrid()}
                </div>
            </div>
        `;
    },

    /**
     * Render PPT page grid showing how samples will be arranged
     */
    renderPPTPageGrid() {
        if (!this.currentLayoutConfig) return '<p class="text-muted">请先扫描图片</p>';

        const { samples, sampleOrder, itemsPerRow } = this.currentLayoutConfig;
        const orderedSamples = sampleOrder || samples;
        const itemsPerPage = itemsPerRow * 2;  // 2 rows per page
        const pages = Math.ceil(orderedSamples.length / itemsPerPage);

        let html = '<div class="ppt-pages-grid">';

        for (let pageIdx = 0; pageIdx < pages; pageIdx++) {
            const startIdx = pageIdx * itemsPerPage;
            const pageSamples = orderedSamples.slice(startIdx, startIdx + itemsPerPage);

            html += `
                <div class="ppt-page-card mb-3">
                    <div class="ppt-page-header">
                        <span class="badge bg-primary">第 ${pageIdx + 1} 页</span>
                        <small class="text-muted">${pageSamples.length} 个样本</small>
                    </div>
                    <div class="ppt-page-content">
                        <div class="ppt-page-grid-preview" style="grid-template-columns: repeat(${itemsPerRow}, 1fr);">
            `;

            pageSamples.forEach((sample) => {
                html += `
                    <div class="ppt-sample-cell">
                        <div class="sample-cell-name">${sample}</div>
                        <div class="sample-cell-image"><i class="bi bi-image"></i></div>
                    </div>
                `;
            });

            // Fill empty cells if needed
            const emptyCells = itemsPerPage - pageSamples.length;
            for (let i = 0; i < emptyCells; i++) {
                html += `<div class="ppt-sample-cell empty"></div>`;
            }

            html += `
                        </div>
                    </div>
                </div>
            `;
        }

        html += '</div>';
        return html;
    },

    /**
     * Initialize drag-drop for sample reordering
     */
    initSampleDragDrop() {
        const container = document.getElementById('sampleOrderList');
        if (!container) return;

        const items = container.querySelectorAll('.sample-order-item');

        items.forEach(item => {
            item.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData('text/plain', item.dataset.index);
                item.classList.add('dragging');
            });

            item.addEventListener('dragend', () => {
                item.classList.remove('dragging');
            });

            item.addEventListener('dragover', (e) => {
                e.preventDefault();
                item.classList.add('drag-over');
            });

            item.addEventListener('dragleave', () => {
                item.classList.remove('drag-over');
            });

            item.addEventListener('drop', (e) => {
                e.preventDefault();
                item.classList.remove('drag-over');

                const fromIndex = parseInt(e.dataTransfer.getData('text/plain'));
                const toIndex = parseInt(item.dataset.index);

                if (fromIndex !== toIndex) {
                    this.reorderSamples(fromIndex, toIndex);
                }
            });
        });
    },

    /**
     * Reorder samples
     */
    reorderSamples(fromIndex, toIndex) {
        if (!this.currentLayoutConfig?.sampleOrder) return;

        const order = this.currentLayoutConfig.sampleOrder;
        const [moved] = order.splice(fromIndex, 1);
        order.splice(toIndex, 0, moved);

        // Re-render sample order list and PPT preview
        const sampleSection = document.querySelector('.sample-order-section');
        if (sampleSection) {
            sampleSection.outerHTML = this.renderSampleOrderSection(
                this.currentLayoutConfig.samples,
                this.currentLayoutConfig.images
            );
            this.initSampleDragDrop();
        }

        const previewContainer = document.getElementById('pptLayoutPreview');
        if (previewContainer) {
            previewContainer.innerHTML = this.renderPPTPageGrid();
        }
    },

    /**
     * Reset sample order to original
     */
    resetSampleOrder() {
        if (!this.currentLayoutConfig) return;

        this.currentLayoutConfig.sampleOrder = [...this.currentLayoutConfig.samples];

        // Re-render
        const sampleSection = document.querySelector('.sample-order-section');
        if (sampleSection) {
            sampleSection.outerHTML = this.renderSampleOrderSection(
                this.currentLayoutConfig.samples,
                this.currentLayoutConfig.images
            );
            this.initSampleDragDrop();
        }

        const previewContainer = document.getElementById('pptLayoutPreview');
        if (previewContainer) {
            previewContainer.innerHTML = this.renderPPTPageGrid();
        }
    },

    /**
     * Generate intelligent layout based on sample count (kept for backward compatibility)
     * @param {number} count - Number of samples
     * @returns {Object} Layout configuration
     */
    generateIntelligentLayout(count) {
        // Layout rules based on sample count
        if (count <= 0) {
            return { pages: 0, layouts: [] };
        } else if (count <= 4) {
            return { pages: 1, layouts: [{ page: 1, rows: 2, cols: 2, samples: count }] };
        } else if (count <= 6) {
            return { pages: 1, layouts: [{ page: 1, rows: 2, cols: 3, samples: count }] };
        } else if (count <= 9) {
            return { pages: 1, layouts: [{ page: 1, rows: 3, cols: 3, samples: count }] };
        } else {
            const pages = Math.ceil(count / 9);
            const layouts = [];
            for (let i = 0; i < pages; i++) {
                const remaining = count - (i * 9);
                layouts.push({ page: i + 1, rows: 3, cols: 3, samples: Math.min(9, remaining) });
            }
            return { pages, layouts };
        }
    },

    /**
     * Render layout preview showing PPT page structure
     * @param {Object} layout - Layout configuration
     * @param {Object} images - Image paths
     * @param {Array} samples - Sample names
     * @returns {string} HTML
     */
    renderLayoutPreview(layout, images, samples) {
        let html = '<div class="layout-pages-container">';

        let sampleIndex = 0;
        layout.layouts.forEach((pageLayout, pageIdx) => {
            html += `
                <div class="layout-page-preview mb-3">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <h6 class="mb-0">
                            <i class="bi bi-file-earmark-slides"></i> 
                            页面 ${pageLayout.page}
                        </h6>
                        <span class="badge bg-secondary">${pageLayout.rows}×${pageLayout.cols}</span>
                    </div>
                    <div class="ppt-page-mockup">
                        <div class="ppt-page-grid" style="grid-template-columns: repeat(${pageLayout.cols}, 1fr); grid-template-rows: repeat(${pageLayout.rows}, 1fr);">
            `;

            // Render grid cells
            for (let i = 0; i < pageLayout.samples; i++) {
                const sample = samples[sampleIndex];
                const imagePath = images[sample];
                const cellId = `layout-cell-${pageIdx}-${i}`;

                html += `
                    <div class="ppt-grid-cell" id="${cellId}" data-sample="${sample}" data-page="${pageIdx}" data-position="${i}">
                        <div class="cell-content">
                            <div class="cell-label">${sample}</div>
                            <div class="cell-image-placeholder">
                                <i class="bi bi-image"></i>
                            </div>
                        </div>
                    </div>
                `;
                sampleIndex++;
            }

            html += `
                        </div>
                    </div>
                </div>
            `;
        });

        html += '</div>';
        return html;
    },

    /**
     * Show layout editor modal for custom layout design
     */
    showLayoutEditor() {
        if (!this.currentLayoutConfig) {
            this.showError('请先扫描图片');
            return;
        }

        const modal = document.getElementById('layoutEditorModal') || this.createLayoutEditorModal();
        this.renderLayoutEditor(modal);

        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    },

    /**
     * Create layout editor modal
     * @returns {HTMLElement} Modal element
     */
    createLayoutEditorModal() {
        const modalHtml = `
            <div class="modal fade" id="layoutEditorModal" tabindex="-1">
                <div class="modal-dialog modal-xl">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="bi bi-grid-3x3"></i> 自定义布局设计
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="row">
                                <div class="col-md-3">
                                    <h6>样本列表</h6>
                                    <div id="layoutEditorSamples" class="sample-list"></div>
                                </div>
                                <div class="col-md-9">
                                    <div class="d-flex justify-content-between mb-3">
                                        <h6>页面布局</h6>
                                        <div class="btn-group btn-group-sm">
                                            <button class="btn btn-outline-secondary" onclick="PPTReplace.addLayoutPage()">
                                                <i class="bi bi-plus"></i> 添加页面
                                            </button>
                                            <button class="btn btn-outline-secondary" onclick="PPTReplace.resetToIntelligentLayout()">
                                                <i class="bi bi-arrow-counterclockwise"></i> 重置为智能布局
                                            </button>
                                        </div>
                                    </div>
                                    <div id="layoutEditorCanvas" class="layout-editor-canvas"></div>
                                </div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                            <button type="button" class="btn btn-primary" onclick="PPTReplace.applyCustomLayout()">应用布局</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        const div = document.createElement('div');
        div.innerHTML = modalHtml;
        document.body.appendChild(div.firstElementChild);
        return document.getElementById('layoutEditorModal');
    },

    /**
     * Render layout editor content
     */
    renderLayoutEditor(modal) {
        const samplesContainer = modal.querySelector('#layoutEditorSamples');
        const canvasContainer = modal.querySelector('#layoutEditorCanvas');

        const config = this.currentLayoutConfig;
        const layout = config.customLayout || config.layout;

        // Render sample list (draggable)
        let samplesHtml = '<div class="list-group">';
        config.samples.forEach((sample, idx) => {
            samplesHtml += `
                <div class="list-group-item list-group-item-action sample-drag-item" 
                     draggable="true" 
                     data-sample="${sample}">
                    <i class="bi bi-grip-vertical me-2"></i>
                    <small>${sample}</small>
                </div>
            `;
        });
        samplesHtml += '</div>';
        samplesContainer.innerHTML = samplesHtml;

        // Render layout canvas (droppable pages)
        let canvasHtml = '';
        layout.layouts.forEach((pageLayout, pageIdx) => {
            canvasHtml += this.renderEditablePage(pageLayout, pageIdx);
        });
        canvasContainer.innerHTML = canvasHtml;

        // Initialize drag-drop for layout editor
        this.initLayoutEditorDragDrop();
    },

    /**
     * Render editable page in layout editor
     */
    renderEditablePage(pageLayout, pageIdx) {
        return `
            <div class="editable-page mb-3" data-page="${pageIdx}">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <strong>页面 ${pageLayout.page}</strong>
                    <div class="btn-group btn-group-sm">
                        <select class="form-select form-select-sm" onchange="PPTReplace.changePageGrid(${pageIdx}, this.value)">
                            <option value="2x2" ${pageLayout.rows === 2 && pageLayout.cols === 2 ? 'selected' : ''}>2×2</option>
                            <option value="2x3" ${pageLayout.rows === 2 && pageLayout.cols === 3 ? 'selected' : ''}>2×3</option>
                            <option value="3x3" ${pageLayout.rows === 3 && pageLayout.cols === 3 ? 'selected' : ''}>3×3</option>
                            <option value="3x4" ${pageLayout.rows === 3 && pageLayout.cols === 4 ? 'selected' : ''}>3×4</option>
                        </select>
                        <button class="btn btn-outline-danger btn-sm" onclick="PPTReplace.removeLayoutPage(${pageIdx})">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
                <div class="ppt-page-mockup editable">
                    <div class="ppt-page-grid droppable" 
                         style="grid-template-columns: repeat(${pageLayout.cols}, 1fr); grid-template-rows: repeat(${pageLayout.rows}, 1fr);"
                         data-page="${pageIdx}">
                        ${this.renderEditableGridCells(pageLayout, pageIdx)}
                    </div>
                </div>
            </div>
        `;
    },

    /**
     * Render editable grid cells
     */
    renderEditableGridCells(pageLayout, pageIdx) {
        let html = '';
        const maxCells = pageLayout.rows * pageLayout.cols;

        for (let i = 0; i < maxCells; i++) {
            html += `
                <div class="ppt-grid-cell editable droppable" 
                     data-page="${pageIdx}" 
                     data-position="${i}">
                    <div class="cell-content">
                        <div class="cell-placeholder">
                            <i class="bi bi-plus-circle"></i>
                            <small>拖拽样本到此</small>
                        </div>
                    </div>
                </div>
            `;
        }

        return html;
    },

    /**
     * Initialize drag-drop for layout editor
     */
    initLayoutEditorDragDrop() {
        // Make sample items draggable
        const sampleItems = document.querySelectorAll('.sample-drag-item');
        sampleItems.forEach(item => {
            item.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData('sample', item.dataset.sample);
                item.classList.add('dragging');
            });

            item.addEventListener('dragend', () => {
                item.classList.remove('dragging');
            });
        });

        // Make grid cells droppable
        const cells = document.querySelectorAll('.ppt-grid-cell.droppable');
        cells.forEach(cell => {
            cell.addEventListener('dragover', (e) => {
                e.preventDefault();
                cell.classList.add('drag-over');
            });

            cell.addEventListener('dragleave', () => {
                cell.classList.remove('drag-over');
            });

            cell.addEventListener('drop', (e) => {
                e.preventDefault();
                cell.classList.remove('drag-over');

                const sample = e.dataTransfer.getData('sample');
                if (sample) {
                    this.placeSampleInCell(cell, sample);
                }
            });
        });
    },

    /**
     * Place sample in grid cell
     */
    placeSampleInCell(cell, sample) {
        cell.dataset.sample = sample;
        cell.querySelector('.cell-content').innerHTML = `
            <div class="cell-label">${sample}</div>
            <div class="cell-image-placeholder">
                <i class="bi bi-image"></i>
            </div>
            <button class="btn btn-sm btn-danger cell-remove-btn" onclick="PPTReplace.removeSampleFromCell(this)">
                <i class="bi bi-x"></i>
            </button>
        `;
    },

    /**
     * Remove sample from cell
     */
    removeSampleFromCell(btn) {
        const cell = btn.closest('.ppt-grid-cell');
        delete cell.dataset.sample;
        cell.querySelector('.cell-content').innerHTML = `
            <div class="cell-placeholder">
                <i class="bi bi-plus-circle"></i>
                <small>拖拽样本到此</small>
            </div>
        `;
    },

    /**
     * Change page grid layout
     */
    changePageGrid(pageIdx, gridValue) {
        const [rows, cols] = gridValue.split('x').map(Number);
        // Re-render the page with new grid
        this.showError('网格布局更改功能开发中');
    },

    /**
     * Add new layout page
     */
    addLayoutPage() {
        this.showError('添加页面功能开发中');
    },

    /**
     * Remove layout page
     */
    removeLayoutPage(pageIdx) {
        this.showError('删除页面功能开发中');
    },

    /**
     * Reset to intelligent layout
     */
    resetToIntelligentLayout() {
        if (this.currentLayoutConfig) {
            this.currentLayoutConfig.customLayout = null;
            const modal = document.getElementById('layoutEditorModal');
            this.renderLayoutEditor(modal);
        }
    },

    /**
     * Apply custom layout
     */
    applyCustomLayout() {
        // Collect layout from editor
        const cells = document.querySelectorAll('.ppt-grid-cell.editable[data-sample]');
        const customLayout = {
            pages: 0,
            layouts: [],
            mapping: {}
        };

        // Group by page
        const pageMap = new Map();
        cells.forEach(cell => {
            const page = parseInt(cell.dataset.page);
            const position = parseInt(cell.dataset.position);
            const sample = cell.dataset.sample;

            if (!pageMap.has(page)) {
                pageMap.set(page, []);
            }
            pageMap.get(page).push({ position, sample });
        });

        // Build layout structure
        pageMap.forEach((samples, page) => {
            customLayout.layouts.push({
                page: page + 1,
                samples: samples
            });
        });

        customLayout.pages = pageMap.size;
        this.currentLayoutConfig.customLayout = customLayout;

        // Close modal and refresh preview
        const modal = bootstrap.Modal.getInstance(document.getElementById('layoutEditorModal'));
        modal.hide();

        this.showSuccess('自定义布局已应用');
    },

    /**
     * Initialize drag-drop for layout reordering
     */
    initLayoutDragDrop() {
        const container = document.getElementById('sortableLayout');
        if (!container) return;

        const items = container.querySelectorAll('.layout-item');

        items.forEach(item => {
            item.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData('text/plain', item.dataset.index);
                item.classList.add('dragging');
            });

            item.addEventListener('dragend', () => {
                item.classList.remove('dragging');
            });

            item.addEventListener('dragover', (e) => {
                e.preventDefault();
                item.classList.add('drag-over');
            });

            item.addEventListener('dragleave', () => {
                item.classList.remove('drag-over');
            });

            item.addEventListener('drop', (e) => {
                e.preventDefault();
                item.classList.remove('drag-over');

                const fromIndex = parseInt(e.dataTransfer.getData('text/plain'));
                const toIndex = parseInt(item.dataset.index);

                if (fromIndex !== toIndex) {
                    this.reorderLayoutItems(fromIndex, toIndex);
                }
            });
        });
    },

    /**
     * Reorder layout items
     */
    reorderLayoutItems(fromIndex, toIndex) {
        if (!this.currentLayoutConfig || !this.currentLayoutConfig.order) return;

        const order = this.currentLayoutConfig.order;
        const [moved] = order.splice(fromIndex, 1);
        order.splice(toIndex, 0, moved);

        // Re-render layout preview
        this.showSampleBasedLayoutPreview({
            images: { [this.currentLayoutConfig.type]: this.currentLayoutConfig.images }
        });
    },

    /**
     * Reset layout order to original
     */
    resetLayoutOrder() {
        if (!this.currentLayoutConfig) return;

        this.currentLayoutConfig.order = Object.keys(this.currentLayoutConfig.images);
        this.showSampleBasedLayoutPreview({
            images: { [this.currentLayoutConfig.type]: this.currentLayoutConfig.images }
        });
    },

    /**
     * Load and preview sample image
     */
    async loadAndPreviewSampleImage(imagePath, sampleName) {
        const dataUrl = await this.loadImageFromPath(imagePath);
        if (dataUrl) {
            this.showImagePreview(dataUrl, `${sampleName} - ${imagePath.split(/[\\/]/).pop()}`);
        } else {
            this.showError('无法加载图片预览');
        }
    },

    /**
     * Show mapping preview with actual scan results from backend
     * @param {Object} data - Scan results from backend
     */
    showMappingPreviewWithResults(data) {
        const card = document.getElementById('mappingCard');
        const list = document.getElementById('mappingList');
        const countBadge = document.getElementById('mappingCount');

        card.style.display = 'block';

        const mappings = data.mappings || [];
        const images = data.images || {};

        // Store mappings for later use
        this.currentMappings = mappings;

        countBadge.textContent = `${mappings.length} 个图片映射`;
        countBadge.classList.remove('bg-success', 'bg-warning');
        countBadge.classList.add(mappings.length > 0 ? 'bg-success' : 'bg-warning');

        let html = '';

        // Show summary of found images
        if (data.summary) {
            html += `
                <div class="alert alert-info mb-2 py-2">
                    <small>
                        <i class="bi bi-info-circle"></i>
                        ${data.summary}
                    </small>
                </div>
            `;
        }

        mappings.forEach((mapping, idx) => {
            const hasFile = mapping.has_file || (mapping.image_path && mapping.image_path.length > 0);
            const statusIcon = hasFile
                ? '<i class="bi bi-check-circle text-success"></i>'
                : '<i class="bi bi-x-circle text-danger"></i>';
            const fileName = mapping.image_file || (mapping.image_path ? mapping.image_path.split(/[\\/]/).pop() : '未找到');
            const imagePath = mapping.image_path || '';

            // Get PPT slide image from slide data - match by metric name for sharing_analysis
            let pptImageDataUrl = '';
            const slideInfo = this.slideData.find(s => s.slide_index === mapping.slide_index);

            if (slideInfo && slideInfo.image_positions) {
                if (mapping.metric) {
                    // For sharing_analysis, match by metric name
                    const matchingImage = slideInfo.image_positions.find(img => img.metric === mapping.metric);
                    pptImageDataUrl = matchingImage?.data_url || '';
                }
                if (!pptImageDataUrl) {
                    // Fallback to position index
                    pptImageDataUrl = slideInfo.image_positions[mapping.position_index || 0]?.data_url || '';
                }
            }

            // Fix issue #2: Mapping direction should be: Source image (folder) → PPT slide image
            if (mapping.image_type === 'sharing_analysis' || mapping.chain) {
                // Sharing Analysis mapping with visual preview
                html += `
                    <div class="mapping-item-visual" onclick="PPTReplace.showMappingDetail(${idx})" title="点击查看详情">
                        <div class="d-flex align-items-center flex-grow-1">
                            <div class="mapping-image-preview me-2 bg-light d-flex align-items-center justify-content-center" style="width:60px;height:60px;border-radius:4px;border:1px solid #dee2e6;">
                                ${hasFile ? '<i class="bi bi-file-image text-success"></i>' : '<i class="bi bi-x-circle text-danger"></i>'}
                            </div>
                            <span class="mapping-arrow"><i class="bi bi-arrow-right"></i></span>
                            ${pptImageDataUrl ? `<img src="${pptImageDataUrl}" class="mapping-image-preview me-2" alt="PPT图片" style="width:60px;height:60px;object-fit:cover;border-radius:4px;border:1px solid #dee2e6;">` : '<div class="mapping-image-preview me-2 bg-light d-flex align-items-center justify-content-center" style="width:60px;height:60px;border-radius:4px;border:1px solid #dee2e6;"><i class="bi bi-image text-muted"></i></div>'}
                            <div class="mapping-info">
                                <div>
                                    <span class="badge ${this.getChainColor(mapping.chain)} me-1">${mapping.chain || 'N/A'}</span>
                                    <strong>${this.formatMetricName(mapping.metric)}</strong>
                                </div>
                                <small class="text-muted">${hasFile ? fileName : '未找到图片文件'}</small>
                            </div>
                        </div>
                        <div class="mapping-status">
                            ${statusIcon}
                            <small class="ms-1 text-muted">幻灯片 ${(mapping.slide_index || 0) + 1}</small>
                        </div>
                    </div>
                `;
            } else {
                // Sample-based mapping with visual preview
                const typeDisplay = this.IMAGE_TYPE_NAMES[mapping.image_type] || mapping.image_type || '图片';
                html += `
                    <div class="mapping-item-visual" onclick="PPTReplace.showMappingDetail(${idx})" title="点击查看详情">
                        <div class="d-flex align-items-center flex-grow-1">
                            <div class="mapping-image-preview me-2 bg-light d-flex align-items-center justify-content-center" style="width:60px;height:60px;border-radius:4px;border:1px solid #dee2e6;">
                                ${hasFile ? '<i class="bi bi-file-image text-success"></i>' : '<i class="bi bi-x-circle text-danger"></i>'}
                            </div>
                            <span class="mapping-arrow"><i class="bi bi-arrow-right"></i></span>
                            ${pptImageDataUrl ? `<img src="${pptImageDataUrl}" class="mapping-image-preview me-2" alt="PPT图片" style="width:60px;height:60px;object-fit:cover;border-radius:4px;border:1px solid #dee2e6;">` : '<div class="mapping-image-preview me-2 bg-light d-flex align-items-center justify-content-center" style="width:60px;height:60px;border-radius:4px;border:1px solid #dee2e6;"><i class="bi bi-image text-muted"></i></div>'}
                            <div class="mapping-info">
                                <div>
                                    <span class="badge bg-warning text-dark me-1">${mapping.sample_name || '未知'}</span>
                                    <strong>${typeDisplay}</strong>
                                </div>
                                <small class="text-muted">${hasFile ? fileName : '未找到图片文件'}</small>
                            </div>
                        </div>
                        <div class="mapping-status">
                            ${statusIcon}
                            <small class="ms-1 text-muted">幻灯片 ${(mapping.slide_index || 0) + 1}</small>
                        </div>
                    </div>
                `;
            }
        });

        list.innerHTML = html || '<p class="text-muted text-center">未找到匹配的图片</p>';
    },

    /**
     * Show detailed mapping preview in modal
     * @param {number} mappingIndex - Index of mapping to show
     */
    async showMappingDetail(mappingIndex) {
        if (!this.currentMappings || mappingIndex >= this.currentMappings.length) {
            console.error('Invalid mapping index or no mappings available');
            return;
        }

        const mapping = this.currentMappings[mappingIndex];
        console.log(`showMappingDetail: mapping index=${mappingIndex}`, mapping);

        const slideInfo = this.slideData.find(s => s.slide_index === mapping.slide_index);
        console.log(`showMappingDetail: slideInfo found=${!!slideInfo}, slide_index=${mapping.slide_index}`);

        // Fix issue #2: Correct mapping direction and ensure PPT images display
        // Left side (source): Image from folder (replacement image)
        // Right side (target): PPT slide image (current image in PPT)

        // Get PPT slide image (target - right side)
        let pptImageDataUrl = '';
        if (slideInfo && slideInfo.image_positions) {
            console.log(`showMappingDetail: image_positions count=${slideInfo.image_positions.length}`);

            if (mapping.metric) {
                // For sharing_analysis, match by metric name
                const matchingImage = slideInfo.image_positions.find(img => img.metric === mapping.metric);
                console.log(`showMappingDetail: Looking for metric=${mapping.metric}, found=${!!matchingImage}`);

                if (matchingImage) {
                    pptImageDataUrl = matchingImage.data_url || '';
                    console.log(`showMappingDetail: PPT image data_url length=${pptImageDataUrl.length}`);
                }
            }

            if (!pptImageDataUrl) {
                // Fallback to position index
                const posIndex = mapping.position_index || 0;
                console.log(`showMappingDetail: Fallback to position_index=${posIndex}`);

                if (slideInfo.image_positions[posIndex]) {
                    pptImageDataUrl = slideInfo.image_positions[posIndex].data_url || '';
                    console.log(`showMappingDetail: Fallback PPT image data_url length=${pptImageDataUrl.length}`);
                }
            }
        } else {
            console.warn(`showMappingDetail: No slideInfo or image_positions for slide_index=${mapping.slide_index}`);
        }

        const pptImageInfo = mapping.chain
            ? `${mapping.chain} - ${this.formatMetricName(mapping.metric)}`
            : `${mapping.sample_name || '样本'} - ${this.IMAGE_TYPE_NAMES[mapping.image_type] || mapping.image_type}`;

        // Load source image from file path (source - left side)
        let sourceImageDataUrl = '';
        const sourceImageInfo = mapping.image_path ? mapping.image_path.split(/[\\/]/).pop() : '未找到图片';

        if (mapping.image_path) {
            console.log(`showMappingDetail: Loading source image from ${mapping.image_path}`);
            sourceImageDataUrl = await this.loadImageFromPath(mapping.image_path);
            console.log(`showMappingDetail: Source image loaded, data_url length=${sourceImageDataUrl ? sourceImageDataUrl.length : 0}`);
        } else {
            console.warn('showMappingDetail: No image_path in mapping');
        }

        // Show modal with correct direction: Source (folder) → Target (PPT)
        console.log(`showMappingDetail: Showing modal - source=${!!sourceImageDataUrl}, ppt=${!!pptImageDataUrl}`);
        this.showMappingModal(sourceImageDataUrl, pptImageDataUrl, `替换图片: ${sourceImageInfo}`, `PPT原图: ${pptImageInfo}`);
    },

    showMappingPreview() {
        const card = document.getElementById('mappingCard');
        const list = document.getElementById('mappingList');
        const countBadge = document.getElementById('mappingCount');

        card.style.display = 'block';

        // Show expected mappings based on slide analysis
        const expectedMappings = [];
        this.slideData.forEach(slide => {
            const imageType = slide.image_type || 'sharing_analysis';

            if (imageType === 'sharing_analysis') {
                // Sharing Analysis - use metric-based mapping
                const metrics = this.getExpectedMetrics(slide);
                metrics.forEach((metric, idx) => {
                    if (idx < slide.image_count) {
                        expectedMappings.push({
                            type: 'sharing_analysis',
                            chain: slide.chain_type,
                            metric: metric,
                            slide_index: slide.slide_index
                        });
                    }
                });
            } else {
                // Sample-based pages (Network Plots, Isotype Upset, Tree Maps)
                const sampleNames = slide.sample_names || [];
                const imagePositions = slide.image_positions || [];

                imagePositions.forEach((img, idx) => {
                    const sampleName = sampleNames[idx] || img.sample_name || `样本 ${idx + 1}`;
                    expectedMappings.push({
                        type: imageType,
                        sample_name: sampleName,
                        slide_index: slide.slide_index
                    });
                });
            }
        });

        countBadge.textContent = `${expectedMappings.length} 个预期映射`;

        let html = '';
        expectedMappings.forEach(mapping => {
            if (mapping.type === 'sharing_analysis') {
                html += `
                    <div class="mapping-item">
                        <span class="badge ${this.getChainColor(mapping.chain)} me-2">${mapping.chain || 'N/A'}</span>
                        <span class="flex-grow-1">${this.formatMetricName(mapping.metric)}</span>
                        <span class="text-muted small">→ 幻灯片 ${mapping.slide_index + 1}</span>
                    </div>
                `;
            } else {
                const typeDisplay = this.IMAGE_TYPE_NAMES[mapping.type] || mapping.type;
                html += `
                    <div class="mapping-item">
                        <span class="badge bg-warning text-dark me-2">${mapping.sample_name}</span>
                        <span class="flex-grow-1">${typeDisplay}</span>
                        <span class="text-muted small">→ 幻灯片 ${mapping.slide_index + 1}</span>
                    </div>
                `;
            }
        });

        list.innerHTML = html || '<p class="text-muted text-center">无映射</p>';
    },

    getExpectedMetrics(slide) {
        // Based on the PPT template structure
        // Check if slide has expected_metrics from backend
        if (slide.expected_metrics && slide.expected_metrics.length > 0) {
            return slide.expected_metrics;
        }

        // Fallback based on metric_type
        // Slide 1 (expression_r2): Expression, R² Outer, R² Inner
        // Slide 2 (morisita_sorensen): Morisita-Horn, uCDR3, Sorensen
        if (slide.metric_type === 'expression_r2') {
            return ['expression', 'r2_outer', 'r2_inner'];
        } else if (slide.metric_type === 'morisita_sorensen') {
            return ['morisita_horn', 'ucdr3', 'sorensen'];
        }

        // Default based on slide_number_for_chain
        if (slide.slide_number_for_chain === 1) {
            return ['expression', 'r2_outer', 'r2_inner'];
        }
        return ['morisita_horn', 'ucdr3', 'sorensen'];
    },

    formatMetricName(metric) {
        const names = {
            'expression': 'Expression',
            'r2_inner': 'R² Inner',
            'r2_outer': 'R² Outer',
            'morisita_horn': 'Morisita-Horn',
            'ucdr3': 'uCDR3',
            'sorensen': 'Sorensen',
            // Legacy names for backward compatibility
            'expression_sharing': 'Expression',
            'cdr3_sharing': 'uCDR3'
        };
        return names[metric] || metric;
    },

    async replaceImages() {
        // Check if comparison mode is enabled
        if (this.comparisonMode.enabled) {
            return this.replaceWithComparison();
        }
        
        if (!this.sessionId || !this.imageSource) {
            this.showError('请先上传PPT并选择图片来源');
            return;
        }

        // Show progress
        document.getElementById('replaceProgress').style.display = 'block';
        document.getElementById('replaceBtn').disabled = true;

        try {
            // Build request data with proper format for backend
            const requestData = {
                session_id: this.sessionId,
                module: this.currentTab
            };

            // Add border configuration (Requirement 11.8)
            const borderConfig = this.getBorderConfig();
            if (borderConfig) {
                requestData.border_config = borderConfig;
                requestData.apply_borders = true;
            } else {
                requestData.apply_borders = false;
            }

            // Convert images to request payload by module type
            if (this.currentTab === 'sharing_analysis' && this.imageSource.images?.sharing_analysis) {
                requestData.heatmaps = this.imageSource.images.sharing_analysis;
            } else if (['network_plots', 'isotype_upset', 'tree_maps'].includes(this.currentTab)) {
                const moduleImages = this.currentLayoutConfig?.images || this.imageSource.images?.[this.currentTab] || {};
                requestData.sample_images = {
                    [this.currentTab]: moduleImages
                };
                requestData.layout_config = this.buildLayoutConfig();
            } else if (this.imageSource.sharing_analysis_dir) {
                requestData.heatmap_dir = this.imageSource.sharing_analysis_dir;
            } else if (this.imageSource.heatmap_dir) {
                requestData.heatmap_dir = this.imageSource.heatmap_dir;
            }

            // Include analysis_id if available
            if (this.imageSource.analysis_id) {
                requestData.analysis_id = this.imageSource.analysis_id;
            }

            console.log('Replace request data:', requestData);

            const response = await fetch('/api/ppt/replace', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });

            const data = await response.json();

            // Hide progress
            document.getElementById('replaceProgress').style.display = 'none';

            if (!data.success) {
                this.showError(data.error || '替换图片失败');
                document.getElementById('replaceBtn').disabled = false;
                return;
            }

            // Update module status (multi-module support)
            this.updateModuleStatus(this.currentTab, data.replaced_count, data.mappings || []);

            // Update step indicator
            this.setStep(3);

            // Show result with border statistics
            this.showResult(data);

            // Refresh PPT preview if available
            if (this.preview && typeof this.refreshPreview === 'function') {
                this.refreshPreview();
            }

        } catch (error) {
            console.error('Error replacing images:', error);
            document.getElementById('replaceProgress').style.display = 'none';
            document.getElementById('replaceBtn').disabled = false;
            this.showError('替换图片时发生错误');
        }
    },

    showResult(data) {
        const card = document.getElementById('resultCard');
        const message = document.getElementById('resultMessage');
        const downloadBtn = document.getElementById('downloadBtn');
        const downloadUrl = document.getElementById('downloadUrl');

        card.style.display = 'block';

        // Build result message with border statistics (Requirement 11.8)
        let messageText = `已成功替换 ${data.replaced_count} 张图片`;
        if (data.border_applied_count !== undefined) {
            messageText += `，应用边框 ${data.border_applied_count} 张`;
        }
        message.textContent = messageText;

        // Store download URL in hidden field
        if (downloadUrl) {
            downloadUrl.value = data.download_url;
        }

        // Save to operation history with deduplication check
        this.saveToHistory(data);

        // Update mapping list with actual results
        if (data.mappings && data.mappings.length > 0) {
            const list = document.getElementById('mappingList');
            const countBadge = document.getElementById('mappingCount');

            countBadge.textContent = `${data.mappings.length} 个映射`;
            countBadge.classList.remove('bg-success');
            countBadge.classList.add(data.replaced_count > 0 ? 'bg-success' : 'bg-warning');

            let html = '';
            data.mappings.forEach(mapping => {
                const statusIcon = mapping.has_file ?
                    '<i class="bi bi-check-circle text-success"></i>' :
                    '<i class="bi bi-x-circle text-danger"></i>';

                if (mapping.chain) {
                    // Sharing Analysis mapping
                    html += `
                        <div class="mapping-item">
                            <span class="badge ${this.getChainColor(mapping.chain)} me-2">${mapping.chain}</span>
                            <span class="flex-grow-1">${this.formatMetricName(mapping.metric)}</span>
                            <span class="me-2">${statusIcon}</span>
                            <span class="text-muted small">${mapping.image_file || mapping.heatmap_file || '未找到'}</span>
                        </div>
                    `;
                } else if (mapping.sample_name) {
                    // Sample-based mapping
                    html += `
                        <div class="mapping-item">
                            <span class="badge bg-warning me-2">${mapping.sample_name}</span>
                            <span class="flex-grow-1">${this.IMAGE_TYPE_NAMES[mapping.image_type] || mapping.image_type}</span>
                            <span class="me-2">${statusIcon}</span>
                            <span class="text-muted small">${mapping.image_file || '未找到'}</span>
                        </div>
                    `;
                }
            });
            list.innerHTML = html;
        }

        // Load PPT preview after replacement (Requirement 4)
        this.loadPreviewSlides();
    },

    setStep(stepNum) {
        for (let i = 1; i <= 3; i++) {
            const step = document.getElementById(`step${i}`);
            step.classList.remove('active', 'completed');
            if (i < stepNum) {
                step.classList.add('completed');
            } else if (i === stepNum) {
                step.classList.add('active');
            }
        }
    },

    /**
     * Clear PPT file and reset all states
     * Requirements: 9.7
     */
    clearPPT() {
        this.pptFile = null;
        this.sessionId = null;
        this.slideData = [];

        // Clear tab states
        this.clearTabStates();

        document.getElementById('pptUploadZone').classList.remove('has-file');
        document.getElementById('pptFileInfo').style.display = 'none';
        document.getElementById('pptFileInput').value = '';
        document.getElementById('slideAnalysisCard').style.display = 'none';
        document.getElementById('imageSourceCard').style.display = 'none';
        document.getElementById('borderConfigCard').style.display = 'none';  // Hide border config
        document.getElementById('mappingCard').style.display = 'none';
        document.getElementById('replaceCard').style.display = 'none';
        document.getElementById('resultCard').style.display = 'none';

        // Update tab badges (all should be 0)
        this.updateTabBadges();

        this.setStep(1);
    },

    showError(message) {
        // Use Bootstrap toast or alert
        const alertHtml = `
            <div class="alert alert-danger alert-dismissible fade show position-fixed" 
                 style="top: 20px; right: 20px; z-index: 9999;" role="alert">
                <i class="bi bi-exclamation-triangle"></i> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', alertHtml);

        // Auto dismiss after 5 seconds
        setTimeout(() => {
            const alert = document.querySelector('.alert-danger');
            if (alert) alert.remove();
        }, 5000);
    },

    showWarning(message) {
        // Use Bootstrap toast or alert for warning
        const alertHtml = `
            <div class="alert alert-warning alert-dismissible fade show position-fixed" 
                 style="top: 20px; right: 20px; z-index: 9999; max-width: 400px; white-space: pre-line;" role="alert">
                <i class="bi bi-exclamation-triangle"></i> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', alertHtml);

        // Auto dismiss after 10 seconds (longer for warnings)
        setTimeout(() => {
            const alert = document.querySelector('.alert-warning');
            if (alert) alert.remove();
        }, 10000);
    },

    showInfo(message) {
        // Use Bootstrap toast or alert for info
        const alertHtml = `
            <div class="alert alert-info alert-dismissible fade show position-fixed" 
                 style="top: 20px; right: 20px; z-index: 9999;" role="alert">
                <i class="bi bi-info-circle"></i> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', alertHtml);

        // Auto dismiss after 5 seconds
        setTimeout(() => {
            const alert = document.querySelector('.alert-info');
            if (alert) alert.remove();
        }, 5000);
    },

    showSuccess(message) {
        // Use Bootstrap toast or alert for success
        const alertHtml = `
            <div class="alert alert-success alert-dismissible fade show position-fixed" 
                 style="top: 20px; right: 20px; z-index: 9999;" role="alert">
                <i class="bi bi-check-circle"></i> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', alertHtml);

        // Auto dismiss after 5 seconds
        setTimeout(() => {
            const alert = document.querySelector('.alert-success');
            if (alert) alert.remove();
        }, 5000);
    },

    showError(message) {
        // Use Bootstrap toast or alert for error
        const alertHtml = `
            <div class="alert alert-danger alert-dismissible fade show position-fixed" 
                 style="top: 20px; right: 20px; z-index: 9999;" role="alert">
                <i class="bi bi-exclamation-circle"></i> ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', alertHtml);

        // Auto dismiss after 8 seconds (longer for errors)
        setTimeout(() => {
            const alert = document.querySelector('.alert-danger');
            if (alert) alert.remove();
        }, 8000);
    },

    /**
     * Save operation to history with deduplication
     * @param {Object} data - Replace operation result data
     */
    saveToHistory(data) {
        try {
            // Load existing history
            const historyStr = localStorage.getItem('pptReplace_history');
            this.operationHistory = historyStr ? JSON.parse(historyStr) : [];

            // Create operation hash for deduplication
            const hash = this.generateOperationHash();

            // Create operation record with full result data
            const record = {
                id: this.sessionId || `ppt_${Date.now()}`,
                timestamp: new Date().toISOString(),
                pptFileName: this.pptFile ? this.pptFile.name : 'unknown',
                imageDir: this.imageSource?.image_dir || this.imageSource?.heatmap_dir || '',
                analysisId: this.imageSource?.analysis_id || '',
                imageType: this.currentTab,
                replacedCount: data.replaced_count || 0,
                downloadUrl: data.download_url || '',
                hash: hash,
                // Store full result for viewing later
                result: {
                    mappings: data.mappings || [],
                    replaced_count: data.replaced_count || 0,
                    download_url: data.download_url || '',
                    summary: data.summary || ''
                }
            };

            // Check for duplicates based on hash and replaced count
            const existingIndex = this.operationHistory.findIndex(item =>
                item.hash === record.hash &&
                item.replacedCount === record.replacedCount &&
                item.imageType === record.imageType
            );

            if (existingIndex === -1) {
                // New operation - add to history
                this.operationHistory.unshift(record);

                // Limit history size
                if (this.operationHistory.length > this.maxHistoryItems) {
                    this.operationHistory = this.operationHistory.slice(0, this.maxHistoryItems);
                }

                localStorage.setItem('pptReplace_history', JSON.stringify(this.operationHistory));
                console.log('Operation saved to history');
            } else {
                // Update existing record with latest result
                this.operationHistory[existingIndex] = {
                    ...this.operationHistory[existingIndex],
                    timestamp: record.timestamp,
                    result: record.result,
                    downloadUrl: record.downloadUrl
                };
                localStorage.setItem('pptReplace_history', JSON.stringify(this.operationHistory));
                console.log('Existing operation updated in history');
            }
        } catch (error) {
            console.error('Failed to save to history:', error);
        }
    },

    /**
     * Generate a hash for the current operation for deduplication
     * @returns {string} Hash string
     */
    generateOperationHash() {
        const parts = [
            this.pptFile ? this.pptFile.name : '',
            this.imageSource?.image_dir || this.imageSource?.heatmap_dir || '',
            this.imageSource?.analysis_id || '',
            this.slideData.length.toString(),
            this.currentTab
        ];
        return btoa(parts.join('|')).substring(0, 32);
    },

    /**
     * Get operation history
     * @returns {Array} Operation history
     */
    getHistory() {
        try {
            const historyStr = localStorage.getItem('pptReplace_history');
            return historyStr ? JSON.parse(historyStr) : [];
        } catch (error) {
            console.error('Failed to load history:', error);
            return [];
        }
    },

    /**
     * Delete a specific history item
     * @param {string} recordId - ID of record to delete
     */
    deleteHistoryItem(recordId) {
        try {
            const history = this.getHistory();
            const filtered = history.filter(item => item.id !== recordId);
            localStorage.setItem('pptReplace_history', JSON.stringify(filtered));
            this.operationHistory = filtered;
            console.log(`History item ${recordId} deleted`);
            return true;
        } catch (error) {
            console.error('Failed to delete history item:', error);
            return false;
        }
    },

    /**
     * View saved result from history
     * @param {string} recordId - ID of record to view
     */
    viewHistoryResult(recordId) {
        try {
            const history = this.getHistory();
            const record = history.find(item => item.id === recordId);

            if (record && record.result) {
                // Show the stored result
                this.showHistoryResultModal(record);
                return true;
            } else {
                this.showError('未找到保存的结果');
                return false;
            }
        } catch (error) {
            console.error('Failed to view history result:', error);
            this.showError('查看结果失败');
            return false;
        }
    },

    /**
     * Show history result in a modal
     * @param {Object} record - History record
     */
    showHistoryResultModal(record) {
        const result = record.result;
        const mappings = result.mappings || [];

        let mappingsHtml = '';
        mappings.forEach(mapping => {
            const statusIcon = mapping.has_file
                ? '<i class="bi bi-check-circle text-success"></i>'
                : '<i class="bi bi-x-circle text-danger"></i>';

            if (mapping.chain) {
                mappingsHtml += `
                    <div class="d-flex align-items-center py-1 border-bottom">
                        <span class="badge ${this.getChainColor(mapping.chain)} me-2">${mapping.chain}</span>
                        <span class="flex-grow-1">${this.formatMetricName(mapping.metric)}</span>
                        <span class="me-2">${statusIcon}</span>
                        <small class="text-muted">${mapping.image_file || '未找到'}</small>
                    </div>
                `;
            } else if (mapping.sample_name) {
                mappingsHtml += `
                    <div class="d-flex align-items-center py-1 border-bottom">
                        <span class="badge bg-warning text-dark me-2">${mapping.sample_name}</span>
                        <span class="flex-grow-1">${this.IMAGE_TYPE_NAMES[mapping.image_type] || mapping.image_type}</span>
                        <span class="me-2">${statusIcon}</span>
                        <small class="text-muted">${mapping.image_file || '未找到'}</small>
                    </div>
                `;
            }
        });

        const modalHtml = `
            <div class="modal fade" id="historyResultModal" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="bi bi-clock-history"></i> 历史操作结果
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="mb-3">
                                <p class="mb-1"><strong>PPT文件:</strong> ${record.pptFileName}</p>
                                <p class="mb-1"><strong>图片来源:</strong> ${record.imageDir || record.analysisId || '未知'}</p>
                                <p class="mb-1"><strong>操作时间:</strong> ${new Date(record.timestamp).toLocaleString()}</p>
                                <p class="mb-0"><strong>替换数量:</strong> ${result.replaced_count} 张图片</p>
                            </div>
                            <hr>
                            <h6><i class="bi bi-link-45deg"></i> 图片映射 (${mappings.length}个)</h6>
                            <div style="max-height: 300px; overflow-y: auto;">
                                ${mappingsHtml || '<p class="text-muted">无映射记录</p>'}
                            </div>
                        </div>
                        <div class="modal-footer">
                            ${record.downloadUrl ? `
                                <a href="${record.downloadUrl}" class="btn btn-primary">
                                    <i class="bi bi-download"></i> 下载PPT
                                </a>
                            ` : ''}
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if any
        const existingModal = document.getElementById('historyResultModal');
        if (existingModal) existingModal.remove();

        document.body.insertAdjacentHTML('beforeend', modalHtml);
        const modal = new bootstrap.Modal(document.getElementById('historyResultModal'));
        modal.show();
    },

    /**
     * Clear operation history
     */
    clearHistory() {
        try {
            localStorage.removeItem('pptReplace_history');
            this.operationHistory = [];
            console.log('History cleared');
        } catch (error) {
            console.error('Failed to clear history:', error);
        }
    },

    /**
     * Show image preview from slide data (fixes issue #1: image zoom not working)
     * Uses data attributes instead of inline data URLs to avoid parsing issues
     * @param {HTMLElement} element - The clicked element with data attributes
     */
    showSlideImagePreview(element) {
        const slideIdx = parseInt(element.dataset.slideIdx);
        const imgIdx = parseInt(element.dataset.imgIdx);
        const imageInfo = element.dataset.imgInfo || '';

        const slide = this.slideData.find(s => s.slide_index === slideIdx);
        if (slide && slide.image_positions && slide.image_positions[imgIdx]) {
            const dataUrl = slide.image_positions[imgIdx].data_url;
            if (dataUrl) {
                this.showImagePreview(dataUrl, imageInfo);
            }
        }
    },

    /**
     * Show image preview - simple fullscreen overlay with enlarged image
     * @param {string} imageSrc - Image source URL or data URL
     * @param {string} imageInfo - Image description
     */
    showImagePreview(imageSrc, imageInfo = '') {
        // 移除已存在的覆盖层
        const existingOverlay = document.getElementById('simpleImageOverlay');
        if (existingOverlay) {
            existingOverlay.remove();
        }

        // 创建简单的全屏覆盖层
        const overlay = document.createElement('div');
        overlay.id = 'simpleImageOverlay';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.9);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            cursor: pointer;
        `;

        // 创建图片元素 - 尽可能放大
        const img = document.createElement('img');
        img.src = imageSrc;
        img.alt = imageInfo || '图片预览';
        img.style.cssText = `
            max-width: 95vw;
            max-height: 95vh;
            width: auto;
            height: auto;
            object-fit: contain;
            border-radius: 4px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
        `;

        // 如果有图片信息，添加标签
        if (imageInfo) {
            const infoLabel = document.createElement('div');
            infoLabel.textContent = imageInfo;
            infoLabel.style.cssText = `
                position: absolute;
                bottom: 15px;
                left: 50%;
                transform: translateX(-50%);
                color: white;
                background: rgba(0, 0, 0, 0.6);
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 13px;
            `;
            overlay.appendChild(infoLabel);
        }

        overlay.appendChild(img);

        // 点击关闭
        overlay.addEventListener('click', () => {
            overlay.remove();
        });

        // ESC键关闭
        const handleEsc = (e) => {
            if (e.key === 'Escape') {
                overlay.remove();
                document.removeEventListener('keydown', handleEsc);
            }
        };
        document.addEventListener('keydown', handleEsc);

        document.body.appendChild(overlay);
    },

    /**
     * Show mapping preview modal with source and target images
     * @param {string} sourceSrc - Source image URL
     * @param {string} targetSrc - Target image URL  
     * @param {string} sourceInfo - Source image info
     * @param {string} targetInfo - Target image info
     */
    showMappingModal(sourceSrc, targetSrc, sourceInfo = '', targetInfo = '') {
        const modal = document.getElementById('mappingPreviewModal');
        const sourceImage = document.getElementById('mappingSourceImage');
        const targetImage = document.getElementById('mappingTargetImage');
        const sourceInfoEl = document.getElementById('mappingSourceInfo');
        const targetInfoEl = document.getElementById('mappingTargetInfo');

        if (!modal) {
            console.error('mappingPreviewModal not found');
            return;
        }

        // Handle source image
        if (sourceImage) {
            if (sourceSrc) {
                sourceImage.src = sourceSrc;
                sourceImage.style.display = 'block';
                sourceImage.onerror = () => {
                    console.error('Failed to load source image');
                    sourceImage.style.display = 'none';
                };
            } else {
                sourceImage.style.display = 'none';
                console.warn('No source image provided');
            }
        }

        // Handle target (PPT) image
        if (targetImage) {
            if (targetSrc) {
                targetImage.src = targetSrc;
                targetImage.style.display = 'block';
                targetImage.onerror = () => {
                    console.error('Failed to load target PPT image');
                    targetImage.style.display = 'none';
                };
            } else {
                targetImage.style.display = 'none';
                console.warn('No target PPT image provided - data_url may be missing');
            }
        }

        if (sourceInfoEl) sourceInfoEl.textContent = sourceInfo;
        if (targetInfoEl) targetInfoEl.textContent = targetInfo;

        console.log(`showMappingModal: source=${!!sourceSrc}, target=${!!targetSrc}`);
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    },

    /**
     * Load image from file path via API and return data URL
     * @param {string} filePath - File path to load
     * @returns {Promise<string>} Data URL
     */
    async loadImageFromPath(filePath) {
        try {
            const response = await fetch('/api/ppt/load-image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: filePath })
            });
            const data = await response.json();
            if (data.success && data.data_url) {
                return data.data_url;
            }
            return null;
        } catch (error) {
            console.error('Failed to load image:', error);
            return null;
        }
    },

    /**
     * Load source image thumbnail and update the preview element
     * @param {string} imagePath - Path to the source image
     * @param {string} elementId - ID of the element to update
     */
    async loadSourceImageThumbnail(imagePath, elementId) {
        const element = document.getElementById(elementId);
        if (!element) return;

        try {
            const dataUrl = await this.loadImageFromPath(imagePath);
            if (dataUrl) {
                // Replace the icon with the actual image
                element.innerHTML = `<img src="${dataUrl}" alt="源图片" style="width:100%;height:100%;object-fit:cover;border-radius:4px;">`;
            } else {
                // Show error icon if loading fails
                element.innerHTML = '<i class="bi bi-exclamation-triangle text-warning"></i>';
            }
        } catch (error) {
            console.error(`Failed to load thumbnail for ${imagePath}:`, error);
            element.innerHTML = '<i class="bi bi-exclamation-triangle text-warning"></i>';
        }
    }
};

// Backward compatibility alias
const PPTHeatmap = PPTReplace;

// PPT Preview Methods (Requirement 4, 5)
Object.assign(PPTReplace, {
    /**
     * Load PPT slides for preview
     * Requirements: Req 4
     */
    async loadPreviewSlides() {
        if (!this.sessionId) {
            console.log('No session ID, cannot load preview');
            return;
        }

        this.preview.isLoading = true;
        this.renderPreviewLoading();

        try {
            const response = await fetch('/api/ppt/render-slides', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: this.sessionId,
                    max_size: 800
                })
            });

            const data = await response.json();

            if (data.success) {
                this.preview.slides = data.slides || [];
                this.preview.currentSlide = 0;
                this.renderPreviewPanel();
            } else {
                console.error('Failed to load preview:', data.error);
                this.renderPreviewError(data.error);
            }
        } catch (error) {
            console.error('Error loading preview:', error);
            this.renderPreviewError('加载预览失败');
        } finally {
            this.preview.isLoading = false;
        }
    },

    /**
     * Refresh PPT preview after replacement
     * Requirements: Req 4
     */
    async refreshPreview() {
        await this.loadPreviewSlides();
    },

    /**
     * Render preview loading state
     */
    renderPreviewLoading() {
        const container = document.getElementById('pptPreviewPanel');
        if (!container) return;

        container.innerHTML = `
            <div class="card-header d-flex justify-content-between align-items-center py-2">
                <h6 class="mb-0"><i class="bi bi-file-earmark-slides"></i> PPT预览</h6>
            </div>
            <div class="card-body text-center py-4">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">加载中...</span>
                </div>
                <p class="text-muted mt-2">正在加载预览...</p>
            </div>
        `;
        container.style.display = 'block';
    },

    /**
     * Render preview error state
     */
    renderPreviewError(message) {
        const container = document.getElementById('pptPreviewPanel');
        if (!container) return;

        container.innerHTML = `
            <div class="card-header d-flex justify-content-between align-items-center py-2">
                <h6 class="mb-0"><i class="bi bi-file-earmark-slides"></i> PPT预览</h6>
            </div>
            <div class="card-body text-center py-4">
                <i class="bi bi-exclamation-triangle text-warning fs-1"></i>
                <p class="text-muted mt-2">${message}</p>
                <button class="btn btn-sm btn-outline-primary" onclick="PPTReplace.loadPreviewSlides()">
                    <i class="bi bi-arrow-clockwise"></i> 重试
                </button>
            </div>
        `;
    },

    /**
     * Render preview panel with thumbnails
     * Requirements: Req 4, 5
     */
    renderPreviewPanel() {
        const container = document.getElementById('pptPreviewPanel');
        if (!container) return;

        const slides = this.preview.slides;
        const currentSlide = this.preview.currentSlide;

        let thumbnailsHtml = '';
        slides.forEach((slide, idx) => {
            const isActive = idx === currentSlide;
            const hasImages = slide.has_images;
            const statusIcon = hasImages ? '<i class="bi bi-check-circle-fill text-success position-absolute" style="bottom: 2px; right: 2px; font-size: 0.7rem;"></i>' : '';

            thumbnailsHtml += `
                <div class="preview-thumbnail ${isActive ? 'active' : ''}" 
                     onclick="PPTReplace.showPreviewSlide(${idx})"
                     title="${slide.title || 'Slide ' + (idx + 1)}">
                    <div class="thumbnail-container position-relative">
                        ${slide.data_url
                    ? `<img src="${slide.data_url}" alt="Slide ${idx + 1}">`
                    : `<div class="thumbnail-placeholder"><span>${idx + 1}</span></div>`
                }
                        ${statusIcon}
                    </div>
                    <small class="thumbnail-label">${idx + 1}</small>
                </div>
            `;
        });

        const currentSlideData = slides[currentSlide] || {};

        container.innerHTML = `
            <div class="card-header d-flex justify-content-between align-items-center py-2">
                <h6 class="mb-0"><i class="bi bi-file-earmark-slides"></i> PPT预览</h6>
                <div>
                    <button class="btn btn-sm btn-outline-secondary me-1" onclick="PPTReplace.refreshPreview()" title="刷新预览">
                        <i class="bi bi-arrow-clockwise"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-secondary" onclick="PPTReplace.togglePreviewFullscreen()" title="全屏">
                        <i class="bi bi-arrows-fullscreen"></i>
                    </button>
                </div>
            </div>
            <div class="card-body p-2">
                <!-- Thumbnails row -->
                <div class="preview-thumbnails-container mb-2">
                    <div class="preview-thumbnails d-flex overflow-auto pb-2">
                        ${thumbnailsHtml}
                    </div>
                </div>
                
                <!-- Current slide preview -->
                <div class="current-slide-preview text-center">
                    ${currentSlideData.data_url
                ? `<img src="${currentSlideData.data_url}" class="img-fluid rounded" style="max-height: 300px;" alt="Current slide">`
                : `<div class="no-preview-placeholder py-4">
                            <i class="bi bi-image text-muted fs-1"></i>
                            <p class="text-muted">无预览图片</p>
                           </div>`
            }
                </div>
                
                <!-- Navigation -->
                <div class="preview-navigation d-flex justify-content-between align-items-center mt-2">
                    <button class="btn btn-sm btn-outline-secondary" onclick="PPTReplace.navigatePreview(-1)" ${currentSlide === 0 ? 'disabled' : ''}>
                        <i class="bi bi-chevron-left"></i> 上一张
                    </button>
                    <span class="text-muted">${currentSlide + 1} / ${slides.length}</span>
                    <button class="btn btn-sm btn-outline-secondary" onclick="PPTReplace.navigatePreview(1)" ${currentSlide >= slides.length - 1 ? 'disabled' : ''}>
                        下一张 <i class="bi bi-chevron-right"></i>
                    </button>
                </div>
            </div>
        `;
        container.style.display = 'block';

        // Scroll active thumbnail into view
        setTimeout(() => {
            const activeThumbnail = container.querySelector('.preview-thumbnail.active');
            if (activeThumbnail) {
                activeThumbnail.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
            }
        }, 100);
    },

    /**
     * Show specific slide in preview
     * Requirements: Req 5
     */
    showPreviewSlide(index) {
        if (index >= 0 && index < this.preview.slides.length) {
            this.preview.currentSlide = index;
            this.renderPreviewPanel();
        }
    },

    /**
     * Navigate preview slides
     * Requirements: Req 5
     */
    navigatePreview(direction) {
        const newIndex = this.preview.currentSlide + direction;
        this.showPreviewSlide(newIndex);
    },

    /**
     * Toggle fullscreen preview
     * Requirements: Req 5
     */
    togglePreviewFullscreen() {
        const currentSlideData = this.preview.slides[this.preview.currentSlide];
        if (currentSlideData && currentSlideData.data_url) {
            this.showImagePreview(currentSlideData.data_url, currentSlideData.title || `Slide ${this.preview.currentSlide + 1}`);
        }
    },

    /**
     * Handle keyboard navigation for preview
     * Requirements: Req 5
     */
    handlePreviewKeyboard(event) {
        if (event.key === 'ArrowLeft') {
            this.navigatePreview(-1);
        } else if (event.key === 'ArrowRight') {
            this.navigatePreview(1);
        }
    },

    // ==================== Download Enhancement (Requirement 7) ====================

    /**
     * Show download summary dialog
     * Requirements: Req 7
     */
    showDownloadSummary() {
        const modal = document.getElementById('downloadSummaryModal');
        if (!modal) {
            // Fallback to direct download if modal not found
            this.downloadPPT();
            return;
        }

        // Render summary content
        this.renderDownloadSummaryContent();

        // Update filename preview
        this.updateFilenamePreview();

        // Bind events
        this.bindDownloadDialogEvents();

        // Show modal
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    },

    /**
     * Render download summary content
     * Requirements: Req 7
     */
    renderDownloadSummaryContent() {
        const container = document.getElementById('downloadSummaryContent');
        if (!container) return;

        const progress = this.getModulesProgress();
        const history = this.session.replacementHistory;

        let html = `
            <div class="summary-stats d-flex justify-content-around text-center mb-3">
                <div>
                    <div class="fs-4 fw-bold text-primary">${this.session.totalReplaced}</div>
                    <small class="text-muted">总替换图片</small>
                </div>
                <div>
                    <div class="fs-4 fw-bold text-success">${progress.completed}</div>
                    <small class="text-muted">已完成模块</small>
                </div>
                <div>
                    <div class="fs-4 fw-bold text-info">${progress.total}</div>
                    <small class="text-muted">总模块数</small>
                </div>
            </div>
        `;

        // Module details
        html += '<div class="module-details small">';
        Object.entries(this.session.moduleStatus).forEach(([module, status]) => {
            const displayName = this.IMAGE_TYPE_NAMES[module] || module;
            const statusIcon = status.replaced
                ? '<i class="bi bi-check-circle-fill text-success"></i>'
                : '<i class="bi bi-circle text-muted"></i>';
            const statusText = status.replaced
                ? `${status.count} 张`
                : '未替换';

            html += `
                <div class="d-flex align-items-center py-1">
                    <span class="me-2">${statusIcon}</span>
                    <span class="flex-grow-1">${displayName}</span>
                    <span class="badge ${status.replaced ? 'bg-success' : 'bg-secondary'}">${statusText}</span>
                </div>
            `;
        });
        html += '</div>';

        container.innerHTML = html;
    },

    /**
     * Update filename preview based on options
     * Requirements: Req 7
     */
    updateFilenamePreview() {
        const preview = document.getElementById('filenamePreview');
        if (!preview) return;

        const filename = this.generateDownloadFilename();
        preview.textContent = filename;
    },

    /**
     * Generate download filename with metadata
     * Requirements: Req 7
     * Format: {original_name}_replaced_{modules}_{timestamp}.pptx
     */
    generateDownloadFilename() {
        // Get original filename
        let baseName = 'presentation';
        if (this.pptFile && this.pptFile.name) {
            baseName = this.pptFile.name.replace(/\.pptx?$/i, '');
        }

        // Get replaced modules
        const replacedModules = Object.entries(this.session.moduleStatus)
            .filter(([_, status]) => status.replaced)
            .map(([module, _]) => this.getModuleShortName(module));

        const modulesStr = replacedModules.length > 0
            ? replacedModules.join('+')
            : 'none';

        // Check if timestamp should be included
        const includeTimestamp = document.getElementById('includeTimestampCheck')?.checked ?? true;

        let filename = `${baseName}_replaced_${modulesStr}`;

        if (includeTimestamp) {
            const timestamp = this.formatFilenameTimestamp(new Date());
            filename += `_${timestamp}`;
        }

        return `${filename}.pptx`;
    },

    /**
     * Get short name for module
     * @param {string} module - Module name
     * @returns {string} Short name
     */
    getModuleShortName(module) {
        const shortNames = {
            'sharing_analysis': 'SA',
            'network_plots': 'NP',
            'isotype_upset': 'IU',
            'tree_maps': 'TM'
        };
        return shortNames[module] || module.substring(0, 2).toUpperCase();
    },

    /**
     * Format timestamp for filename
     * @param {Date} date - Date object
     * @returns {string} Formatted timestamp (YYYYMMDD_HHmm)
     */
    formatFilenameTimestamp(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}${month}${day}_${hours}${minutes}`;
    },

    /**
     * Bind events for download dialog
     * Requirements: Req 7
     */
    bindDownloadDialogEvents() {
        // Update filename preview when options change
        const timestampCheck = document.getElementById('includeTimestampCheck');
        if (timestampCheck) {
            timestampCheck.onchange = () => this.updateFilenamePreview();
        }

        // Confirm download button
        const confirmBtn = document.getElementById('confirmDownloadBtn');
        if (confirmBtn) {
            confirmBtn.onclick = () => this.confirmDownload();
        }
    },

    /**
     * Confirm and execute download
     * Requirements: Req 7
     */
    async confirmDownload() {
        const addSummarySlide = document.getElementById('addSummarySlideCheck')?.checked ?? false;
        const customFilename = this.generateDownloadFilename();

        // Close modal
        const modal = bootstrap.Modal.getInstance(document.getElementById('downloadSummaryModal'));
        if (modal) modal.hide();

        // Show loading
        this.showInfo('正在准备下载...');

        try {
            if (addSummarySlide) {
                // Call API to add summary slide and download
                await this.downloadWithSummarySlide(customFilename);
            } else {
                // Direct download with custom filename
                await this.downloadPPT(customFilename);
            }
        } catch (error) {
            console.error('Download error:', error);
            this.showError('下载失败: ' + error.message);
        }
    },

    /**
     * Download PPT with optional custom filename
     * Requirements: Req 7
     * @param {string} customFilename - Optional custom filename
     */
    async downloadPPT(customFilename = null) {
        const downloadUrl = document.getElementById('downloadUrl')?.value;
        if (!downloadUrl) {
            this.showError('下载链接不可用');
            return;
        }

        try {
            const response = await fetch(downloadUrl);
            if (!response.ok) {
                throw new Error('下载失败');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = customFilename || this.generateDownloadFilename();
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            this.showSuccess('PPT下载成功');
        } catch (error) {
            console.error('Download error:', error);
            throw error;
        }
    },

    /**
     * Download PPT with summary slide added
     * Requirements: Req 7
     * @param {string} customFilename - Custom filename
     */
    async downloadWithSummarySlide(customFilename) {
        if (!this.sessionId) {
            throw new Error('会话ID不可用');
        }

        // Prepare summary data
        const summaryData = {
            session_id: this.sessionId,
            filename: customFilename,
            summary: {
                total_replaced: this.session.totalReplaced,
                modules: Object.entries(this.session.moduleStatus).map(([module, status]) => ({
                    name: this.IMAGE_TYPE_NAMES[module] || module,
                    replaced: status.replaced,
                    count: status.count,
                    timestamp: status.timestamp
                })),
                generated_at: new Date().toISOString()
            }
        };

        try {
            const response = await fetch('/api/ppt/download-with-summary', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(summaryData)
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || '添加摘要页失败');
            }

            // Download the file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = customFilename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            this.showSuccess('PPT下载成功（含摘要页）');
        } catch (error) {
            console.error('Download with summary error:', error);
            // Fallback to regular download
            console.log('Falling back to regular download');
            await this.downloadPPT(customFilename);
        }
    }
});

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    PPTReplace.init();

    // Add keyboard listener for preview navigation
    document.addEventListener('keydown', (e) => {
        // Only handle if preview panel is visible
        const previewPanel = document.getElementById('pptPreviewPanel');
        if (previewPanel && previewPanel.style.display !== 'none') {
            PPTReplace.handlePreviewKeyboard(e);
        }
    });
});
