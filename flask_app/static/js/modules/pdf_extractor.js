/**
 * PDF Extractor Module
 * Handles PDF table and image extraction UI interactions
 * 
 * Requirements: 9.1-9.6, 12.1-12.6
 */

const PDFExtractorModule = {
    // State
    selectedTableFiles: new Set(),
    selectedBatchFiles: new Set(),
    selectedImageFiles: new Set(),
    selectedImageIndices: new Set(),
    currentPdfImages: [],
    extractedTableData: null,
    extractedImages: {},
    currentTableProject: '',
    currentImageProject: '',
    projects: [],
    legacyProjects: [],

    // Default image indices
    defaultImageIndices: [15, -1],

    /**
     * Initialize the module
     */
    init: function () {
        this.bindEvents();
        this.loadProjects();
        this.loadPdfFiles();
    },

    /**
     * Bind event handlers
     */
    bindEvents: function () {
        const self = this;

        // Table extraction
        document.getElementById('extractTablesBtn').addEventListener('click', function () {
            self.extractTables();
        });

        document.getElementById('copyExtractedTableBtn').addEventListener('click', function () {
            self.copyTableToClipboard();
        });

        // Chart generation
        document.getElementById('generateChartBtn')?.addEventListener('click', function () {
            self.generateChart();
        });

        // Sample chart selector
        document.getElementById('sampleChartSelect')?.addEventListener('change', function () {
            self.displaySelectedSampleChart(this.value);
        });

        // Download all charts
        document.getElementById('downloadAllChartsBtn')?.addEventListener('click', function () {
            self.downloadAllCharts();
        });

        // PDF upload for table extraction
        const pdfFileInput = document.getElementById('pdfFileInput');
        if (pdfFileInput) {
            pdfFileInput.addEventListener('change', function () {
                if (this.files && this.files[0]) {
                    self.uploadPdfFile(this.files[0]);
                }
            });
        }

        // Drag and drop for PDF upload
        const dropZone = document.getElementById('pdfUploadDropZone');
        if (dropZone) {
            dropZone.addEventListener('dragover', function (e) {
                e.preventDefault();
                e.stopPropagation();
                this.classList.add('drag-over');
            });

            dropZone.addEventListener('dragleave', function (e) {
                e.preventDefault();
                e.stopPropagation();
                this.classList.remove('drag-over');
            });

            dropZone.addEventListener('drop', function (e) {
                e.preventDefault();
                e.stopPropagation();
                this.classList.remove('drag-over');

                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    self.uploadPdfFile(files[0]);
                }
            });
        }

        // Image file upload
        const imageFileInput = document.getElementById('imageFileInput');
        if (imageFileInput) {
            imageFileInput.addEventListener('change', function () {
                if (this.files && this.files[0]) {
                    self.uploadPdfFile(this.files[0]);
                }
            });
        }

        // Drag and drop for image upload
        const imageDropZone = document.getElementById('imageUploadDropZone');
        if (imageDropZone) {
            imageDropZone.addEventListener('dragover', function (e) {
                e.preventDefault();
                e.stopPropagation();
                this.classList.add('drag-over');
            });

            imageDropZone.addEventListener('dragleave', function (e) {
                e.preventDefault();
                e.stopPropagation();
                this.classList.remove('drag-over');
            });

            imageDropZone.addEventListener('drop', function (e) {
                e.preventDefault();
                e.stopPropagation();
                this.classList.remove('drag-over');

                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    self.uploadPdfFile(files[0]);
                }
            });
        }

        // Image extraction - file selection
        document.getElementById('imageFileSelect')?.addEventListener('change', function () {
            self.onImageFileSelected(this.value);
        });

        document.getElementById('listImagesBtn')?.addEventListener('click', function () {
            self.listImages();
        });

        // Image selection controls
        document.getElementById('selectAllImagesBtn')?.addEventListener('click', function () {
            self.selectAllImages();
        });

        document.getElementById('deselectAllImagesBtn')?.addEventListener('click', function () {
            self.deselectAllImages();
        });

        document.getElementById('selectByIndicesBtn')?.addEventListener('click', function () {
            self.selectByIndices();
        });

        document.getElementById('extractSelectedImagesBtn')?.addEventListener('click', function () {
            self.extractSelectedImages();
        });

        // Batch extraction
        document.getElementById('batchExtractBtn').addEventListener('click', function () {
            self.batchExtractImages();
        });

        document.getElementById('downloadAllImagesBtn')?.addEventListener('click', function () {
            self.downloadAllImages();
        });

        // PDF image selector
        document.getElementById('pdfImageSelect')?.addEventListener('change', function () {
            self.displayPdfImages(this.value);
        });

        // Default indices checkbox
        const useDefaultCheckbox = document.getElementById('useDefaultIndices');
        if (useDefaultCheckbox) {
            useDefaultCheckbox.addEventListener('change', function () {
                const indicesInput = document.getElementById('imageIndices');
                if (this.checked) {
                    indicesInput.value = '16, -1';
                    indicesInput.disabled = true;
                } else {
                    indicesInput.disabled = false;
                }
            });
        }

        // Directory browser
        const browseOutputBtn = document.getElementById('browseOutputBtn');
        if (browseOutputBtn) {
            browseOutputBtn.addEventListener('click', function () {
                self.showDirectoryBrowser();
            });
        }

        const selectDirectoryBtn = document.getElementById('selectDirectoryBtn');
        if (selectDirectoryBtn) {
            selectDirectoryBtn.addEventListener('click', function () {
                self.selectDirectory();
            });
        }

        const cancelDirectoryBtn = document.getElementById('cancelDirectoryBtn');
        if (cancelDirectoryBtn) {
            cancelDirectoryBtn.addEventListener('click', function () {
                self.hideDirectoryBrowser();
            });
        }

        // Project selectors
        const tableProjectSelect = document.getElementById('tableProjectSelect');
        if (tableProjectSelect) {
            tableProjectSelect.addEventListener('change', function () {
                self.currentTableProject = this.value;
                self.loadPdfFiles();
            });
        }

        const imageProjectSelect = document.getElementById('imageProjectSelect');
        if (imageProjectSelect) {
            imageProjectSelect.addEventListener('change', function () {
                self.currentImageProject = this.value;
                self.loadPdfFiles();
            });
        }

        // New project buttons
        const newTableProjectBtn = document.getElementById('newTableProjectBtn');
        if (newTableProjectBtn) {
            newTableProjectBtn.addEventListener('click', function () {
                self.createNewProject('table');
            });
        }

        const newImageProjectBtn = document.getElementById('newImageProjectBtn');
        if (newImageProjectBtn) {
            newImageProjectBtn.addEventListener('click', function () {
                self.createNewProject('image');
            });
        }
    },

    /**
     * Load project list
     */
    loadProjects: async function () {
        try {
            const [projectResponse, legacyResponse] = await Promise.all([
                fetch('/api/projects').catch(() => null),
                fetch('/api/files/projects').catch(() => null)
            ]);

            const projectItems = [];
            if (projectResponse?.ok) {
                const data = await projectResponse.json();
                (data.projects || []).forEach(project => {
                    if (project && project.id && project.name) {
                        projectItems.push({
                            id: project.id,
                            name: project.name,
                            label: project.institution ? `${project.name} · ${project.institution}` : project.name,
                            legacy: false
                        });
                    }
                });
            }

            const seenNames = new Set(projectItems.map(project => project.name));
            this.legacyProjects = [];
            if (legacyResponse?.ok) {
                const data = await legacyResponse.json();
                this.legacyProjects = data.projects || [];
                this.legacyProjects.forEach(name => {
                    if (!name || seenNames.has(name)) return;
                    projectItems.push({
                        id: `legacy:${name}`,
                        name,
                        label: name === 'default' ? '默认项目' : `${name}（旧文件）`,
                        legacy: true
                    });
                });
            }

            this.projects = projectItems;

            // Populate project selectors
            this.populateProjectSelect('tableProjectSelect', this.currentTableProject);
            this.populateProjectSelect('imageProjectSelect', this.currentImageProject);
        } catch (error) {
            console.error('Error loading projects:', error);
        }
    },

    /**
     * Populate project select dropdown
     */
    populateProjectSelect: function (selectId, currentValue) {
        const select = document.getElementById(selectId);
        if (!select) return;

        const currentSelection = currentValue || select.value;
        select.innerHTML = '<option value="">全部项目</option>';

        this.projects.forEach(project => {
            const option = document.createElement('option');
            option.value = project.id;
            option.textContent = project.label || project.name;
            option.dataset.projectName = project.name;
            option.dataset.legacyProject = project.legacy ? 'true' : 'false';
            if (project.id === currentSelection) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    },

    /**
     * Resolve the selected project object for a panel.
     */
    getSelectedProject: function (type) {
        const projectId = type === 'table' ? this.currentTableProject : this.currentImageProject;
        if (!projectId) return null;
        return this.projects.find(project => project.id === projectId) || null;
    },

    /**
     * Resolve the legacy project name used by old PDF file APIs.
     */
    getSelectedProjectName: function (type) {
        const project = this.getSelectedProject(type);
        return project ? project.name : '';
    },

    /**
     * Create new project
     */
    createNewProject: async function (type) {
        const projectName = prompt('请输入新项目名称:');
        if (!projectName || !projectName.trim()) return;

        const trimmedName = projectName.trim();

        try {
            const response = await fetch('/api/projects', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: trimmedName })
            });

            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.message || data.error || '创建项目失败');
            }

            const project = await response.json();
            const projectItem = {
                id: project.id,
                name: project.name,
                label: project.institution ? `${project.name} · ${project.institution}` : project.name,
                legacy: false
            };

            this.projects = [
                projectItem,
                ...this.projects.filter(item => item.id !== projectItem.id && item.name !== projectItem.name)
            ];

            if (type === 'table') {
                this.currentTableProject = projectItem.id;
            } else {
                this.currentImageProject = projectItem.id;
            }

            this.populateProjectSelect('tableProjectSelect', this.currentTableProject);
            this.populateProjectSelect('imageProjectSelect', this.currentImageProject);
            this.loadPdfFiles();
        } catch (error) {
            console.error('Error creating project:', error);
            this.showError(error.message || '创建项目失败');
        }
    },

    /**
     * Load available PDF files
     */
    loadPdfFiles: async function () {
        try {
            // Build URL with project filter
            let tableUrl = '/api/files';
            let imageUrl = '/api/files';

            const tableProjectName = this.getSelectedProjectName('table');
            const imageProjectName = this.getSelectedProjectName('image');

            if (tableProjectName) {
                tableUrl += `?project=${encodeURIComponent(tableProjectName)}`;
            }
            if (imageProjectName) {
                imageUrl += `?project=${encodeURIComponent(imageProjectName)}`;
            }

            // Load files for table panel
            const tableResponse = await fetch(tableUrl);
            if (tableResponse.ok) {
                const tableData = await tableResponse.json();
                const tablePdfFiles = tableData.files.filter(file =>
                    file.name.toLowerCase().endsWith('.pdf')
                );
                this.populateFileList('tableFileList', tablePdfFiles, 'table');
            }

            // Load files for image panel
            const imageResponse = await fetch(imageUrl);
            if (imageResponse.ok) {
                const imageData = await imageResponse.json();
                const imagePdfFiles = imageData.files.filter(file =>
                    file.name.toLowerCase().endsWith('.pdf')
                );
                this.populateFileList('batchFileList', imagePdfFiles, 'batch');
            }

        } catch (error) {
            console.error('Error loading files:', error);

            const errorMessage = '<p class="text-danger">加载文件失败，请刷新页面重试</p>';
            const tableFileList = document.getElementById('tableFileList');
            if (tableFileList) tableFileList.innerHTML = errorMessage;
            const batchFileList = document.getElementById('batchFileList');
            if (batchFileList) batchFileList.innerHTML = errorMessage;
        }
    },

    /**
     * Load available PDF files (old implementation - kept for reference)
     */
    loadPdfFilesOld: async function () {
        try {
            const response = await fetch('/api/files');

            if (!response.ok) {
                throw new Error('加载文件列表失败');
            }

            const data = await response.json();

            // Filter PDF files
            const pdfFiles = data.files.filter(file =>
                file.name.toLowerCase().endsWith('.pdf')
            );

            // Populate table file list
            this.populateFileList('tableFileList', pdfFiles, 'table');

            // Populate batch file list (for image extraction)
            this.populateFileList('batchFileList', pdfFiles, 'batch');

        } catch (error) {
            console.error('Error loading files:', error);

            // Show error in all file lists
            const errorMessage = '<p class="text-danger">加载文件失败，请刷新页面重试</p>';

            const tableFileList = document.getElementById('tableFileList');
            if (tableFileList) {
                tableFileList.innerHTML = errorMessage;
            }

            const batchFileList = document.getElementById('batchFileList');
            if (batchFileList) {
                batchFileList.innerHTML = errorMessage;
            }
        }
    },

    /**
     * Populate file list with checkboxes
     */
    populateFileList: function (containerId, files, type) {
        const container = document.getElementById(containerId);

        if (!container) {
            console.warn(`Container ${containerId} not found`);
            return;
        }

        if (files.length === 0) {
            container.innerHTML = '<p class="text-muted">暂无PDF文件。请先上传PDF文件。</p>';
            return;
        }

        container.innerHTML = '';
        const self = this;

        files.forEach(file => {
            const item = document.createElement('div');
            item.className = 'file-item';

            // Use original_name if available, otherwise use name
            const displayName = file.name || '未命名文件';

            item.innerHTML = `
                <input type="checkbox" id="${type}_${file.id}" value="${file.id}">
                <i class="bi bi-file-earmark-pdf file-icon"></i>
                <span class="file-name" title="${displayName}">${displayName}</span>
            `;

            const checkbox = item.querySelector('input[type="checkbox"]');
            checkbox.addEventListener('change', function () {
                if (type === 'table') {
                    self.onTableFileToggle(file.id, this.checked);
                } else if (type === 'batch') {
                    self.onBatchFileToggle(file.id, this.checked);
                } else if (type === 'image') {
                    self.onImageFileToggle(file.id, this.checked);
                }
                item.classList.toggle('selected', this.checked);
            });

            container.appendChild(item);
        });
    },

    /**
     * Populate file select dropdown
     */
    populateFileSelect: function (selectId, files) {
        const select = document.getElementById(selectId);

        if (!select) {
            console.warn(`Select element ${selectId} not found`);
            return;
        }

        select.innerHTML = '<option value="">-- 选择PDF文件 --</option>';

        if (files.length === 0) {
            select.innerHTML = '<option value="">-- 暂无PDF文件 --</option>';
            return;
        }

        files.forEach(file => {
            const option = document.createElement('option');
            option.value = file.id;

            // Use original_name if available, otherwise use name
            const displayName = file.name || '未命名文件';
            option.textContent = displayName;

            select.appendChild(option);
        });
    },

    /**
     * Handle table file selection toggle
     */
    onTableFileToggle: function (fileId, selected) {
        if (selected) {
            this.selectedTableFiles.add(fileId);
        } else {
            this.selectedTableFiles.delete(fileId);
        }

        document.getElementById('tableSelectedCount').textContent =
            `${this.selectedTableFiles.size} files selected`;
        document.getElementById('extractTablesBtn').disabled =
            this.selectedTableFiles.size === 0;
    },

    /**
     * Handle batch file selection toggle
     */
    onBatchFileToggle: function (fileId, selected) {
        if (selected) {
            this.selectedBatchFiles.add(fileId);
        } else {
            this.selectedBatchFiles.delete(fileId);
        }

        document.getElementById('batchSelectedCount').textContent =
            `${this.selectedBatchFiles.size} files selected`;
        document.getElementById('batchExtractBtn').disabled =
            this.selectedBatchFiles.size === 0;
    },

    /**
     * Handle image file selection toggle
     */
    onImageFileToggle: function (fileId, selected) {
        if (selected) {
            this.selectedImageFiles.add(fileId);
        } else {
            this.selectedImageFiles.delete(fileId);
        }

        const countEl = document.getElementById('imageSelectedCount');
        if (countEl) {
            countEl.textContent = `已选择${this.selectedImageFiles.size}个文件`;
        }
    },

    /**
     * Handle image file selection (for dropdown - legacy)
     */
    onImageFileSelected: function (fileId) {
        // Clear upload input when selecting from dropdown
        const pdfFileInput = document.getElementById('pdfFileInput');
        if (pdfFileInput) pdfFileInput.value = '';

        const uploadBtn = document.getElementById('uploadPdfBtn');
        if (uploadBtn) uploadBtn.disabled = true;

        const listBtn = document.getElementById('listImagesBtn');
        if (listBtn) listBtn.disabled = !fileId;

        // Hide thumbnails section when file changes
        const thumbnailsSection = document.getElementById('imageThumbnailsSection');
        if (thumbnailsSection) thumbnailsSection.classList.add('d-none');
        this.currentPdfImages = [];
        this.selectedImageIndices.clear();
    },

    /**
     * Handle PDF file selected for upload
     */
    onPdfFileSelected: function (file) {
        const uploadBtn = document.getElementById('uploadPdfBtn');
        const statusDiv = document.getElementById('uploadStatus');

        statusDiv.innerHTML = '';

        if (!file) {
            uploadBtn.disabled = true;
            return;
        }

        // Validate file type
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            statusDiv.innerHTML = '<div class="alert alert-danger">请选择PDF文件</div>';
            uploadBtn.disabled = true;
            return;
        }

        // Validate file size (50MB)
        const maxSize = 50 * 1024 * 1024;
        if (file.size > maxSize) {
            statusDiv.innerHTML = '<div class="alert alert-danger">文件太大，最大支持50MB</div>';
            uploadBtn.disabled = true;
            return;
        }

        // Clear dropdown selection when uploading new file
        document.getElementById('imageFileSelect').value = '';

        uploadBtn.disabled = false;
        statusDiv.innerHTML = `<div class="alert alert-info">准备上传: ${file.name} (${this.formatFileSize(file.size)})</div>`;
    },

    /**
     * Upload PDF file
     */
    uploadPdfFile: async function (file) {
        // 如果没有传入文件，尝试从input获取
        if (!file) {
            const fileInput = document.getElementById('pdfFileInput');
            file = fileInput?.files?.[0];
        }

        if (!file) {
            this.showError('请选择要上传的文件');
            return;
        }

        const uploadBtn = document.getElementById('uploadPdfBtn');
        const progressDiv = document.getElementById('pdfUploadProgress');
        const progressBar = progressDiv?.querySelector('.progress-bar');
        const statusDiv = document.getElementById('uploadStatus');

        if (uploadBtn) uploadBtn.disabled = true;
        if (progressDiv) progressDiv.classList.remove('d-none');
        if (statusDiv) statusDiv.innerHTML = '';

        try {
            const formData = new FormData();
            formData.append('file', file);

            // Add project to form data (use current project from active tab)
            const activeTab = document.querySelector('#extractorTabs .nav-link.active');
            const isTableTab = activeTab?.id === 'tables-tab';
            const projectType = isTableTab ? 'table' : 'image';
            const projectName = this.getSelectedProjectName(projectType);
            const project = this.getSelectedProject(projectType);
            if (projectName) {
                formData.append('project', projectName);
            }

            const response = await fetch('/api/pdf/upload', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || '上传失败');
            }

            const result = await response.json();

            if (project && !project.legacy) {
                await this.uploadFileToProjectAsset(project.id, file, 'pdf_source');
            }

            // Update progress to 100%
            if (progressBar) {
                progressBar.style.width = '100%';
                progressBar.textContent = '100%';
            }

            // Show success message
            if (statusDiv) statusDiv.innerHTML = `<div class="alert alert-success">上传成功！</div>`;

            // Reload file list
            await this.loadPdfFiles();

            // Auto-select the uploaded file (if elements exist)
            const imageFileSelect = document.getElementById('imageFileSelect');
            const listImagesBtn = document.getElementById('listImagesBtn');
            if (imageFileSelect) imageFileSelect.value = result.id || result.file_id;
            if (listImagesBtn) listImagesBtn.disabled = false;

            // Clear file input
            const fileInput = document.getElementById('pdfFileInput');
            if (fileInput) fileInput.value = '';

            // Hide progress after a delay
            setTimeout(() => {
                if (progressDiv) {
                    progressDiv.classList.add('d-none');
                    if (progressBar) {
                        progressBar.style.width = '0%';
                        progressBar.textContent = '0%';
                    }
                }
            }, 2000);

        } catch (error) {
            console.error('Error uploading PDF:', error);
            if (statusDiv) statusDiv.innerHTML = `<div class="alert alert-danger">上传失败: ${error.message}</div>`;
            if (progressDiv) progressDiv.classList.add('d-none');
        } finally {
            if (uploadBtn) uploadBtn.disabled = false;
        }
    },

    /**
     * Store the uploaded PDF under the selected project assets as well.
     */
    uploadFileToProjectAsset: async function (projectId, file, assetType) {
        try {
            const assetForm = new FormData();
            assetForm.append('asset_type', assetType);
            assetForm.append('files', file);
            assetForm.append('relative_paths', JSON.stringify([file.name]));

            const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/assets`, {
                method: 'POST',
                body: assetForm
            });

            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(data.message || data.error || '项目资产登记失败');
            }
        } catch (error) {
            console.warn('PDF uploaded, but project asset registration failed:', error);
        }
    },

    /**
     * Format file size for display
     */
    formatFileSize: function (bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    },

    // =========================================================================
    // Table Extraction - Requirements: 9.1-9.6
    // =========================================================================

    /**
     * Extract tables from selected PDF files
     */
    extractTables: async function () {
        if (this.selectedTableFiles.size === 0) {
            this.showError('请至少选择一个PDF文件');
            return;
        }

        const btn = document.getElementById('extractTablesBtn');
        const spinner = document.getElementById('tableLoadingSpinner');
        btn.disabled = true;
        spinner.classList.remove('d-none');

        try {
            const response = await fetch('/api/pdf/extract-tables', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_ids: Array.from(this.selectedTableFiles)
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || 'Extraction failed');
            }

            const result = await response.json();
            this.extractedTableData = result;
            this.displayTableResults(result);

        } catch (error) {
            console.error('Error extracting tables:', error);
            this.showError(error.message || '提取表格失败');
        } finally {
            btn.disabled = false;
            spinner.classList.add('d-none');
        }
    },

    /**
     * Display table extraction results
     */
    displayTableResults: function (result) {
        const section = document.getElementById('tableResultsSection');
        section.classList.remove('d-none');

        // Display status
        const statusDiv = document.getElementById('extractionStatus');
        statusDiv.innerHTML = `
            <span class="success-count">${result.success_count} files extracted successfully</span>
            ${result.fail_count > 0 ?
                `<span class="ms-3 fail-count">${result.fail_count} files failed</span>` : ''}
        `;

        // Display error messages if any
        if (result.failed_files && result.failed_files.length > 0) {
            let errorHtml = '<div class="error-list mt-2">';
            result.failed_files.forEach(file => {
                const errorMsg = result.error_messages[file] || 'Unknown error';
                errorHtml += `
                    <div class="error-item">
                        <span class="error-file">${file}:</span>
                        <span class="error-message">${errorMsg}</span>
                    </div>
                `;
            });
            errorHtml += '</div>';
            statusDiv.innerHTML += errorHtml;
        }

        // Display data table
        this.displayExtractedDataTable(result.table_data);

        // Show chart section
        const chartSection = document.getElementById('chartSection');
        if (chartSection && result.success_count > 0) {
            chartSection.style.display = 'block';
        }
    },

    /**
     * Display extracted data in table format
     */
    displayExtractedDataTable: function (tableData) {
        if (!tableData) return;

        const table = document.getElementById('extractedDataTable');
        const thead = table.querySelector('thead');
        const tbody = table.querySelector('tbody');

        thead.innerHTML = '';
        tbody.innerHTML = '';

        // Create header row
        if (tableData.headers) {
            const headerRow = document.createElement('tr');
            tableData.headers.forEach(header => {
                const th = document.createElement('th');
                th.textContent = header;
                headerRow.appendChild(th);
            });
            thead.appendChild(headerRow);
        }

        // Create data rows
        if (tableData.rows) {
            tableData.rows.forEach(row => {
                const tr = document.createElement('tr');
                row.forEach(cell => {
                    const td = document.createElement('td');
                    td.textContent = cell;
                    tr.appendChild(td);
                });
                tbody.appendChild(tr);
            });
        }
    },

    /**
     * Copy extracted table to clipboard
     */
    copyTableToClipboard: function () {
        if (!this.extractedTableData || !this.extractedTableData.table_data) {
            this.showError('No data to copy');
            return;
        }

        const tabSeparated = this.extractedTableData.table_data.tab_separated;

        navigator.clipboard.writeText(tabSeparated).then(() => {
            this.showToast('表格已复制到剪贴板！');
        }).catch(err => {
            console.error('Failed to copy:', err);
            this.showError('复制到剪贴板失败');
        });
    },

    // 存储生成的图表数据
    generatedCharts: [],

    /**
     * Generate chart from extracted data
     */
    generateChart: async function () {
        if (!this.extractedTableData || !this.extractedTableData.extracted_data) {
            this.showError('没有可用的数据来生成图表');
            return;
        }

        const btn = document.getElementById('generateChartBtn');
        const spinner = document.getElementById('chartLoadingSpinner');
        const container = document.getElementById('chartContainer');
        const sampleSelector = document.getElementById('sampleSelector');
        const sampleSelect = document.getElementById('sampleChartSelect');
        const downloadBtn = document.getElementById('downloadAllChartsBtn');

        btn.disabled = true;
        spinner.classList.remove('d-none');
        container.innerHTML = '';

        try {
            const response = await fetch('/api/pdf/generate-chart', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    extracted_data: this.extractedTableData.extracted_data
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || '生成图表失败');
            }

            const result = await response.json();

            // 存储图表数据
            this.generatedCharts = result.charts || [];

            if (this.generatedCharts.length > 0) {
                // 填充样本选择器
                sampleSelect.innerHTML = '<option value="">-- 请选择样本 --</option>';
                this.generatedCharts.forEach((chart, index) => {
                    const option = document.createElement('option');
                    option.value = index;
                    option.textContent = chart.title;
                    sampleSelect.appendChild(option);
                });

                // 显示样本选择器和下载按钮
                sampleSelector.style.display = 'block';
                downloadBtn.style.display = 'inline-block';

                // 默认显示第一个图表
                sampleSelect.value = '0';
                this.displaySelectedSampleChart('0');
            } else {
                container.innerHTML = '<p class="text-muted">没有生成图表</p>';
                sampleSelector.style.display = 'none';
                downloadBtn.style.display = 'none';
            }

        } catch (error) {
            console.error('Error generating chart:', error);
            this.showError(error.message || '生成图表失败');
            container.innerHTML = `<p class="text-danger">${error.message || '生成图表失败'}</p>`;
        } finally {
            btn.disabled = false;
            spinner.classList.add('d-none');
        }
    },

    /**
     * Display selected sample chart
     */
    displaySelectedSampleChart: function (index) {
        const container = document.getElementById('chartContainer');
        container.innerHTML = '';

        if (index === '' || !this.generatedCharts || !this.generatedCharts[index]) {
            return;
        }

        const chart = this.generatedCharts[index];
        const imgWrapper = document.createElement('div');
        imgWrapper.className = 'chart-wrapper mb-4';

        const img = document.createElement('img');
        img.src = `data:image/png;base64,${chart.base64}`;
        img.alt = chart.title;
        img.className = 'chart-image img-fluid';
        img.style.maxWidth = '100%';

        imgWrapper.appendChild(img);
        container.appendChild(imgWrapper);
    },

    /**
     * Download all charts as ZIP
     */
    downloadAllCharts: async function () {
        if (!this.generatedCharts || this.generatedCharts.length === 0) {
            this.showError('没有可下载的图表');
            return;
        }

        const btn = document.getElementById('downloadAllChartsBtn');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>打包中...';

        try {
            const response = await fetch('/api/pdf/download-charts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    charts: this.generatedCharts
                })
            });

            if (!response.ok) {
                throw new Error('下载失败');
            }

            // 获取ZIP文件
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'bcell_isotype_charts.zip';
            a.click();
            URL.revokeObjectURL(url);

            this.showToast('图表下载成功！');
        } catch (error) {
            console.error('Error downloading charts:', error);
            this.showError('下载图表失败');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-download me-1"></i>下载所有图表';
        }
    },

    // =========================================================================
    // Image Extraction - Requirements: 12.1-12.6
    // =========================================================================

    /**
     * List images in selected PDF
     */
    listImages: async function () {
        const fileId = document.getElementById('imageFileSelect').value;
        if (!fileId) {
            this.showError('请选择一个PDF文件');
            return;
        }

        const btn = document.getElementById('listImagesBtn');
        const spinner = document.getElementById('imageListSpinner');
        btn.disabled = true;
        spinner.classList.remove('d-none');

        try {
            const response = await fetch(`/api/pdf/images/${fileId}`);

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || 'Failed to list images');
            }

            const result = await response.json();
            this.currentPdfImages = result.images;
            this.displayImageThumbnails(result);

        } catch (error) {
            console.error('Error listing images:', error);
            this.showError(error.message || '列出图像失败');
        } finally {
            btn.disabled = false;
            spinner.classList.add('d-none');
        }
    },

    /**
     * Display image thumbnails
     */
    displayImageThumbnails: function (result) {
        const section = document.getElementById('imageThumbnailsSection');
        section.classList.remove('d-none');

        document.getElementById('imageCount').textContent = result.total_count;

        const grid = document.getElementById('thumbnailGrid');
        grid.innerHTML = '';

        if (result.images.length === 0) {
            grid.innerHTML = '<p class="text-muted">No images found in this PDF</p>';
            return;
        }

        const self = this;
        result.images.forEach(img => {
            const item = document.createElement('div');
            item.className = 'thumbnail-item';
            item.dataset.index = img.index;

            item.innerHTML = `
                <span class="thumbnail-index">#${img.index}</span>
                <input type="checkbox" class="thumbnail-checkbox" data-index="${img.index}">
                ${img.thumbnail ?
                    `<img src="data:image/png;base64,${img.thumbnail}" alt="Image ${img.index}">` :
                    '<div class="text-muted">No preview</div>'
                }
                <div class="thumbnail-info">
                    ${img.width}x${img.height}<br>
                    Page ${img.page_number}
                </div>
            `;

            const checkbox = item.querySelector('.thumbnail-checkbox');
            checkbox.addEventListener('change', function () {
                self.onImageToggle(img.index, this.checked);
                item.classList.toggle('selected', this.checked);
            });

            item.addEventListener('click', function (e) {
                if (e.target !== checkbox) {
                    checkbox.checked = !checkbox.checked;
                    checkbox.dispatchEvent(new Event('change'));
                }
            });

            grid.appendChild(item);
        });

        this.updateExtractSelectedButton();
    },

    /**
     * Handle image selection toggle
     */
    onImageToggle: function (index, selected) {
        if (selected) {
            this.selectedImageIndices.add(index);
        } else {
            this.selectedImageIndices.delete(index);
        }
        this.updateExtractSelectedButton();
    },

    /**
     * Update extract selected button state
     */
    updateExtractSelectedButton: function () {
        document.getElementById('extractSelectedImagesBtn').disabled =
            this.selectedImageIndices.size === 0;
    },

    /**
     * Select all images
     */
    selectAllImages: function () {
        const checkboxes = document.querySelectorAll('.thumbnail-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = true;
            cb.dispatchEvent(new Event('change'));
        });
    },

    /**
     * Deselect all images
     */
    deselectAllImages: function () {
        const checkboxes = document.querySelectorAll('.thumbnail-checkbox');
        checkboxes.forEach(cb => {
            cb.checked = false;
            cb.dispatchEvent(new Event('change'));
        });
    },

    /**
     * Select images by indices from input
     */
    selectByIndices: function () {
        const indicesStr = document.getElementById('imageIndices').value;
        const indices = this.parseIndices(indicesStr);

        // Resolve negative indices
        const totalImages = this.currentPdfImages.length;
        const resolvedIndices = new Set();

        indices.forEach(idx => {
            let resolved = idx;
            if (idx < 0) {
                resolved = totalImages + idx;
            }
            if (resolved >= 0 && resolved < totalImages) {
                resolvedIndices.add(resolved);
            }
        });

        // Update checkboxes
        const checkboxes = document.querySelectorAll('.thumbnail-checkbox');
        checkboxes.forEach(cb => {
            const index = parseInt(cb.dataset.index);
            cb.checked = resolvedIndices.has(index);
            cb.dispatchEvent(new Event('change'));
        });
    },

    /**
     * Parse indices string to array
     */
    parseIndices: function (str) {
        return str.split(',')
            .map(s => parseInt(s.trim()))
            .filter(n => !isNaN(n));
    },

    /**
     * Extract selected images from current PDF
     */
    extractSelectedImages: async function () {
        const fileId = document.getElementById('imageFileSelect').value;
        if (!fileId || this.selectedImageIndices.size === 0) {
            this.showError('请选择要提取的图像');
            return;
        }

        const indices = Array.from(this.selectedImageIndices);
        await this.extractImagesFromFiles([fileId], indices);
    },

    /**
     * Batch extract images from multiple PDFs
     */
    batchExtractImages: async function () {
        if (this.selectedBatchFiles.size === 0) {
            this.showError('请至少选择一个PDF文件');
            return;
        }

        const indicesInput = document.getElementById('imageIndices');
        const indicesStr = indicesInput ? indicesInput.value : '16, -1';
        const indices = this.parseIndices(indicesStr);

        if (indices.length === 0) {
            // 使用默认索引
            indices.push(...this.defaultImageIndices);
        }

        const btn = document.getElementById('batchExtractBtn');
        const spinner = document.getElementById('batchExtractSpinner');
        btn.disabled = true;
        spinner.classList.remove('d-none');

        try {
            await this.extractImagesFromFiles(
                Array.from(this.selectedBatchFiles),
                indices
            );
        } finally {
            btn.disabled = false;
            spinner.classList.add('d-none');
        }
    },

    /**
     * Extract images from files
     */
    extractImagesFromFiles: async function (fileIds, indices) {
        try {
            const response = await fetch('/api/pdf/extract-images', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    file_ids: fileIds,
                    indices: indices
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || 'Extraction failed');
            }

            const result = await response.json();
            this.extractedImages = result.extracted_images;
            this.displayExtractedImages(result);

        } catch (error) {
            console.error('Error extracting images:', error);
            this.showError(error.message || '提取图像失败');
        }
    },

    /**
     * Display extracted images - grouped by PDF
     */
    displayExtractedImages: function (result) {
        const section = document.getElementById('extractedImagesSection');
        if (!section) {
            console.warn('extractedImagesSection not found');
            this.showToast('图像提取成功！');
            return;
        }
        section.classList.remove('d-none');

        // 存储提取的图像数据
        this.extractedImages = result.extracted_images;

        // 填充PDF选择器
        const pdfSelect = document.getElementById('pdfImageSelect');
        if (pdfSelect) {
            pdfSelect.innerHTML = '<option value="">-- 请选择PDF --</option>';
            const pdfNames = Object.keys(result.extracted_images);
            pdfNames.forEach((name, index) => {
                const option = document.createElement('option');
                option.value = name;
                option.textContent = name;
                pdfSelect.appendChild(option);
            });

            // 默认显示第一个PDF的图像
            if (pdfNames.length > 0) {
                pdfSelect.value = pdfNames[0];
                this.displayPdfImages(pdfNames[0]);
            }
        }
    },

    /**
     * Display images for selected PDF
     */
    displayPdfImages: function (pdfName) {
        const grid = document.getElementById('extractedImagesGrid');
        if (!grid) return;

        grid.innerHTML = '';

        const images = this.extractedImages[pdfName];
        if (!images || images.length === 0) {
            grid.innerHTML = '<p class="text-muted">该PDF没有提取到图像</p>';
            return;
        }

        images.forEach(imgData => {
            const col = document.createElement('div');
            col.className = 'col-md-6 col-lg-4 mb-3';

            col.innerHTML = `
            <div class="card">
                <img src="data:image/png;base64,${imgData.image}" class="card-img-top" alt="Extracted image">
                <div class="card-body p-2">
                    <small class="text-muted">Index: ${imgData.index}</small>
                </div>
            </div>
        `;

            grid.appendChild(col);
        });
    },

    /**
     * Download all extracted images as ZIP
     */
    downloadAllImages: async function () {
        if (!this.extractedImages || Object.keys(this.extractedImages).length === 0) {
            this.showError('没有可下载的图像');
            return;
        }

        const btn = document.getElementById('downloadAllImagesBtn');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>打包中...';

        try {
            const response = await fetch('/api/pdf/download-images', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    images: this.extractedImages
                })
            });

            if (!response.ok) {
                throw new Error('下载失败');
            }

            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'extracted_images.zip';
            a.click();
            URL.revokeObjectURL(url);

            this.showToast('图像下载成功！');
        } catch (error) {
            console.error('Error downloading images:', error);
            this.showError('下载图像失败');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-download me-1"></i>下载全部(ZIP)';
        }
    },

    /**
     * Download a single image (legacy)
     */
    downloadImage: function (base64Data, filename, index) {
        const link = document.createElement('a');
        link.href = `data:image/png;base64,${base64Data}`;
        const baseName = filename.replace('.pdf', '');
        link.download = `${baseName}_image_${index}.png`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    },

    /**
     * Legacy download all images (replaced by ZIP download)
     */
    downloadAllImagesLegacy: function () {
        Object.entries(this.extractedImages).forEach(([filename, images]) => {
            images.forEach(imgData => {
                this.downloadImage(imgData.image, filename, imgData.index);
            });
        });
    },

    // =========================================================================
    // Utility Functions
    // =========================================================================

    /**
     * Show error message
     */
    showError: function (message) {
        // Create a more user-friendly error display
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger alert-dismissible fade show';
        errorDiv.setAttribute('role', 'alert');
        errorDiv.innerHTML = `
            <i class="bi bi-exclamation-triangle-fill me-2"></i>
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;

        // Insert at the top of the active tab
        const activeTab = document.querySelector('.tab-pane.active');
        if (activeTab) {
            activeTab.insertBefore(errorDiv, activeTab.firstChild);

            // Auto-dismiss after 5 seconds
            setTimeout(() => {
                errorDiv.remove();
            }, 5000);
        } else {
            // Fallback to alert
            alert(message);
        }
    },

    /**
     * Show toast notification
     */
    showToast: function (message) {
        const toast = document.createElement('div');
        toast.className = 'copy-toast';
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 2000);
    },

    // =========================================================================
    // Directory Browser Functions
    // =========================================================================

    /**
     * Show directory browser
     */
    showDirectoryBrowser: function () {
        const browser = document.getElementById('directoryBrowser');
        browser.classList.remove('d-none');
        this.loadDirectories();
    },

    /**
     * Hide directory browser
     */
    hideDirectoryBrowser: function () {
        const browser = document.getElementById('directoryBrowser');
        browser.classList.add('d-none');
    },

    /**
     * Load directories
     */
    loadDirectories: async function (parentPath = null) {
        const listDiv = document.getElementById('directoryList');
        listDiv.innerHTML = '<p class="text-muted">加载目录中...</p>';

        try {
            const url = parentPath
                ? `/api/browse-directory?path=${encodeURIComponent(parentPath)}`
                : '/api/browse-directory';

            const response = await fetch(url);

            if (!response.ok) {
                throw new Error('加载目录失败');
            }

            const data = await response.json();
            this.displayDirectories(data);

        } catch (error) {
            console.error('Error loading directories:', error);
            listDiv.innerHTML = '<p class="text-danger">加载目录失败</p>';
        }
    },

    /**
     * Display directories
     */
    displayDirectories: function (data) {
        const listDiv = document.getElementById('directoryList');
        listDiv.innerHTML = '';

        // Show current path
        const pathDiv = document.createElement('div');
        pathDiv.className = 'mb-2';
        pathDiv.innerHTML = `<strong>当前路径:</strong> ${data.current_path}`;
        listDiv.appendChild(pathDiv);

        // Show parent directory link
        if (data.parent_path) {
            const parentLink = document.createElement('div');
            parentLink.className = 'directory-item';
            parentLink.innerHTML = `
                <i class="bi bi-arrow-up"></i>
                <span>.. (上级目录)</span>
            `;
            parentLink.style.cursor = 'pointer';
            parentLink.addEventListener('click', () => {
                this.loadDirectories(data.parent_path);
            });
            listDiv.appendChild(parentLink);
        }

        // Show directories
        if (data.items && data.items.length > 0) {
            data.items.forEach(item => {
                if (item.type === 'directory') {
                    const itemDiv = document.createElement('div');
                    itemDiv.className = 'directory-item';
                    itemDiv.innerHTML = `
                        <i class="bi bi-folder"></i>
                        <span>${item.name}</span>
                    `;
                    itemDiv.style.cursor = 'pointer';
                    itemDiv.addEventListener('click', () => {
                        this.loadDirectories(item.path);
                    });
                    listDiv.appendChild(itemDiv);
                }
            });
        } else {
            listDiv.innerHTML += '<p class="text-muted">此目录为空</p>';
        }

        // Store current path for selection
        this.currentDirectoryPath = data.current_path;
    },

    /**
     * Select directory
     */
    selectDirectory: function () {
        if (this.currentDirectoryPath) {
            document.getElementById('outputPath').value = this.currentDirectoryPath;
            this.hideDirectoryBrowser();

            // Enable extract button if we have images selected
            const extractBtn = document.getElementById('extractImagesBtn');
            if (extractBtn && this.selectedImageIndices.size > 0) {
                extractBtn.disabled = false;
            }
        }
    }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function () {
    PDFExtractorModule.init();
});
