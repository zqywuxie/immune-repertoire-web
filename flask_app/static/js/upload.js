/**
 * File Upload Module
 * Handles file upload functionality with drag and drop support
 */
const FileUploader = {
    acceptedFormats: ['.csv', '.xlsx', '.csv.gz', '.pdf'],
    maxFileSize: 100 * 1024 * 1024, // 100MB
    projects: [],
    uploadQueue: [],
    isUploading: false,
    uploadResults: { success: 0, failed: 0, total: 0 },

    init() {
        this.loadProjects();
        this.bindEvents();
    },

    async loadProjects() {
        try {
            const response = await fetch('/api/files/projects');
            if (!response.ok) return;

            const data = await response.json();
            this.projects = data.projects || [];
            this.populateProjectSelect();
        } catch (error) {
            console.error('Error loading projects:', error);
        }
    },

    populateProjectSelect() {
        const select = document.getElementById('projectSelect');
        if (!select) return;

        const currentValue = select.value;
        select.innerHTML = '';

        this.projects.forEach(project => {
            const option = document.createElement('option');
            option.value = project;
            option.textContent = project === 'default' ? '默认项目' : project;
            if (project === currentValue) option.selected = true;
            select.appendChild(option);
        });

        // Ensure default is selected if nothing else
        if (!select.value && this.projects.includes('default')) {
            select.value = 'default';
        }
    },

    createNewProject() {
        const projectName = prompt('请输入新项目名称:');
        if (!projectName || !projectName.trim()) return;

        const trimmedName = projectName.trim();
        if (!this.projects.includes(trimmedName)) {
            this.projects.push(trimmedName);
        }

        this.populateProjectSelect();
        document.getElementById('projectSelect').value = trimmedName;
    },

    bindEvents() {
        const uploadArea = document.getElementById('uploadArea');
        const fileInput = document.getElementById('fileInput');
        const newProjectBtn = document.getElementById('newProjectBtn');

        if (fileInput) {
            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    if (e.target.files.length === 1) {
                        this.uploadFile(e.target.files[0]);
                    } else {
                        this.uploadMultipleFiles(e.target.files);
                    }
                }
            });
        }

        if (newProjectBtn) {
            newProjectBtn.addEventListener('click', () => this.createNewProject());
        }

        if (uploadArea) {
            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.classList.add('drag-over');
            });

            uploadArea.addEventListener('dragleave', () => {
                uploadArea.classList.remove('drag-over');
            });

            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadArea.classList.remove('drag-over');
                if (e.dataTransfer.files.length > 0) {
                    if (e.dataTransfer.files.length === 1) {
                        this.uploadFile(e.dataTransfer.files[0]);
                    } else {
                        this.uploadMultipleFiles(e.dataTransfer.files);
                    }
                }
            });
        }
    },

    validateFormat(filename) {
        const lower = filename.toLowerCase();
        return this.acceptedFormats.some(ext => lower.endsWith(ext));
    },

    async uploadFile(file) {
        if (!this.validateFormat(file.name)) {
            this.showError('不支持的文件格式。请上传 CSV, XLSX 或 CSV.GZ 文件。');
            return;
        }

        if (file.size > this.maxFileSize) {
            this.showError('文件大小超过限制 (最大 100MB)');
            return;
        }

        this.showProgress(file.name);

        const formData = new FormData();
        formData.append('file', file);

        // Add project to form data
        const projectSelect = document.getElementById('projectSelect');
        const project = projectSelect?.value || 'default';
        formData.append('project', project);

        // Determine upload endpoint based on file type
        const isPdf = file.name.toLowerCase().endsWith('.pdf');
        const uploadUrl = isPdf ? '/api/pdf/upload' : '/api/files/upload';

        try {
            const xhr = new XMLHttpRequest();

            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    this.updateProgress(percent);
                }
            });

            xhr.addEventListener('load', () => {
                if (xhr.status === 201) {
                    const result = JSON.parse(xhr.responseText);
                    this.showSuccess(result, isPdf);
                } else {
                    const error = JSON.parse(xhr.responseText);
                    this.showError(error.message || '上传失败');
                }
            });

            xhr.addEventListener('error', () => {
                this.showError('网络错误，请重试');
            });

            xhr.open('POST', uploadUrl);
            xhr.send(formData);
        } catch (error) {
            this.showError(error.message);
        }
    },

    showProgress(filename) {
        const uploadArea = document.getElementById('uploadArea');
        const uploadSuccess = document.getElementById('uploadSuccess');
        const uploadError = document.getElementById('uploadError');
        const progressContainer = document.getElementById('progressContainer');
        const fileName = document.getElementById('fileName');

        if (uploadArea) uploadArea.classList.add('d-none');
        if (uploadSuccess) uploadSuccess.classList.add('d-none');
        if (uploadError) uploadError.classList.add('d-none');
        if (progressContainer) progressContainer.classList.remove('d-none');
        if (fileName) fileName.textContent = filename;
        this.updateProgress(0);
    },

    updateProgress(percent) {
        const progressPercent = document.getElementById('progressPercent');
        const progressBar = document.getElementById('progressBar');

        if (progressPercent) progressPercent.textContent = percent + '%';
        if (progressBar) progressBar.style.width = percent + '%';
    },

    showSuccess(result, isPdf = false) {
        const progressContainer = document.getElementById('progressContainer');
        const uploadSuccess = document.getElementById('uploadSuccess');
        const successMessage = document.getElementById('successMessage');

        if (progressContainer) progressContainer.classList.add('d-none');
        if (uploadSuccess) uploadSuccess.classList.remove('d-none');
        if (successMessage) {
            if (isPdf) {
                successMessage.textContent =
                    `PDF文件 "${result.filename}" 上传成功！共 ${result.page_count} 页。`;
            } else {
                successMessage.textContent =
                    `文件 "${result.name}" 上传成功！检测到 ${result.columns.length} 列，${result.row_count.toLocaleString()} 行数据。`;
            }
        }
    },

    showError(message) {
        const progressContainer = document.getElementById('progressContainer');
        const uploadArea = document.getElementById('uploadArea');
        const uploadError = document.getElementById('uploadError');
        const errorMessage = document.getElementById('errorMessage');

        if (progressContainer) progressContainer.classList.add('d-none');
        if (uploadArea) uploadArea.classList.add('d-none');
        if (uploadError) uploadError.classList.remove('d-none');
        if (errorMessage) errorMessage.textContent = message;
    },

    reset() {
        const uploadArea = document.getElementById('uploadArea');
        const progressContainer = document.getElementById('progressContainer');
        const uploadSuccess = document.getElementById('uploadSuccess');
        const uploadError = document.getElementById('uploadError');
        const fileInput = document.getElementById('fileInput');
        const batchProgressContainer = document.getElementById('batchProgressContainer');

        if (uploadArea) uploadArea.classList.remove('d-none');
        if (progressContainer) progressContainer.classList.add('d-none');
        if (uploadSuccess) uploadSuccess.classList.add('d-none');
        if (uploadError) uploadError.classList.add('d-none');
        if (batchProgressContainer) batchProgressContainer.classList.add('d-none');
        if (fileInput) fileInput.value = '';

        this.uploadQueue = [];
        this.isUploading = false;
        this.uploadResults = { success: 0, failed: 0, total: 0 };
    },

    async uploadMultipleFiles(files) {
        const validFiles = [];
        const invalidFiles = [];

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            if (!this.validateFormat(file.name)) {
                invalidFiles.push({ name: file.name, error: '不支持的格式' });
            } else if (file.size > this.maxFileSize) {
                invalidFiles.push({ name: file.name, error: '文件过大' });
            } else {
                validFiles.push(file);
            }
        }

        if (validFiles.length === 0) {
            this.showError('没有有效的文件可以上传');
            return;
        }

        this.uploadResults = { success: 0, failed: invalidFiles.length, total: files.length };
        this.showBatchProgress(validFiles, invalidFiles);

        for (let i = 0; i < validFiles.length; i++) {
            await this.uploadSingleFileInBatch(validFiles[i], i);
        }

        this.showBatchComplete();
    },

    showBatchProgress(validFiles, invalidFiles) {
        const uploadArea = document.getElementById('uploadArea');
        const batchProgressContainer = document.getElementById('batchProgressContainer');
        const batchFileList = document.getElementById('batchFileList');
        const batchProgressBadge = document.getElementById('batchProgressBadge');

        if (uploadArea) uploadArea.classList.add('d-none');
        if (batchProgressContainer) batchProgressContainer.classList.remove('d-none');

        batchProgressBadge.textContent = `0/${validFiles.length + invalidFiles.length}`;

        let html = '';

        validFiles.forEach((file, idx) => {
            html += `
                <div class="list-group-item d-flex justify-content-between align-items-center" id="batchFile${idx}">
                    <div>
                        <i class="bi bi-file-earmark me-2"></i>
                        <span class="file-name">${this.escapeHtml(file.name)}</span>
                        <small class="text-muted ms-2">(${this.formatFileSize(file.size)})</small>
                    </div>
                    <div class="batch-status">
                        <span class="badge bg-secondary">等待中</span>
                    </div>
                </div>
            `;
        });

        invalidFiles.forEach((file, idx) => {
            html += `
                <div class="list-group-item d-flex justify-content-between align-items-center list-group-item-danger">
                    <div>
                        <i class="bi bi-file-earmark-x me-2"></i>
                        <span class="file-name">${this.escapeHtml(file.name)}</span>
                    </div>
                    <div>
                        <span class="badge bg-danger">${file.error}</span>
                    </div>
                </div>
            `;
        });

        batchFileList.innerHTML = html;
    },

    async uploadSingleFileInBatch(file, index) {
        const fileItem = document.getElementById(`batchFile${index}`);
        const statusDiv = fileItem?.querySelector('.batch-status');

        if (statusDiv) {
            statusDiv.innerHTML = `
                <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
                <span class="ms-2 text-primary">上传中...</span>
            `;
        }

        const formData = new FormData();
        formData.append('file', file);
        const projectSelect = document.getElementById('projectSelect');
        formData.append('project', projectSelect?.value || 'default');

        const isPdf = file.name.toLowerCase().endsWith('.pdf');
        const uploadUrl = isPdf ? '/api/pdf/upload' : '/api/files/upload';

        return new Promise((resolve) => {
            const xhr = new XMLHttpRequest();

            xhr.addEventListener('load', () => {
                if (xhr.status === 201) {
                    this.uploadResults.success++;
                    if (statusDiv) {
                        statusDiv.innerHTML = '<span class="badge bg-success"><i class="bi bi-check"></i> 成功</span>';
                    }
                    if (fileItem) fileItem.classList.add('list-group-item-success');
                } else {
                    this.uploadResults.failed++;
                    if (statusDiv) {
                        statusDiv.innerHTML = '<span class="badge bg-danger"><i class="bi bi-x"></i> 失败</span>';
                    }
                    if (fileItem) fileItem.classList.add('list-group-item-danger');
                }
                this.updateBatchBadge();
                resolve();
            });

            xhr.addEventListener('error', () => {
                this.uploadResults.failed++;
                if (statusDiv) {
                    statusDiv.innerHTML = '<span class="badge bg-danger"><i class="bi bi-x"></i> 网络错误</span>';
                }
                if (fileItem) fileItem.classList.add('list-group-item-danger');
                this.updateBatchBadge();
                resolve();
            });

            xhr.open('POST', uploadUrl);
            xhr.send(formData);
        });
    },

    updateBatchBadge() {
        const badge = document.getElementById('batchProgressBadge');
        const completed = this.uploadResults.success + this.uploadResults.failed;
        if (badge) {
            badge.textContent = `${completed}/${this.uploadResults.total}`;
        }
    },

    showBatchComplete() {
        const uploadSuccess = document.getElementById('uploadSuccess');
        const successMessage = document.getElementById('successMessage');
        const batchProgressContainer = document.getElementById('batchProgressContainer');

        if (uploadSuccess) uploadSuccess.classList.remove('d-none');

        let msg = `批量上传完成！成功 ${this.uploadResults.success} 个文件`;
        if (this.uploadResults.failed > 0) {
            msg += `，失败 ${this.uploadResults.failed} 个文件`;
        }
        if (successMessage) successMessage.textContent = msg;
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    },

    formatFileSize(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
};

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('uploadArea') || document.getElementById('fileInput')) {
        FileUploader.init();
    }
});
