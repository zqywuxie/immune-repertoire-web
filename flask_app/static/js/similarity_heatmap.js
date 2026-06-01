/**
 * Auto Heatmap Analysis Module
 * Handles folder scanning, file selection, field mapping, sample renaming/grouping, and heatmap generation
 */
const AutoHeatmap = {
    basePath: '',
    scanResult: null,
    selectedFileType: null,
    selectedFilePath: null,
    selectedChains: [],
    isChainMode: false,
    fileColumns: [],
    fieldMapping: {
        cdr3_column: '',
        copy_column: ''
    },
    samples: [],           // All detected samples
    selectedSamples: new Set(),  // Selected sample display names
    groups: [],            // User-defined groups
    currentStep: 1,
    heatmapResult: null,
    currentMetric: 'expression_sharing',  // Current selected metric
    currentDataType: 'original',  // 'original' or 'grouped'
    heatmapReportConfigKey: 'auto_heatmap_web_report_config_v1',
    currentPlotType: 'heatmap',
    draggedSampleIndex: null,
    projectContext: null,

    // Metric display names
    METRIC_NAMES: {
        'expression_sharing': 'Expression Sharing',
        'morisita_horn': 'Morisita-Horn Index',
        'cdr3_sharing': 'Unique CDR3 Sharing',
        'r2_inner': 'R² Inner',
        'r2_outer': 'R² Outer',
        'sorensen': 'Sorensen-Dice Index'
    },

    init() {
        if (typeof DirectoryBrowser !== 'undefined') {
            window._heatmapBrowser = DirectoryBrowser.init({
                container: '#heatmapDirBrowser',
                fileFilter: 'csv,tsv,csv.gz',
                allowFileSelect: false,
                multiSelect: false,
                defaultPath: '/data',
                onSelect: (path, type) => AutoHeatmap.onBrowserSelect(path, type),
            });
            window._heatmapBrowser.build();
            window._heatmapBrowser.goTo('/data');
        }

        this.initDragAndDrop();
        this.initMetricTabs();
        this.loadHeatmapReportConfig();

        this.initializeFromProjectContext();
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey && e.key === 'a') {
                const activeElement = document.activeElement;
                if (activeElement.tagName !== 'INPUT' && activeElement.tagName !== 'TEXTAREA') {
                    e.preventDefault();
                    this.toggleAllSamples();
                }
            }
        });
    },

    onBrowserSelect(path, type) {
        document.getElementById('basePath').value = path;
    },

    getProjectContext() {
        if (this.projectContext) return this.projectContext;
        const params = new URLSearchParams(window.location.search);
        this.projectContext = {
            projectId: params.get('project_id') || '',
            projectName: params.get('project_name') || '',
            basePath: params.get('base_path') || '',
            autoScan: params.get('auto_scan') === '1'
        };
        return this.projectContext;
    },

    initializeFromProjectContext() {
        const context = this.getProjectContext();
        if (!context.projectId) return;

        const container = document.querySelector('.container-fluid.py-4');
        if (container) {
            const banner = document.createElement('div');
            banner.className = 'alert alert-primary d-flex justify-content-between align-items-center gap-3';
            banner.innerHTML = `
                <div>
                    <div class="fw-semibold">项目桥接已启用</div>
                    <div class="small">当前项目：${this.escapeHtml(context.projectName || context.projectId)}。页面会直接使用项目数据目录。</div>
                </div>
                <a class="btn btn-sm btn-outline-primary" href="/projects/${encodeURIComponent(context.projectId)}">返回项目详情</a>
            `;
            container.insertBefore(banner, container.firstChild);
        }

        const basePathInput = document.getElementById('basePath');
        if (basePathInput && context.basePath) {
            basePathInput.value = context.basePath;
        }
        if (context.autoScan && context.basePath) {
            this.scanFolder();
        }
    },

    escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    },

    async registerProjectResult(payload) {
        const context = this.getProjectContext();
        if (!context.projectId) return;
        try {
            await fetch(`/api/projects/${encodeURIComponent(context.projectId)}/analysis/similarity-heatmap/register-result`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch (error) {
            console.warn('Failed to register similarity heatmap result for project:', error);
        }
    },

    loadHeatmapReportConfig() {
        const defaults = {
            output_name: '',
            embed_images: false
        };

        let config = { ...defaults };
        try {
            const raw = localStorage.getItem(this.heatmapReportConfigKey);
            if (raw) {
                const parsed = JSON.parse(raw);
                config = { ...defaults, ...parsed };
            }
        } catch (error) {
            console.warn('Failed to load heatmap report config from localStorage:', error);
        }

        const outputNameInput = document.getElementById('heatmapReportOutputName');
        const embedImagesInput = document.getElementById('heatmapReportEmbedImages');

        if (outputNameInput) outputNameInput.value = config.output_name || '';
        if (embedImagesInput) embedImagesInput.checked = Boolean(config.embed_images);
    },

    saveHeatmapReportConfig(config) {
        try {
            localStorage.setItem(this.heatmapReportConfigKey, JSON.stringify({
                output_name: config.output_name,
                embed_images: config.embed_images
            }));
        } catch (error) {
            console.warn('Failed to save heatmap report config to localStorage:', error);
        }
    },

    getHeatmapReportConfigFromForm() {
        const reportOutputName = document.getElementById('heatmapReportOutputName');
        const reportEmbedImages = document.getElementById('heatmapReportEmbedImages');

        return {
            output_name: (reportOutputName?.value || '').trim(),
            embed_images: reportEmbedImages ? reportEmbedImages.checked : false
        };
    },

    getSelectedSamplesPayload() {
        return this.samples
            .filter(s => this.selectedSamples.has(s.display_name))
            .map(s => ({
                original_name: s.original_name,
                display_name: s.display_name,
                folder_path: s.folder_path,
                data_files: s.data_files.map(f => ({
                    filename: f.filename,
                    filepath: f.filepath,
                    size: f.size,
                    rows: f.rows,
                    columns: f.columns
                }))
            }));
    },

    buildCDR3ExportRequestData() {
        return {
            samples: this.getSelectedSamplesPayload(),
            file_pattern: this.isChainMode ? null : this.selectedFileType,
            selected_chains: this.isChainMode ? this.selectedChains : null,
            field_mapping: this.fieldMapping,
            top_n: 100
        };
    },

    buildHeatmapReportPayload(config = {}, extraPayload = {}) {
        return {
            heatmap_result: this.heatmapResult,
            output_name: config.output_name || null,
            embed_images: Boolean(config.embed_images),
            report_context: {
                source: 'similarity_heatmap',
                base_path: this.basePath || null,
                selected_samples: this.samples
                    .filter(s => this.selectedSamples.has(s.display_name))
                    .map(s => s.display_name),
                selected_chains: this.isChainMode ? this.selectedChains : null,
                generated_at: new Date().toISOString()
            },
            cdr3_export_request: this.buildCDR3ExportRequestData(),
            ...extraPayload
        };
    },

    getSelectedPlotType() {
        return document.getElementById('plotType')?.value || 'heatmap';
    },

    getPlotFileSuffix() {
        return this.currentPlotType || this.getSelectedPlotType() || 'heatmap';
    },

    filenameMatchesChain(filename, chain) {
        const nameWithoutExt = filename.replace(/\.(csv|tsv|txt)(\.gz)?$/i, '');
        const normalizedName = nameWithoutExt.toUpperCase();
        const normalizedChain = String(chain || '').toUpperCase();
        return normalizedName.endsWith(`__${normalizedChain}`) || normalizedName.endsWith(`_${normalizedChain}`);
    },

    initMetricTabs() {
        // Setup original metric tab click handlers
        document.querySelectorAll('#originalMetricTabs .nav-link').forEach(tab => {
            tab.addEventListener('click', (e) => {
                document.querySelectorAll('#originalMetricTabs .nav-link').forEach(t => t.classList.remove('active'));
                e.target.classList.add('active');
                this.currentMetric = e.target.dataset.metric;
                this.updateOriginalHeatmapDisplay();
            });
        });

        // Setup grouped metric tab click handlers
        document.querySelectorAll('#groupedMetricTabs .nav-link').forEach(tab => {
            tab.addEventListener('click', (e) => {
                document.querySelectorAll('#groupedMetricTabs .nav-link').forEach(t => t.classList.remove('active'));
                e.target.classList.add('active');
                this.currentMetric = e.target.dataset.metric;
                this.updateGroupedHeatmapDisplay();
            });
        });
    },

    updateStepIndicator(step) {
        this.currentStep = step;
        document.querySelectorAll('.step-item').forEach((item, index) => {
            const stepNum = index + 1;
            item.classList.remove('active', 'completed');
            if (stepNum < step) item.classList.add('completed');
            else if (stepNum === step) item.classList.add('active');
        });
    },

    showLoading(text = '正在处理...') {
        document.getElementById('loadingText').textContent = text;
        document.getElementById('loadingOverlay').style.display = 'flex';
    },

    hideLoading() {
        document.getElementById('loadingOverlay').style.display = 'none';
    },

    showError(message) {
        alert(message);
    },

    // Folder browser support
    browseFolder() {
        document.getElementById('folderInput').click();
    },

    onFolderSelected(event) {
        const files = event.target.files;
        if (files.length > 0) {
            // Extract the common parent path from selected files
            // Note: Due to browser security, we can only get relative paths
            const firstPath = files[0].webkitRelativePath || files[0].name;
            const folderName = firstPath.split('/')[0];

            // Show message that folder selection has browser limitations
            alert(`已选择文件夹: ${folderName}\n\n注意：由于浏览器安全限制，无法直接获取完整路径。\n请在输入框中手动输入完整路径，或复制粘贴文件夹路径。`);
        }
    },

    // Step 1: Scan folder
    async scanFolder() {
        const basePath = document.getElementById('basePath').value.trim();
        if (!basePath) {
            this.showError('请输入文件夹路径');
            return;
        }

        this.showLoading('正在扫描文件夹...');
        try {
            const response = await fetch('/api/auto-heatmap/scan-folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ base_path: basePath })
            });
            const data = await response.json();

            if (!data.success) throw new Error(data.message || '扫描失败');

            this.basePath = basePath;
            this.scanResult = data;
            this.samples = data.samples.map(s => ({
                ...s,
                selected: true  // Default select all
            }));

            // Update UI
            document.getElementById('scanSummary').style.display = 'block';
            document.getElementById('scanSummaryText').textContent = data.summary;

            if (data.samples.length === 0) {
                // No samples found - show warning
                document.getElementById('scanSummary').className = 'alert alert-warning mt-3';
            } else {
                document.getElementById('scanSummary').className = 'alert alert-success mt-3';

                // 根据是否检测到链后缀决定显示模式
                if (data.has_chain_suffix && data.all_chains && data.all_chains.length > 0) {
                    // 显示链选择模式
                    this.renderChainSelection(data.all_chains);
                } else {
                    // 显示传统文件类型选择模式
                    this.renderFileTypes(data.all_file_types);
                }

                document.getElementById('step2Card').style.display = 'block';
                this.updateStepIndicator(2);

                // Hide field mapping section until file type is selected
                document.getElementById('fieldMappingSection').style.display = 'none';

                // Scroll to next step
                document.getElementById('step2Card').scrollIntoView({ behavior: 'smooth', block: 'start' });
            }

        } catch (error) {
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    },

    // Step 2: Render chain selection (for chain-suffixed files)
    renderChainSelection(chains) {
        const container = document.getElementById('fileTypeList');
        container.innerHTML = '';

        // 添加说明文字 - 更紧凑的样式
        const header = document.createElement('div');
        header.className = 'mb-2';
        header.innerHTML = '<small class="text-muted"><i class="bi bi-info-circle me-1"></i>检测到链类型文件，请选择要分析的链（可多选）</small>';
        container.appendChild(header);

        // 使用网格布局使界面更紧凑
        const gridContainer = document.createElement('div');
        gridContainer.className = 'row g-2 mb-3';

        chains.forEach((chain, index) => {
            const count = this.countSamplesWithChain(chain);
            const col = document.createElement('div');
            col.className = 'col-6 col-md-4 col-lg-3';

            const item = document.createElement('div');
            item.className = 'file-type-item selected';
            item.style.padding = '8px 12px';
            item.innerHTML = `
                <input type="checkbox" name="chainType" value="${chain}" id="chain_${index}" checked>
                <div>
                    <div class="fw-medium">${chain}</div>
                    <small class="text-muted">${count} 个样本</small>
                </div>
            `;

            item.addEventListener('click', (e) => {
                if (e.target.tagName !== 'INPUT') {
                    const checkbox = item.querySelector('input');
                    checkbox.checked = !checkbox.checked;
                }

                // 更新选中状态样式
                if (item.querySelector('input').checked) {
                    item.classList.add('selected');
                } else {
                    item.classList.remove('selected');
                }

                this.updateChainSelection();
            });

            col.appendChild(item);
            gridContainer.appendChild(col);
        });

        container.appendChild(gridContainer);

        // 添加操作按钮组 - 更紧凑
        const buttonGroup = document.createElement('div');
        buttonGroup.className = 'd-flex gap-2 align-items-center';
        buttonGroup.innerHTML = `
            <button class="btn btn-sm btn-outline-secondary" onclick="AutoHeatmap.selectAllChains()">
                <i class="bi bi-check-all me-1"></i>全选
            </button>
            <button class="btn btn-sm btn-outline-secondary" onclick="AutoHeatmap.deselectAllChains()">
                <i class="bi bi-x-circle me-1"></i>清空
            </button>
            <div class="ms-auto">
                <button class="btn btn-primary" onclick="AutoHeatmap.confirmChainSelection()">
                    确认选择 <i class="bi bi-arrow-right ms-1"></i>
                </button>
            </div>
        `;
        container.appendChild(buttonGroup);

        // 自动选择所有链
        this.selectedChains = [...chains];
    },

    selectAllChains() {
        document.querySelectorAll('.file-type-item input[type="checkbox"]').forEach(cb => {
            cb.checked = true;
            cb.closest('.file-type-item').classList.add('selected');
        });
        this.updateChainSelection();
    },

    deselectAllChains() {
        document.querySelectorAll('.file-type-item input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
            cb.closest('.file-type-item').classList.remove('selected');
        });
        this.updateChainSelection();
    },

    countSamplesWithChain(chain) {
        return this.samples.filter(s =>
            s.data_files.some(f => this.filenameMatchesChain(f.filename, chain))
        ).length;
    },

    updateChainSelection() {
        const checkboxes = document.querySelectorAll('.file-type-item input[type="checkbox"][name="chainType"]');
        this.selectedChains = Array.from(checkboxes)
            .filter(cb => cb.checked)
            .map(cb => cb.value);
    },

    updateOriginalHeatmapDisplay() {
        if (!this.heatmapResult) return;

        // Handle chain mode
        if (this.heatmapResult.mode === 'chain' && this.heatmapResult.chains) {
            this.displayChainResult(this.currentChain);
            return;
        }

        // Traditional mode
        if (!this.heatmapResult.images) return;

        const imagesData = this.heatmapResult.images;
        if (!imagesData[this.currentMetric]) {
            console.warn('Metric data not available:', this.currentMetric);
            return;
        }

        // Update image
        document.getElementById('originalHeatmapImage').src =
            'data:image/png;base64,' + imagesData[this.currentMetric];

        // Update table if available
        const metricsData = this.heatmapResult.metrics;
        if (metricsData && metricsData[this.currentMetric] && metricsData[this.currentMetric].table_data) {
            this.renderMatrixTable(metricsData[this.currentMetric].table_data, 'originalMatrixTable');
        }
    },

    updateGroupedHeatmapDisplay() {
        if (!this.heatmapResult || !this.heatmapResult.grouped_images) return;

        const imagesData = this.heatmapResult.grouped_images;
        if (!imagesData[this.currentMetric]) {
            console.warn('Grouped metric data not available:', this.currentMetric);
            return;
        }

        // Update image
        document.getElementById('groupedHeatmapImage').src =
            'data:image/png;base64,' + imagesData[this.currentMetric];

        // Update table if available
        const groupedMetrics = this.heatmapResult.grouped_metrics;
        if (groupedMetrics && groupedMetrics[this.currentMetric] && groupedMetrics[this.currentMetric].table_data) {
            this.renderMatrixTable(groupedMetrics[this.currentMetric].table_data, 'groupedMatrixTable');
        }
    },

    updateStepIndicator(step) {
        this.currentStep = step;
        document.querySelectorAll('.step-item').forEach((item, index) => {
            const stepNum = index + 1;
            item.classList.remove('active', 'completed');
            if (stepNum < step) item.classList.add('completed');
            else if (stepNum === step) item.classList.add('active');
        });
    },

    showLoading(text = '正在处理...') {
        document.getElementById('loadingText').textContent = text;
        document.getElementById('loadingOverlay').style.display = 'flex';
    },

    hideLoading() {
        document.getElementById('loadingOverlay').style.display = 'none';
    },

    showError(message) {
        alert(message);
    },

    // Folder browser support
    browseFolder() {
        document.getElementById('folderInput').click();
    },

    onFolderSelected(event) {
        const files = event.target.files;
        if (files.length > 0) {
            // Extract the common parent path from selected files
            // Note: Due to browser security, we can only get relative paths
            const firstPath = files[0].webkitRelativePath || files[0].name;
            const folderName = firstPath.split('/')[0];

            // Show message that folder selection has browser limitations
            alert(`已选择文件夹: ${folderName}\n\n注意：由于浏览器安全限制，无法直接获取完整路径。\n请在输入框中手动输入完整路径，或复制粘贴文件夹路径。`);
        }
    },

    // Step 1: Scan folder
    async scanFolder() {
        const basePath = document.getElementById('basePath').value.trim();
        if (!basePath) {
            this.showError('请输入文件夹路径');
            return;
        }

        this.showLoading('正在扫描文件夹...');
        try {
            const response = await fetch('/api/auto-heatmap/scan-folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ base_path: basePath })
            });
            const data = await response.json();

            if (!data.success) throw new Error(data.message || '扫描失败');

            this.basePath = basePath;
            this.scanResult = data;
            this.samples = data.samples.map(s => ({
                ...s,
                selected: true  // Default select all
            }));

            // Update UI
            document.getElementById('scanSummary').style.display = 'block';
            document.getElementById('scanSummaryText').textContent = data.summary;

            if (data.samples.length === 0) {
                // No samples found - show warning
                document.getElementById('scanSummary').className = 'alert alert-warning mt-3';
            } else {
                document.getElementById('scanSummary').className = 'alert alert-success mt-3';

                // 根据是否检测到链后缀决定显示模式
                if (data.has_chain_suffix && data.all_chains && data.all_chains.length > 0) {
                    // 显示链选择模式
                    this.renderChainSelection(data.all_chains);
                } else {
                    // 显示传统文件类型选择模式
                    this.renderFileTypes(data.all_file_types);
                }

                document.getElementById('step2Card').style.display = 'block';
                this.updateStepIndicator(2);

                // Hide field mapping section until file type is selected
                document.getElementById('fieldMappingSection').style.display = 'none';

                // Scroll to next step
                document.getElementById('step2Card').scrollIntoView({ behavior: 'smooth', block: 'start' });
            }

        } catch (error) {
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    },

    // Step 2: Render chain selection (for chain-suffixed files)
    renderChainSelection(chains) {
        const container = document.getElementById('fileTypeList');
        container.innerHTML = '';

        const header = document.createElement('div');
        header.className = 'mb-2';
        header.innerHTML = '<small class="text-muted"><i class="bi bi-info-circle me-1"></i>检测到链类型文件，请选择要分析的链（可多选）</small>';
        container.appendChild(header);

        const gridContainer = document.createElement('div');
        gridContainer.className = 'row g-2 mb-3';

        chains.forEach((chain, index) => {
            const count = this.countSamplesWithChain(chain);
            const col = document.createElement('div');
            col.className = 'col-6 col-md-4 col-lg-3';

            const item = document.createElement('div');
            item.className = 'file-type-item selected';
            item.style.padding = '8px 12px';
            item.innerHTML = `
                <input type="checkbox" name="chainType" value="${chain}" id="chain_${index}" checked>
                <div>
                    <div class="fw-medium">${chain}</div>
                    <small class="text-muted">${count} 个样本</small>
                </div>
            `;

            item.addEventListener('click', (e) => {
                if (e.target.tagName !== 'INPUT') {
                    const checkbox = item.querySelector('input');
                    checkbox.checked = !checkbox.checked;
                }

                if (item.querySelector('input').checked) {
                    item.classList.add('selected');
                } else {
                    item.classList.remove('selected');
                }

                this.updateChainSelection();
            });

            col.appendChild(item);
            gridContainer.appendChild(col);
        });

        container.appendChild(gridContainer);

        const buttonGroup = document.createElement('div');
        buttonGroup.className = 'd-flex gap-2 align-items-center';
        buttonGroup.innerHTML = `
            <button class="btn btn-sm btn-outline-secondary" onclick="AutoHeatmap.selectAllChains()">
                <i class="bi bi-check-all me-1"></i>全选
            </button>
            <button class="btn btn-sm btn-outline-secondary" onclick="AutoHeatmap.deselectAllChains()">
                <i class="bi bi-x-circle me-1"></i>清空
            </button>
            <div class="ms-auto">
                <button class="btn btn-primary" onclick="AutoHeatmap.confirmChainSelection()">
                    确认选择 <i class="bi bi-arrow-right ms-1"></i>
                </button>
            </div>
        `;
        container.appendChild(buttonGroup);

        this.selectedChains = [...chains];
    },

    selectAllChains() {
        document.querySelectorAll('.file-type-item input[type="checkbox"]').forEach(cb => {
            cb.checked = true;
            cb.closest('.file-type-item').classList.add('selected');
        });
        this.updateChainSelection();
    },

    deselectAllChains() {
        document.querySelectorAll('.file-type-item input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
            cb.closest('.file-type-item').classList.remove('selected');
        });
        this.updateChainSelection();
    },

    countSamplesWithChain(chain) {
        return this.samples.filter(s =>
            s.data_files.some(f => this.filenameMatchesChain(f.filename, chain))
        ).length;
    },

    updateChainSelection() {
        const checkboxes = document.querySelectorAll('.file-type-item input[type="checkbox"][name="chainType"]');
        this.selectedChains = Array.from(checkboxes)
            .filter(cb => cb.checked)
            .map(cb => cb.value);
    },

    async confirmChainSelection() {
        if (!this.selectedChains || this.selectedChains.length === 0) {
            this.showError('请至少选择一种链类型');
            return;
        }

        this.selectedFileType = '__CHAIN_SUFFIX__';
        this.isChainMode = true;

        let sampleFilePath = null;
        for (const sample of this.samples) {
            const matchingFile = sample.data_files.find(f =>
                this.selectedChains.some(chain => this.filenameMatchesChain(f.filename, chain))
            );
            if (matchingFile) {
                sampleFilePath = matchingFile.filepath;
                break;
            }
        }

        if (!sampleFilePath) {
            this.showError('未找到匹配的数据文件');
            return;
        }

        this.selectedFilePath = sampleFilePath;

        this.showLoading('正在读取文件列...');
        try {
            const response = await fetch('/api/auto-heatmap/get-file-columns', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath: sampleFilePath })
            });
            const data = await response.json();

            if (!data.success) throw new Error(data.message || '读取失败');

            this.fileColumns = data.columns;
            this.renderFieldMapping(data);

            document.getElementById('fieldMappingSection').style.display = 'block';
            document.getElementById('fieldMappingSection').scrollIntoView({ behavior: 'smooth', block: 'start' });

        } catch (error) {
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    },

    // Step 2: Render and select file types (traditional mode)
    renderFileTypes(fileTypes) {
        const container = document.getElementById('fileTypeList');
        container.innerHTML = '';

        const uniquePatterns = this.extractUniquePatterns(fileTypes);

        uniquePatterns.forEach((pattern, index) => {
            const count = this.countSamplesWithPattern(pattern);
            const item = document.createElement('div');
            item.className = 'file-type-item';
            item.innerHTML = `
                <input type="radio" name="fileType" value="${pattern}" id="fileType_${index}">
                <div>
                    <div class="fw-medium">${pattern}</div>
                    <small class="text-muted">${count} 个样本包含此文件</small>
                </div>
            `;
            item.addEventListener('click', () => {
                this.selectFileType(pattern);
                document.querySelectorAll('.file-type-item').forEach(i => i.classList.remove('selected'));
                item.classList.add('selected');
                item.querySelector('input').checked = true;
            });
            container.appendChild(item);
        });
    },

    extractUniquePatterns(fileTypes) {
        // Extract unique file name patterns (e.g., "_pep.csv", "_CDR3_list_1.csv")
        const patterns = new Set();
        fileTypes.forEach(ft => {
            // Extract the suffix pattern
            const match = ft.match(/(_[^_]+\.csv)$/i) || ft.match(/(\.csv)$/i);
            if (match) {
                patterns.add(match[0]);
            } else {
                patterns.add(ft);
            }
        });

        // If patterns are too generic, use full filenames
        if (patterns.size === 1 && patterns.has('.csv')) {
            return fileTypes;
        }

        return Array.from(patterns);
    },

    countSamplesWithPattern(pattern) {
        return this.samples.filter(s =>
            s.data_files.some(f => f.filename.includes(pattern) || f.filename.endsWith(pattern))
        ).length;
    },

    async selectFileType(pattern) {
        this.selectedFileType = pattern;

        // Find a sample file to get columns
        let sampleFilePath = null;
        for (const sample of this.samples) {
            const matchingFile = sample.data_files.find(f =>
                f.filename.includes(pattern) || f.filename.endsWith(pattern)
            );
            if (matchingFile) {
                sampleFilePath = matchingFile.filepath;
                break;
            }
        }

        if (!sampleFilePath) {
            this.showError('未找到匹配的数据文件');
            return;
        }

        this.selectedFilePath = sampleFilePath;

        // Get columns from the file
        this.showLoading('正在读取文件列...');
        try {
            const response = await fetch('/api/auto-heatmap/get-file-columns', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filepath: sampleFilePath })
            });
            const data = await response.json();

            if (!data.success) throw new Error(data.message || '读取失败');

            this.fileColumns = data.columns;
            this.renderFieldMapping(data);

            // Show field mapping section in the same card (combined step 2)
            document.getElementById('fieldMappingSection').style.display = 'block';

            // Scroll to field mapping section
            document.getElementById('fieldMappingSection').scrollIntoView({ behavior: 'smooth', block: 'start' });

        } catch (error) {
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    },

    // Step 3: Field mapping
    renderFieldMapping(data) {
        const cdr3Select = document.getElementById('cdr3Column');
        const copySelect = document.getElementById('copyColumn');

        // Clear and populate options
        cdr3Select.innerHTML = '<option value="">-- 请选择 --</option>';
        copySelect.innerHTML = '<option value="">-- 请选择 --</option>';

        data.columns.forEach(col => {
            cdr3Select.innerHTML += `<option value="${col}">${col}</option>`;
            copySelect.innerHTML += `<option value="${col}">${col}</option>`;
        });

        // Auto-select suggested columns
        if (data.suggested_cdr3) {
            cdr3Select.value = data.suggested_cdr3;
            this.fieldMapping.cdr3_column = data.suggested_cdr3;
        }
        if (data.suggested_copy) {
            copySelect.value = data.suggested_copy;
            this.fieldMapping.copy_column = data.suggested_copy;
        }

        // Add change listeners
        cdr3Select.onchange = () => {
            this.fieldMapping.cdr3_column = cdr3Select.value;
            this.updatePreview();
        };
        copySelect.onchange = () => {
            this.fieldMapping.copy_column = copySelect.value;
            this.updatePreview();
        };

        // Show preview
        if (data.sample_data && data.sample_data.length > 0) {
            this.renderPreviewTable(data.columns, data.sample_data);
        }
    },


    renderPreviewTable(columns, sampleData) {
        const container = document.getElementById('columnPreview');
        const table = document.getElementById('previewTable');

        // Build header
        let headerHtml = '<tr>';
        columns.forEach(col => {
            headerHtml += `<th>${col}</th>`;
        });
        headerHtml += '</tr>';
        table.querySelector('thead').innerHTML = headerHtml;

        // Build body
        let bodyHtml = '';
        sampleData.forEach(row => {
            bodyHtml += '<tr>';
            row.forEach(cell => {
                const displayValue = cell === null ? '' : String(cell).substring(0, 50);
                bodyHtml += `<td>${displayValue}</td>`;
            });
            bodyHtml += '</tr>';
        });
        table.querySelector('tbody').innerHTML = bodyHtml;

        container.style.display = 'block';
    },

    async updatePreview() {
        if (!this.selectedFilePath || !this.fieldMapping.cdr3_column) return;

        try {
            const response = await fetch('/api/auto-heatmap/preview-data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filepath: this.selectedFilePath,
                    field_mapping: this.fieldMapping,
                    max_rows: 5
                })
            });
            const data = await response.json();

            if (data.success && data.preview) {
                // Update preview display if needed
            }
        } catch (error) {
            console.error('Preview update failed:', error);
        }
    },

    confirmFieldMapping() {
        if (!this.fieldMapping.cdr3_column) {
            this.showError('请选择CDR3序列列');
            return;
        }
        if (!this.fieldMapping.copy_column) {
            this.showError('请选择拷贝数/表达量列');
            return;
        }

        // Filter samples based on mode
        if (this.isChainMode) {
            // 链模式：过滤包含选中链类型的样本
            this.samples = this.samples.filter(s =>
                s.data_files.some(f =>
                    this.selectedChains.some(chain => this.filenameMatchesChain(f.filename, chain))
                )
            );
        } else {
            // 传统模式：按文件类型过滤
            this.samples = this.samples.filter(s =>
                s.data_files.some(f =>
                    f.filename.includes(this.selectedFileType) ||
                    f.filename.endsWith(this.selectedFileType)
                )
            );
        }

        // Select all by default
        this.selectedSamples = new Set(this.samples.map(s => s.display_name));

        // Show CDR3 export button after field mapping is confirmed
        const exportBtn = document.getElementById('exportCDR3Btn');
        if (exportBtn && this.samples.length >= 2) {
            exportBtn.style.display = 'inline-block';
        }

        this.renderSampleList();
        document.getElementById('step3Card').style.display = 'block';
        this.updateStepIndicator(3);

        // Automatically show steps 4 and 5 since all samples are selected by default
        if (this.selectedSamples.size >= 2) {
            document.getElementById('step4Card').style.display = 'block';
            document.getElementById('step5Card').style.display = 'block';
            this.updateStepIndicator(4);
            this.initializeGroups();
        }

        // Scroll to next step
        document.getElementById('step3Card').scrollIntoView({ behavior: 'smooth', block: 'start' });
    },

    // Step 4: Sample selection and renaming
    renderSampleList() {
        const container = document.getElementById('sampleList');
        container.innerHTML = '';

        // Add chain info banner if in chain mode
        if (this.isChainMode && this.selectedChains && this.selectedChains.length > 0) {
            const chainBanner = document.createElement('div');
            chainBanner.className = 'alert alert-info mb-3';
            chainBanner.innerHTML = `
                <i class="bi bi-info-circle me-2"></i>
                <strong>链类型分析模式：</strong>已选择 ${this.selectedChains.length} 条链 
                <span class="badge bg-primary ms-2">${this.selectedChains.join(', ')}</span>
                <div class="small mt-1">热图将合并所有选中链的数据进行分析</div>
            `;
            container.appendChild(chainBanner);
        }

        this.samples.forEach((sample, index) => {
            const isSelected = this.selectedSamples.has(sample.display_name);
            const item = document.createElement('div');
            item.className = 'sample-item' + (isSelected ? ' selected' : '');
            item.dataset.index = index;

            const fileCount = sample.data_files.length;
            let matchingFiles = [];

            if (this.isChainMode) {
                // 链模式：找到所有匹配选中链的文件
                matchingFiles = sample.data_files.filter(f =>
                    this.selectedChains.some(chain => this.filenameMatchesChain(f.filename, chain))
                );
            } else {
                // 传统模式：找到匹配文件类型的文件
                const matchingFile = sample.data_files.find(f =>
                    f.filename.includes(this.selectedFileType) ||
                    f.filename.endsWith(this.selectedFileType)
                );
                if (matchingFile) matchingFiles = [matchingFile];
            }

            const fileInfo = this.isChainMode
                ? `${matchingFiles.length} 个链文件 (${this.selectedChains.join(', ')})`
                : matchingFiles.length > 0
                    ? `${matchingFiles[0].filename} (${matchingFiles[0].rows.toLocaleString()} 行)`
                    : '';

            item.innerHTML = `
                <input type="checkbox" ${isSelected ? 'checked' : ''} onchange="AutoHeatmap.toggleSample(${index})">
                <span class="sample-order-badge" title="当前顺序">#${index + 1}</span>
                <div class="sample-info">
                    <div class="d-flex align-items-center gap-2">
                        <span class="text-muted small">${sample.original_name}</span>
                        <i class="bi bi-arrow-right text-muted"></i>
                        <input type="text" class="form-control form-control-sm sample-name-input"
                            value="${sample.display_name}"
                            onchange="AutoHeatmap.renameSample(${index}, this.value)"
                            onclick="event.stopPropagation()">
                    </div>
                    <div class="sample-files">
                        ${fileInfo}
                    </div>
                </div>
                <span class="sample-drag-handle" title="拖拽调整顺序" draggable="true">
                    <i class="bi bi-grip-vertical"></i>
                </span>
            `;

            const dragHandle = item.querySelector('.sample-drag-handle');
            dragHandle.addEventListener('dragstart', (e) => this.startSampleDrag(e, index));
            dragHandle.addEventListener('dragend', () => this.endSampleDrag());
            item.addEventListener('dragover', (e) => this.onSampleDragOver(e, index));
            item.addEventListener('dragleave', () => this.onSampleDragLeave(index));
            item.addEventListener('drop', (e) => this.dropSample(e, index));

            item.addEventListener('click', (e) => {
                if (e.target.tagName !== 'INPUT' && !e.target.closest('.sample-drag-handle')) {
                    this.toggleSample(index);
                }
            });

            container.appendChild(item);
        });

        this.updateSelectedCount();
    },

    startSampleDrag(event, index) {
        this.draggedSampleIndex = index;
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', String(index));
        const sourceItem = event.target.closest('.sample-item');
        if (sourceItem) {
            sourceItem.classList.add('dragging');
        }
    },

    onSampleDragOver(event, index) {
        if (this.draggedSampleIndex === null || this.draggedSampleIndex === index) {
            return;
        }
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        const targetItem = event.currentTarget;
        if (targetItem) {
            targetItem.classList.add('drag-over');
        }
    },

    onSampleDragLeave(index) {
        const item = document.querySelector(`.sample-item[data-index="${index}"]`);
        if (item) {
            item.classList.remove('drag-over');
        }
    },

    dropSample(event, index) {
        event.preventDefault();
        const sourceIndex = this.draggedSampleIndex;
        this.clearSampleDragState();
        if (sourceIndex === null || sourceIndex === index) {
            return;
        }

        this.moveSampleToIndex(sourceIndex, index);
    },

    endSampleDrag() {
        this.clearSampleDragState();
    },

    clearSampleDragState() {
        document.querySelectorAll('.sample-item.dragging, .sample-item.drag-over').forEach(item => {
            item.classList.remove('dragging', 'drag-over');
        });
        this.draggedSampleIndex = null;
    },

    moveSampleToIndex(sourceIndex, targetIndex) {
        if (
            sourceIndex < 0 || sourceIndex >= this.samples.length ||
            targetIndex < 0 || targetIndex >= this.samples.length
        ) {
            return;
        }

        const reordered = [...this.samples];
        const [movedSample] = reordered.splice(sourceIndex, 1);
        const insertIndex = sourceIndex < targetIndex ? targetIndex - 1 : targetIndex;
        reordered.splice(insertIndex, 0, movedSample);
        this.samples = reordered;
        this.renderSampleList();
        this.renderGroups();
    },

    toggleSample(index) {
        const sample = this.samples[index];
        const displayName = sample.display_name;

        if (this.selectedSamples.has(displayName)) {
            this.selectedSamples.delete(displayName);
        } else {
            this.selectedSamples.add(displayName);
        }

        this.renderSampleList();
        this.checkCanProceed();
    },

    toggleAllSamples() {
        const allSelected = this.samples.every(s => this.selectedSamples.has(s.display_name));

        if (allSelected) {
            this.selectedSamples.clear();
        } else {
            this.selectedSamples = new Set(this.samples.map(s => s.display_name));
        }

        this.renderSampleList();
        this.checkCanProceed();
    },

    renameSample(index, newName) {
        const oldName = this.samples[index].display_name;
        const trimmedName = newName.trim();

        if (!trimmedName) {
            this.showError('样本名称不能为空');
            this.renderSampleList();
            return;
        }

        // Check for duplicate names
        const isDuplicate = this.samples.some((s, i) =>
            i !== index && s.display_name === trimmedName
        );

        if (isDuplicate) {
            this.showError('样本名称已存在，请使用不同的名称');
            this.renderSampleList();
            return;
        }

        // Update selected samples set
        if (this.selectedSamples.has(oldName)) {
            this.selectedSamples.delete(oldName);
            this.selectedSamples.add(trimmedName);
        }

        // Update groups
        this.groups.forEach(group => {
            const idx = group.sample_names.indexOf(oldName);
            if (idx > -1) {
                group.sample_names[idx] = trimmedName;
            }
        });

        this.samples[index].display_name = trimmedName;
    },

    updateSelectedCount() {
        document.getElementById('selectedCount').textContent = '已选: ' + this.selectedSamples.size;
    },

    checkCanProceed() {
        if (this.selectedSamples.size >= 2) {
            document.getElementById('step4Card').style.display = 'block';
            document.getElementById('step5Card').style.display = 'block';
            this.updateStepIndicator(4);
            this.initializeGroups();

            // Scroll to grouping step
            document.getElementById('step4Card').scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    },

    // Step 5: Grouping
    initializeGroups() {
        this.groups = [];
        this.renderGroups();
    },

    renderGroups() {
        const container = document.getElementById('groupContainer');
        container.innerHTML = '';

        // Get samples that are in groups
        const groupedSamples = new Set();
        this.groups.forEach(g => g.sample_names.forEach(s => groupedSamples.add(s)));

        // Get ungrouped selected samples
        const ungroupedSamples = [...this.selectedSamples].filter(s => !groupedSamples.has(s));

        // Render ungrouped card
        container.appendChild(this.createGroupCard({ name: '未分组', sample_names: ungroupedSamples }, true));

        // Render group cards
        this.groups.forEach((group, index) => {
            container.appendChild(this.createGroupCard(group, false, index));
        });
    },

    createGroupCard(group, isUngrouped, groupIndex = -1) {
        const card = document.createElement('div');
        card.className = 'group-card' + (isUngrouped ? ' ungrouped' : '');
        card.dataset.groupIndex = groupIndex;

        let headerHtml = `
            <div class="group-header">
                <span class="group-name">${group.name}</span>
                <span class="group-count">(${group.sample_names.length})</span>
        `;

        if (!isUngrouped) {
            headerHtml += `
                <button class="btn btn-sm btn-outline-danger" onclick="AutoHeatmap.deleteGroup(${groupIndex})">
                    <i class="bi bi-trash"></i>
                </button>
            `;
        }
        headerHtml += '</div>';

        let samplesHtml = `<div class="group-samples drop-zone" data-group-index="${groupIndex}">`;
        group.sample_names.forEach(s => {
            samplesHtml += `
                <div class="group-sample-item" draggable="true" data-sample="${s}">
                    <span>${s}</span>
            `;
            if (!isUngrouped) {
                samplesHtml += `
                    <button class="btn btn-sm btn-link remove-btn p-0" onclick="AutoHeatmap.removeSampleFromGroup('${s}', ${groupIndex})">
                        <i class="bi bi-x"></i>
                    </button>
                `;
            }
            samplesHtml += '</div>';
        });
        samplesHtml += '</div>';

        card.innerHTML = headerHtml + samplesHtml;
        return card;
    },

    initDragAndDrop() {
        document.addEventListener('dragstart', (e) => {
            if (e.target.classList.contains('group-sample-item')) {
                e.dataTransfer.setData('text/plain', e.target.dataset.sample);
                e.target.classList.add('dragging');
            }
        });

        document.addEventListener('dragend', (e) => {
            if (e.target.classList.contains('group-sample-item')) {
                e.target.classList.remove('dragging');
            }
        });

        document.addEventListener('dragover', (e) => {
            const dropZone = e.target.classList.contains('drop-zone') ? e.target : e.target.closest('.drop-zone');
            if (dropZone) {
                e.preventDefault();
                dropZone.classList.add('drag-over');
            }
        });

        document.addEventListener('dragleave', (e) => {
            if (e.target.classList.contains('drop-zone')) {
                e.target.classList.remove('drag-over');
            }
        });

        document.addEventListener('drop', (e) => {
            const dropZone = e.target.classList.contains('drop-zone') ? e.target : e.target.closest('.drop-zone');
            if (dropZone) {
                e.preventDefault();
                dropZone.classList.remove('drag-over');
                const sampleName = e.dataTransfer.getData('text/plain');
                const targetGroupIndex = parseInt(dropZone.dataset.groupIndex);
                this.moveSampleToGroup(sampleName, targetGroupIndex);
            }
        });
    },

    moveSampleToGroup(sampleName, targetGroupIndex) {
        // Remove from all groups first
        this.groups.forEach(g => {
            const idx = g.sample_names.indexOf(sampleName);
            if (idx > -1) g.sample_names.splice(idx, 1);
        });

        // Add to target group if it's a valid group (not ungrouped)
        if (targetGroupIndex >= 0 && this.groups[targetGroupIndex]) {
            this.groups[targetGroupIndex].sample_names.push(sampleName);
        }

        this.renderGroups();
    },

    removeSampleFromGroup(sampleName, groupIndex) {
        if (this.groups[groupIndex]) {
            const idx = this.groups[groupIndex].sample_names.indexOf(sampleName);
            if (idx > -1) {
                this.groups[groupIndex].sample_names.splice(idx, 1);
            }
        }
        this.renderGroups();
    },

    createGroup() {
        const modal = new bootstrap.Modal(document.getElementById('createGroupModal'));
        document.getElementById('newGroupName').value = '';
        modal.show();
    },

    doCreateGroup() {
        const name = document.getElementById('newGroupName').value.trim();
        if (!name) {
            this.showError('请输入分组名称');
            return;
        }
        if (this.groups.some(g => g.name === name)) {
            this.showError('分组名称已存在');
            return;
        }

        this.groups.push({ name: name, sample_names: [] });
        this.renderGroups();
        bootstrap.Modal.getInstance(document.getElementById('createGroupModal')).hide();
    },

    deleteGroup(groupIndex) {
        if (confirm('确定要删除这个分组吗？')) {
            this.groups.splice(groupIndex, 1);
            this.renderGroups();
        }
    },

    exportGroupConfig() {
        const config = {
            groups: this.groups,
            selectedSamples: [...this.selectedSamples],
            sampleMappings: this.samples.map(s => ({
                original_name: s.original_name,
                display_name: s.display_name
            }))
        };

        const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'heatmap_config.json';
        a.click();
        URL.revokeObjectURL(url);
    },

    importGroupConfig() {
        const modal = new bootstrap.Modal(document.getElementById('importModal'));
        document.getElementById('importConfigText').value = '';
        modal.show();
    },

    doImportConfig() {
        try {
            const config = JSON.parse(document.getElementById('importConfigText').value);

            if (config.groups) {
                this.groups = config.groups;
            }

            if (config.sampleMappings) {
                config.sampleMappings.forEach(mapping => {
                    const sample = this.samples.find(s => s.original_name === mapping.original_name);
                    if (sample) {
                        sample.display_name = mapping.display_name;
                    }
                });
            }

            this.renderGroups();
            this.renderSampleList();
            bootstrap.Modal.getInstance(document.getElementById('importModal')).hide();

        } catch (e) {
            this.showError('无效的JSON格式');
        }
    },

    // Step 6: Generate heatmap
    async generateHeatmap() {
        if (this.selectedSamples.size < 2) {
            this.showError('至少需要选择2个样本');
            return;
        }

        this.showLoading('正在生成热图...');

        try {
            // Prepare selected samples data
            const selectedSamplesData = this.samples
                .filter(s => this.selectedSamples.has(s.display_name))
                .map(s => ({
                    original_name: s.original_name,
                    display_name: s.display_name,
                    folder_path: s.folder_path,
                    data_files: s.data_files.map(f => ({
                        filename: f.filename,
                        filepath: f.filepath,
                        size: f.size,
                        rows: f.rows,
                        columns: f.columns
                    }))
                }));

            // Prepare groups (only include groups with samples)
            const validGroups = this.groups
                .filter(g => g.sample_names.length > 0)
                .map(g => ({
                    name: g.name,
                    sample_names: g.sample_names.filter(s => this.selectedSamples.has(s))
                }))
                .filter(g => g.sample_names.length > 0);

            const requestData = {
                samples: selectedSamplesData,
                file_pattern: this.isChainMode ? null : this.selectedFileType,
                selected_chains: this.isChainMode ? this.selectedChains : null,
                field_mapping: this.fieldMapping,
                groups: validGroups,
                config: {
                    title: document.getElementById('heatmapTitle').value,
                    plot_type: this.getSelectedPlotType(),
                    color_scheme: document.getElementById('colorScheme').value,
                    annotation: document.getElementById('showAnnotation').checked
                }
            };

            const response = await fetch('/api/auto-heatmap/generate-heatmap', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });

            const data = await response.json();

            if (!data.success) throw new Error(data.message || '生成失败');

            this.heatmapResult = data;
            this.currentPlotType = data.plot_type || requestData.config.plot_type || 'heatmap';

            // Handle different modes
            if (data.mode === 'chain' && data.chains) {
                // Chain mode: display results for each chain
                this.renderChainModeResults(data);
            } else {
                // Traditional mode
                if (data.grouped_metrics && Object.keys(data.grouped_metrics).length > 0) {
                    document.getElementById('groupedTabItem').style.display = 'block';
                } else {
                    document.getElementById('groupedTabItem').style.display = 'none';
                }

                this.currentMetric = 'expression_sharing';
                this.updateOriginalHeatmapDisplay();
                if (data.grouped_images) {
                    this.updateGroupedHeatmapDisplay();
                }
            }

            document.getElementById('heatmapResults').style.display = 'block';
            this.updateStepIndicator(5);

        } catch (error) {
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    },

    // Render results for chain mode (each chain gets separate heatmaps)
    renderChainModeResults(data) {
        const resultsContainer = document.getElementById('heatmapResults');
        const chains = Object.keys(data.chains);

        // Hide grouped tab in chain mode
        const groupedTab = document.getElementById('groupedTabItem');
        if (groupedTab) groupedTab.style.display = 'none';

        // Store current chain and metric for navigation
        this.currentChain = chains[0];
        this.currentMetric = 'expression_sharing';

        // Create chain selector tabs - use originalHeatmap (the tab pane)
        const originalContent = document.getElementById('originalHeatmap');
        if (!originalContent) {
            console.error('originalHeatmap element not found');
            return;
        }

        // Build chain tabs HTML
        let chainTabsHtml = `
            <div class="chain-results-header mb-3">
                <div class="d-flex align-items-center justify-content-between">
                    <div>
                        <h6 class="mb-1">链类型结果</h6>
                        <small class="text-muted">共 ${chains.length} 条链的分析结果</small>
                    </div>
                    <div class="btn-group" role="group">
                        ${chains.map(chain => `
                            <button type="button" class="btn btn-outline-primary chain-tab-btn ${chain === this.currentChain ? 'active' : ''}" 
                                    data-chain="${chain}" onclick="AutoHeatmap.selectChainResult('${chain}')">
                                ${chain} <span class="badge bg-secondary ms-1">${data.chains[chain].sample_count}</span>
                            </button>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;

        // Insert chain tabs before the image
        const existingChainHeader = originalContent.querySelector('.chain-results-header');
        if (existingChainHeader) {
            existingChainHeader.outerHTML = chainTabsHtml;
        } else {
            originalContent.insertAdjacentHTML('afterbegin', chainTabsHtml);
        }

        // Display first chain's results
        this.displayChainResult(this.currentChain);
    },

    selectChainResult(chain) {
        this.currentChain = chain;

        // Update tab buttons
        document.querySelectorAll('.chain-tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.chain === chain);
        });

        this.displayChainResult(chain);
    },

    displayChainResult(chain) {
        if (!this.heatmapResult || !this.heatmapResult.chains || !this.heatmapResult.chains[chain]) return;

        const chainData = this.heatmapResult.chains[chain];
        const metricData = chainData.metrics[this.currentMetric];
        const imageData = chainData.images[this.currentMetric];

        if (!metricData || !imageData) {
            console.warn('No data for chain:', chain, 'metric:', this.currentMetric);
            return;
        }

        // Update image
        document.getElementById('originalHeatmapImage').src = 'data:image/png;base64,' + imageData;

        // Update/create table display
        this.renderMatrixTable(metricData.table_data, 'originalMatrixTable');
    },

    renderMatrixTable(tableData, containerId) {
        let container = document.getElementById(containerId);

        // Create container if it doesn't exist
        if (!container) {
            const imageElement = document.getElementById('originalHeatmapImage');
            if (!imageElement || !imageElement.parentElement || !imageElement.parentElement.parentElement) {
                console.error('Cannot find image container to append table');
                return;
            }
            const tableDiv = document.createElement('div');
            tableDiv.id = containerId;
            tableDiv.className = 'matrix-table-container mt-3';
            imageElement.parentElement.parentElement.appendChild(tableDiv);
            container = tableDiv;
        }

        if (!tableData || !tableData.columns || !tableData.rows) {
            container.innerHTML = '<p class="text-muted">表格数据不可用</p>';
            return;
        }

        let html = `
            <div class="card">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h6 class="mb-0"><i class="bi bi-table me-2"></i>相似度矩阵数据</h6>
                    <button class="btn btn-sm btn-outline-secondary" onclick="AutoHeatmap.copyMatrixTable()">
                        <i class="bi bi-clipboard me-1"></i>复制
                    </button>
                </div>
                <div class="card-body p-0">
                    <div class="table-responsive" style="max-height: 400px; overflow: auto;">
                        <table class="table table-sm table-bordered mb-0" id="${containerId}Table">
                            <thead class="table-light">
                                <tr>
                                    ${tableData.columns.map(col => `<th class="text-center">${col}</th>`).join('')}
                                </tr>
                            </thead>
                            <tbody>
                                ${tableData.rows.map((row, rowIdx) => `
                                    <tr>
                                        ${row.map((cell, colIdx) => {
            const isHeader = colIdx === 0;
            const isDiagonal = colIdx > 0 && rowIdx === colIdx - 1;
            const cellClass = isHeader ? 'fw-bold bg-light' : (isDiagonal ? 'bg-secondary bg-opacity-25' : '');
            const value = cell === null ? '-' : (typeof cell === 'number' ? cell.toFixed(4) : cell);
            return `<td class="text-center ${cellClass}">${value}</td>`;
        }).join('')}
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;

        container.innerHTML = html;
    },

    copyMatrixTable() {
        const table = document.querySelector('#originalMatrixTableTable');
        if (!table) return;

        let text = '';
        const rows = table.querySelectorAll('tr');
        rows.forEach(row => {
            const cells = row.querySelectorAll('th, td');
            const rowData = Array.from(cells).map(cell => cell.textContent.trim());
            text += rowData.join('\t') + '\n';
        });

        navigator.clipboard.writeText(text).then(() => {
            this.showSuccess('表格数据已复制到剪贴板');
        }).catch(err => {
            this.showError('复制失败: ' + err.message);
        });
    },

    downloadHeatmap(type, format) {
        if (!this.heatmapResult) return;

        let imageData, filename;

        // Handle chain mode
        if (this.heatmapResult.mode === 'chain' && this.heatmapResult.chains && this.currentChain) {
            const chainData = this.heatmapResult.chains[this.currentChain];
            if (!chainData || !chainData.images || !chainData.images[this.currentMetric]) return;
            imageData = chainData.images[this.currentMetric];
            filename = `${this.currentChain}_${this.currentMetric}_${this.getPlotFileSuffix()}.${format}`;
        } else {
            const imagesData = type === 'grouped' ? this.heatmapResult.grouped_images : this.heatmapResult.images;
            if (!imagesData || !imagesData[this.currentMetric]) return;
            imageData = imagesData[this.currentMetric];
            filename = `${this.currentMetric}${type === 'grouped' ? '_grouped' : ''}_${this.getPlotFileSuffix()}.${format}`;
        }

        const link = document.createElement('a');
        link.href = 'data:image/png;base64,' + imageData;
        link.download = filename;
        link.click();
    },

    downloadMatrix(type) {
        if (!this.heatmapResult) return;

        let matrixData, filename;

        // Handle chain mode
        if (this.heatmapResult.mode === 'chain' && this.heatmapResult.chains && this.currentChain) {
            const chainData = this.heatmapResult.chains[this.currentChain];
            if (!chainData || !chainData.metrics || !chainData.metrics[this.currentMetric]) return;
            matrixData = chainData.metrics[this.currentMetric].matrix_data;
            filename = `${this.currentChain}_${this.currentMetric}_matrix.csv`;
        } else {
            const metricsData = type === 'grouped' ? this.heatmapResult.grouped_metrics : this.heatmapResult.metrics;
            if (!metricsData || !metricsData[this.currentMetric]) return;
            matrixData = metricsData[this.currentMetric].matrix_data;
            filename = `${this.currentMetric}${type === 'grouped' ? '_grouped' : ''}_matrix.csv`;
        }

        if (!matrixData) return;

        const labels = matrixData.samples || matrixData.groups || matrixData.columns;
        const rowLabels = matrixData.samples || matrixData.groups;

        let csv = ',' + labels.join(',') + '\n';
        matrixData.values.forEach((row, i) => {
            csv += rowLabels[i] + ',' + row.map(v => v !== null ? v.toFixed(4) : '').join(',') + '\n';
        });

        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    },

    downloadAllHeatmaps(type) {
        if (!this.heatmapResult) return;

        // Handle chain mode - download all chains' heatmaps
        if (this.heatmapResult.mode === 'chain' && this.heatmapResult.chains) {
            Object.keys(this.heatmapResult.chains).forEach(chain => {
                const chainData = this.heatmapResult.chains[chain];
                if (!chainData || !chainData.images) return;

                Object.keys(chainData.images).forEach(metricName => {
                    const link = document.createElement('a');
                    link.href = 'data:image/png;base64,' + chainData.images[metricName];
                    link.download = `${chain}_${metricName}_${this.getPlotFileSuffix()}.png`;
                    link.click();
                });
            });
            return;
        }

        // Traditional mode
        const imagesData = type === 'grouped' ? this.heatmapResult.grouped_images : this.heatmapResult.images;
        if (!imagesData) return;

        Object.keys(imagesData).forEach(metricName => {
            const link = document.createElement('a');
            link.href = 'data:image/png;base64,' + imagesData[metricName];
            link.download = `${metricName}${type === 'grouped' ? '_grouped' : ''}_${this.getPlotFileSuffix()}.png`;
            link.click();
        });
    },

    downloadAllMatrices(type) {
        if (!this.heatmapResult) return;

        // Handle chain mode - download all chains' matrices
        if (this.heatmapResult.mode === 'chain' && this.heatmapResult.chains) {
            Object.keys(this.heatmapResult.chains).forEach(chain => {
                const chainData = this.heatmapResult.chains[chain];
                if (!chainData || !chainData.metrics) return;

                Object.keys(chainData.metrics).forEach(metricName => {
                    const matrixData = chainData.metrics[metricName].matrix_data;
                    if (!matrixData) return;

                    const labels = matrixData.samples || matrixData.columns;
                    const rowLabels = matrixData.samples;

                    let csv = ',' + labels.join(',') + '\n';
                    matrixData.values.forEach((row, i) => {
                        csv += rowLabels[i] + ',' + row.map(v => v !== null ? v.toFixed(4) : '').join(',') + '\n';
                    });

                    const blob = new Blob([csv], { type: 'text/csv' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${chain}_${metricName}_matrix.csv`;
                    a.click();
                    URL.revokeObjectURL(url);
                });
            });
            return;
        }

        // Traditional mode
        const metricsData = type === 'grouped' ? this.heatmapResult.grouped_metrics : this.heatmapResult.metrics;
        if (!metricsData) return;

        Object.keys(metricsData).forEach(metricName => {
            const matrixData = metricsData[metricName].matrix_data;
            if (!matrixData) return;

            const labels = matrixData.samples || matrixData.groups || matrixData.columns;
            const rowLabels = matrixData.samples || matrixData.groups;

            let csv = ',' + labels.join(',') + '\n';
            matrixData.values.forEach((row, i) => {
                csv += rowLabels[i] + ',' + row.map(v => v !== null ? v.toFixed(4) : '').join(',') + '\n';
            });

            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${metricName}${type === 'grouped' ? '_grouped' : ''}_matrix.csv`;
            a.click();
            URL.revokeObjectURL(url);
        });
    },

    /**
     * Generate integrated pipeline comparison HTML report.
     * Reuses current scanned base_path and selected chains.
     */
    async generateHeatmapWebReport() {
        if (!this.heatmapResult) {
            this.showError('请先填写并扫描base_path');
            return;
        }

        const config = this.getHeatmapReportConfigFromForm();
        if (!config) {
            return;
        }
        this.saveHeatmapReportConfig(config);
        this.showLoading('正在生成网页分析报告...');

        this.showLoading('正在生成Pipeline对比报告...');
        try {
            const payload = this.buildHeatmapReportPayload(config);

            const response = await fetch('/api/auto-heatmap/generate-heatmap-report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.message || '生成Pipeline报告失败');
            }

            await this.registerProjectResult({
                job_id: data.job_id,
                output_base: data.output_base,
                report_path: data.report_path,
                report_url: data.report_url,
                metadata_url: data.metadata_url,
                metadata: data.metadata
            });

            if (data.report_url) {
                window.open(data.report_url, '_blank');
            }
            const reportMsgText = data.report_url
                ? `\n报告地址: ${data.report_url}`
                : '\n报告未生成，请检查输出目录和日志。';
            alert(`网页分析报告生成完成。Job ID: ${data.job_id}${reportMsgText}`);
            return;

            const reportText = data.report_url
                ? `\n报告地址: ${data.report_url}`
                : '\n报告未生成，请检查输出目录和日志。';

            alert(`Pipeline对比报告生成完成。Job ID: ${data.job_id}${reportText}`);
        } catch (error) {
            this.showError(error.message || '生成Pipeline报告失败');
        } finally {
            this.hideLoading();
        }
    },

    /**
     * Generate web report from already generated similarity heatmap result.
     */
    async generateHeatmapWebReportV2() {
        if (!this.heatmapResult) {
            this.showError('请先生成热图后再创建网页报告');
            return;
        }

        const config = this.getHeatmapReportConfigFromForm();
        this.saveHeatmapReportConfig(config);
        this.showLoading('正在生成网页分析报告...');

        try {
            const payload = {
                heatmap_result: this.heatmapResult,
                output_name: config.output_name || null,
                embed_images: config.embed_images,
                report_context: {
                    source: 'similarity_heatmap',
                    base_path: this.basePath || null,
                    selected_samples: this.samples
                        .filter(s => this.selectedSamples.has(s.display_name))
                        .map(s => s.display_name),
                    selected_chains: this.isChainMode ? this.selectedChains : null,
                    generated_at: new Date().toISOString()
                }
            };

            const response = await fetch('/api/auto-heatmap/generate-heatmap-report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.message || '生成网页分析报告失败');
            }

            if (data.report_url) {
                window.open(data.report_url, '_blank');
            }

            const reportMsgText = data.report_url
                ? `\n报告地址: ${data.report_url}`
                : '\n报告未生成，请检查输出目录和日志。';
            alert(`网页分析报告生成完成。Job ID: ${data.job_id}${reportMsgText}`);
        } catch (error) {
            this.showError(error.message || '生成网页分析报告失败');
        } finally {
            this.hideLoading();
        }
    },

    /**
     * Export shared CDR3 sequences and abundance matrices as ZIP file
     */
    async exportSharedCDR3() {
        // Check if we have enough samples
        const selectedSamplesData = this.getSelectedSamplesPayload();

        if (selectedSamplesData.length < 2) {
            this.showError('至少需要选择2个样本才能导出CDR3分析数据');
            return;
        }

        if (!this.fieldMapping.cdr3_column || !this.fieldMapping.copy_column) {
            this.showError('请先完成字段映射');
            return;
        }

        this.showLoading('正在生成CDR3分析数据（Excel + CSV）...');

        try {
            const requestData = this.buildCDR3ExportRequestData();

            const response = await fetch('/api/auto-heatmap/export-shared-cdr3', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestData)
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.message || '导出失败');
            }

            // Download the ZIP file
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = 'CDR3_Export.zip';
            link.click();
            window.URL.revokeObjectURL(url);

            // Store flag for ZIP packaging
            this.hasCDR3Export = true;

            // Show success message
            alert('CDR3分析数据导出成功！\n包含：\n1. CDR3共享列表(样本对)\n2. 各链丰度矩阵(并集)\n3. 每个样本Top100\n4. Top100交集矩阵(按链)');

        } catch (error) {
            this.showError(error.message);
        } finally {
            this.hideLoading();
        }
    },

    /**
     * Download all results from the backend-generated shared_analysis bundle.
     * @param {string} type - 'original' or 'grouped'
     */
    async downloadBundledResults(type) {
        if (!this.heatmapResult) {
            this.showError('娌℃湁鍙笅杞界殑缁撴灉');
            return;
        }

        const timestamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
        const defaultName = `Shared_Analysis_${timestamp}`;
        const customName = prompt('璇疯緭鍏ュ帇缂╁寘鍚嶇О锛堜笉鍚?zip鎵╁睍鍚嶏級:', defaultName);

        if (customName === null) {
            return;
        }

        const zipFileName = (customName.trim() || defaultName) + '.zip';
        this.showLoading('姝ｅ湪鐢熸垚鍘嬬缉鍖?..');

        try {
            const config = this.getHeatmapReportConfigFromForm();
            this.saveHeatmapReportConfig(config);

            const response = await fetch('/api/auto-heatmap/generate-heatmap-report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.buildHeatmapReportPayload(config, { create_archive: true }))
            });

            const data = await response.json();
            if (!response.ok || !data.success || !data.archive_url) {
                throw new Error(data.message || '鐢熸垚鍘嬬缉鍖呭け璐?');
            }

            const archiveResponse = await fetch(data.archive_url);
            if (!archiveResponse.ok) {
                throw new Error('涓嬭浇鍘嬬缉鍖呭け璐?');
            }

            const blob = await archiveResponse.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = zipFileName;
            link.click();
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('Error creating bundled ZIP:', error);
            this.showError('鐢熸垚鍘嬬缉鍖呭け璐? ' + error.message);
        } finally {
            this.hideLoading();
        }
    },

    /**
     * Download all results (heatmaps + CSV matrices + CDR3 shared list) as a single ZIP file
     * @param {string} type - 'original' or 'grouped'
     */
    async downloadAllAsZip(type) {
        if (!this.heatmapResult) {
            this.showError('没有可下载的结果');
            return;
        }

        // Check if JSZip is available
        if (typeof JSZip === 'undefined') {
            this.showError('JSZip库未加载，请刷新页面重试');
            return;
        }

        // Prompt user for custom zip filename
        const timestamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
        const defaultName = `Shared_Analysis_${timestamp}`;
        const customName = prompt('请输入压缩包名称（不含.zip扩展名）:', defaultName);

        if (customName === null) {
            return;
        }

        const zipFileName = (customName.trim() || defaultName) + '.zip';

        this.showLoading('正在生成压缩包...');

        try {
            const zip = new JSZip();
            const folder = zip.folder(folderName);

            // Handle chain mode vs traditional mode
            if (this.heatmapResult.mode === 'chain' && this.heatmapResult.chains) {
                // Chain mode: create folder for each chain
                for (const [chain, chainData] of Object.entries(this.heatmapResult.chains)) {
                    const chainFolder = folder.folder(chain);

                    // Add heatmap images for this chain
                    if (chainData.images) {
                        const imagesFolder = chainFolder.folder('heatmaps');
                        for (const [metricName, base64Data] of Object.entries(chainData.images)) {
                            const fileName = `${chain}_${metricName}_${this.getPlotFileSuffix()}.png`;
                            imagesFolder.file(fileName, base64Data, { base64: true });
                        }
                    }

                    // Add CSV matrices for this chain
                    if (chainData.metrics) {
                        const csvFolder = chainFolder.folder('matrices');
                        for (const [metricName, metricInfo] of Object.entries(chainData.metrics)) {
                            const matrixData = metricInfo.matrix_data;
                            if (!matrixData) continue;

                            const labels = matrixData.samples || matrixData.columns;
                            const rowLabels = matrixData.samples;

                            let csv = ',' + labels.join(',') + '\n';
                            matrixData.values.forEach((row, i) => {
                                csv += rowLabels[i] + ',' + row.map(v => v !== null ? v.toFixed(4) : '').join(',') + '\n';
                            });

                            const fileName = `${chain}_${metricName}_matrix.csv`;
                            csvFolder.file(fileName, csv);
                        }
                    }
                }
            } else {
                // Traditional mode
                const imagesData = type === 'grouped' ? this.heatmapResult.grouped_images : this.heatmapResult.images;
                const metricsData = type === 'grouped' ? this.heatmapResult.grouped_metrics : this.heatmapResult.metrics;
                const suffix = type === 'grouped' ? '_grouped' : '';

                // Add all heatmap images
                if (imagesData) {
                    const imagesFolder = folder.folder('heatmaps');
                    for (const [metricName, base64Data] of Object.entries(imagesData)) {
                        const fileName = `${metricName}${suffix}_${this.getPlotFileSuffix()}.png`;
                        imagesFolder.file(fileName, base64Data, { base64: true });
                    }
                }

                // Add all CSV matrices
                if (metricsData) {
                    const csvFolder = folder.folder('matrices');
                    for (const [metricName, metricInfo] of Object.entries(metricsData)) {
                        const matrixData = metricInfo.matrix_data;
                        if (!matrixData) continue;

                        const labels = matrixData.samples || matrixData.groups || matrixData.columns;
                        const rowLabels = matrixData.samples || matrixData.groups;

                        let csv = ',' + labels.join(',') + '\n';
                        matrixData.values.forEach((row, i) => {
                            csv += rowLabels[i] + ',' + row.map(v => v !== null ? v.toFixed(4) : '').join(',') + '\n';
                        });

                        const fileName = `${metricName}${suffix}_matrix.csv`;
                        csvFolder.file(fileName, csv);
                    }
                }
            }

            // Add CDR3 analysis data if available or fetch it
            try {
                const selectedSamplesData = this.samples.filter(s => this.selectedSamples.has(s.display_name));

                if (selectedSamplesData.length >= 2 && this.fieldMapping.cdr3_column && this.fieldMapping.copy_column) {
                    // Fetch CDR3 export ZIP
                    const cdr3Response = await fetch('/api/auto-heatmap/export-shared-cdr3', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            samples: selectedSamplesData.map(s => ({
                                original_name: s.original_name,
                                display_name: s.display_name,
                                folder_path: s.folder_path,
                                data_files: s.data_files.map(f => ({
                                    filename: f.filename,
                                    filepath: f.filepath,
                                    size: f.size,
                                    rows: f.rows,
                                    columns: f.columns
                                }))
                            })),
                            file_pattern: this.isChainMode ? null : this.selectedFileType,
                            selected_chains: this.isChainMode ? this.selectedChains : null,
                            field_mapping: this.fieldMapping,
                            return_type: 'base64'
                        })
                    });

                    const cdr3Data = await cdr3Response.json();
                    if (cdr3Data.success && cdr3Data.data) {
                        // Load the CDR3 export ZIP and extract its contents
                        const cdr3Zip = await JSZip.loadAsync(cdr3Data.data, { base64: true });

                        // Create CDR3_Analysis folder in main ZIP
                        const cdr3Folder = folder.folder('CDR3_Analysis');

                        // Copy all files from CDR3 export ZIP to main ZIP
                        const filePromises = [];
                        cdr3Zip.forEach((relativePath, file) => {
                            if (!file.dir) {
                                filePromises.push(
                                    file.async('blob').then(content => {
                                        cdr3Folder.file(relativePath, content);
                                    })
                                );
                            }
                        });

                        await Promise.all(filePromises);
                    }
                }
            } catch (cdr3Error) {
                console.warn('Could not include CDR3 analysis data in ZIP:', cdr3Error);
            }

            // Generate ZIP and trigger download
            const content = await zip.generateAsync({ type: 'blob' });

            const url = URL.createObjectURL(content);
            const a = document.createElement('a');
            a.href = url;
            a.download = zipFileName;
            a.click();
            URL.revokeObjectURL(url);

        } catch (error) {
            console.error('Error creating ZIP:', error);
            this.showError('生成压缩包失败: ' + error.message);
        } finally {
            this.hideLoading();
        }
    },

    stopSyncPolling() {
        if (this.syncPollTimer) {
            clearTimeout(this.syncPollTimer);
            this.syncPollTimer = null;
        }
    },

    setScanSummary(message, variant = 'info') {
        const summary = document.getElementById('scanSummary');
        const text = document.getElementById('scanSummaryText');
        if (!summary || !text) return;
        summary.style.display = 'block';
        summary.className = `alert alert-${variant} mt-3`;
        text.textContent = message || '';
    }

};
window.AutoHeatmap = AutoHeatmap;
