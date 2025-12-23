/**
 * FileUploader - Reusable file upload component
 * Supports both selecting existing files and uploading new files
 * Can operate in single or multiple file mode
 */
class FileUploader {
    constructor(options = {}) {
        this.options = {
            containerId: options.containerId || 'fileUploaderContainer',
            onFileSelected: options.onFileSelected || null,
            onUploadComplete: options.onUploadComplete || null,
            onUploadError: options.onUploadError || null,
            onMultipleFilesSelected: options.onMultipleFilesSelected || null,
            acceptedFormats: options.acceptedFormats || '.csv,.xlsx,.xls,.pdf',
            maxFileSize: options.maxFileSize || 50 * 1024 * 1024, // 50MB default
            uploadEndpoint: options.uploadEndpoint || '/api/files/upload',
            multipleUploadEndpoint: options.multipleUploadEndpoint || '/api/files/upload-multiple',
            multiple: options.multiple || false // Enable multiple file mode
        };

        this.selectedFileId = null;
        this.selectedFileName = null;
        this.currentFile = null;
        this.selectedFiles = []; // For multiple file mode
        this.allFiles = []; // Store all files for filtering
        this.projects = []; // Store project list
        this.currentProject = ''; // Current selected project

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadProjects();
        this.loadExistingFiles();
    }

    setupEventListeners() {
        // Radio button toggle
        const existingRadio = document.getElementById('existingFileRadio');
        const newRadio = document.getElementById('newFileRadio');
        const existingSection = document.getElementById('existingFileSection');
        const newSection = document.getElementById('newFileSection');

        if (existingRadio && newRadio) {
            existingRadio.addEventListener('change', () => {
                existingSection.classList.remove('d-none');
                newSection.classList.add('d-none');
                this.resetUploadState();
            });

            newRadio.addEventListener('change', () => {
                existingSection.classList.add('d-none');
                newSection.classList.remove('d-none');
            });
        }

        // Project filter selection
        const projectFilterSelect = document.getElementById('projectFilterSelect');
        if (projectFilterSelect) {
            projectFilterSelect.addEventListener('change', (e) => {
                this.currentProject = e.target.value;
                this.filterFilesByProject();
            });
        }

        // Existing file selection
        const existingFileSelect = document.getElementById('existingFileSelect');
        if (existingFileSelect) {
            existingFileSelect.addEventListener('change', (e) => {
                this.handleExistingFileSelection(e.target.value);
            });
        }

        // New file input
        const newFileInput = document.getElementById('newFileInput');
        if (newFileInput) {
            // Set multiple attribute if in multiple mode
            if (this.options.multiple) {
                newFileInput.setAttribute('multiple', 'true');
            }

            newFileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    if (this.options.multiple) {
                        this.handleMultipleFileSelection(e.target.files);
                    } else {
                        this.handleNewFileSelection(e.target.files[0]);
                    }
                }
            });
        }

        // Drag and drop
        const dropZone = document.getElementById('uploadDropZone');
        if (dropZone) {
            dropZone.addEventListener('click', () => {
                newFileInput?.click();
            });

            dropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropZone.classList.add('drag-over');
            });

            dropZone.addEventListener('dragleave', () => {
                dropZone.classList.remove('drag-over');
            });

            dropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropZone.classList.remove('drag-over');

                if (e.dataTransfer.files.length > 0) {
                    if (this.options.multiple) {
                        this.handleMultipleFileSelection(e.dataTransfer.files);
                    } else {
                        this.handleNewFileSelection(e.dataTransfer.files[0]);
                    }
                }
            });
        }
    }

    async loadProjects() {
        try {
            const response = await fetch('/api/files/projects');
            if (!response.ok) return;

            const data = await response.json();
            this.projects = data.projects || [];

            const select = document.getElementById('projectFilterSelect');
            if (select) {
                select.innerHTML = '<option value="">全部项目</option>';
                this.projects.forEach(project => {
                    const option = document.createElement('option');
                    option.value = project;
                    option.textContent = project === 'default' ? '默认项目' : project;
                    select.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Error loading projects:', error);
        }
    }

    async loadExistingFiles() {
        try {
            const response = await fetch('/api/files');
            if (!response.ok) throw new Error('Failed to load files');

            const data = await response.json();
            this.allFiles = data.files || [];
            this.filterFilesByProject();
        } catch (error) {
            console.error('Error loading files:', error);
            this.showError('加载文件列表失败');
        }
    }

    filterFilesByProject() {
        const select = document.getElementById('existingFileSelect');
        if (!select) return;

        // Filter files by project and exclude PDF files
        let filteredFiles = this.allFiles.filter(f => {
            const name = (f.name || f.filename || f.original_name || '').toLowerCase();
            return !name.endsWith('.pdf');
        });
        if (this.currentProject) {
            filteredFiles = filteredFiles.filter(f => f.project === this.currentProject);
        }

        // Update file select options
        select.innerHTML = '<option value="">-- 选择文件 --</option>';
        filteredFiles.forEach(file => {
            const option = document.createElement('option');
            option.value = file.id;
            const fileName = file.name || file.filename || file.original_name || '未知文件';
            option.textContent = `${fileName} (${this.formatFileSize(file.size)})`;
            option.setAttribute('data-filename', fileName);
            option.setAttribute('data-project', file.project || 'default');
            select.appendChild(option);
        });

        // Reset selection
        this.selectedFileId = null;
        this.selectedFileName = null;
        this.hideFileInfo();
    }

    handleExistingFileSelection(fileId) {
        if (!fileId) {
            this.selectedFileId = null;
            this.selectedFileName = null;
            this.hideFileInfo();
            return;
        }

        const select = document.getElementById('existingFileSelect');
        const selectedOption = select.options[select.selectedIndex];

        this.selectedFileId = fileId;
        // Get file name from data attribute or text content
        this.selectedFileName = selectedOption.getAttribute('data-filename') || selectedOption.textContent;

        this.showFileInfo(this.selectedFileName);

        if (this.options.onFileSelected) {
            this.options.onFileSelected({
                fileId: this.selectedFileId,
                fileName: this.selectedFileName,
                source: 'existing'
            });
        }
    }

    async handleNewFileSelection(file) {
        // Validate file
        if (!this.validateFile(file)) {
            return;
        }

        this.currentFile = file;
        this.resetUploadState();

        // Start upload
        await this.uploadFile(file);
    }

    async handleMultipleFileSelection(files) {
        // Validate all files
        const validFiles = [];
        const invalidFiles = [];

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            if (this.validateFile(file)) {
                validFiles.push(file);
            } else {
                invalidFiles.push({
                    filename: file.name,
                    error: 'Validation failed'
                });
            }
        }

        if (validFiles.length === 0) {
            this.showError('没有有效的文件可以上传');
            return;
        }

        this.selectedFiles = validFiles;
        this.resetUploadState();

        // Start multiple file upload
        await this.uploadMultipleFiles(validFiles);
    }

    validateFile(file) {
        // Check file size
        if (file.size > this.options.maxFileSize) {
            this.showError(`文件大小超过限制 (${this.formatFileSize(this.options.maxFileSize)})`);
            return false;
        }

        // Check file type
        const extension = '.' + file.name.split('.').pop().toLowerCase();
        const acceptedFormats = this.options.acceptedFormats.split(',');

        if (!acceptedFormats.includes(extension)) {
            this.showError(`不支持的文件格式。支持的格式: ${this.options.acceptedFormats}`);
            return false;
        }

        return true;
    }

    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        const progressBar = document.getElementById('uploadProgressBar');
        const progressPercentage = document.getElementById('uploadPercentage');
        const progressContainer = document.getElementById('uploadProgress');

        try {
            // Show progress
            progressContainer.classList.remove('d-none');

            const xhr = new XMLHttpRequest();

            // Track upload progress
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percentComplete = Math.round((e.loaded / e.total) * 100);
                    progressBar.style.width = percentComplete + '%';
                    progressPercentage.textContent = percentComplete + '%';
                }
            });

            // Handle completion
            xhr.addEventListener('load', () => {
                if (xhr.status === 200 || xhr.status === 201) {
                    const response = JSON.parse(xhr.responseText);
                    this.handleUploadSuccess(response);
                } else {
                    const error = JSON.parse(xhr.responseText);
                    this.handleUploadError(error.error || '上传失败');
                }
            });

            // Handle errors
            xhr.addEventListener('error', () => {
                this.handleUploadError('网络错误，上传失败');
            });

            xhr.open('POST', this.options.uploadEndpoint);
            xhr.send(formData);

        } catch (error) {
            console.error('Upload error:', error);
            this.handleUploadError(error.message || '上传失败');
        }
    }

    async uploadMultipleFiles(files) {
        const formData = new FormData();

        // Add all files to FormData
        files.forEach(file => {
            formData.append('files', file);
        });

        const progressBar = document.getElementById('uploadProgressBar');
        const progressPercentage = document.getElementById('uploadPercentage');
        const progressContainer = document.getElementById('uploadProgress');

        try {
            // Show progress
            progressContainer.classList.remove('d-none');

            const xhr = new XMLHttpRequest();

            // Track upload progress
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percentComplete = Math.round((e.loaded / e.total) * 100);
                    progressBar.style.width = percentComplete + '%';
                    progressPercentage.textContent = percentComplete + '%';
                }
            });

            // Handle completion
            xhr.addEventListener('load', () => {
                if (xhr.status === 200 || xhr.status === 201) {
                    const response = JSON.parse(xhr.responseText);
                    this.handleMultipleUploadSuccess(response);
                } else {
                    const error = JSON.parse(xhr.responseText);
                    this.handleUploadError(error.error || '上传失败');
                }
            });

            // Handle errors
            xhr.addEventListener('error', () => {
                this.handleUploadError('网络错误，上传失败');
            });

            xhr.open('POST', this.options.multipleUploadEndpoint);
            xhr.send(formData);

        } catch (error) {
            console.error('Upload error:', error);
            this.handleUploadError(error.message || '上传失败');
        }
    }

    handleMultipleUploadSuccess(response) {
        const progressContainer = document.getElementById('uploadProgress');
        const successContainer = document.getElementById('uploadSuccess');
        const successMessage = document.getElementById('uploadSuccessMessage');

        progressContainer.classList.add('d-none');
        successContainer.classList.remove('d-none');

        // Display success message with upload summary
        const { uploaded_files, total_uploaded, total_errors } = response;
        let message = `成功上传 ${total_uploaded} 个文件`;
        if (total_errors > 0) {
            message += `，${total_errors} 个文件上传失败`;
        }
        successMessage.textContent = message;

        // Store uploaded files
        this.selectedFiles = uploaded_files;

        // Reload existing files list
        this.loadExistingFiles();

        if (this.options.onMultipleFilesSelected) {
            this.options.onMultipleFilesSelected({
                uploadedFiles: uploaded_files,
                totalUploaded: total_uploaded,
                totalErrors: total_errors,
                errors: response.errors || []
            });
        }

        if (this.options.onUploadComplete) {
            this.options.onUploadComplete({
                multiple: true,
                uploadedFiles: uploaded_files,
                response: response
            });
        }
    }

    handleUploadSuccess(response) {
        const progressContainer = document.getElementById('uploadProgress');
        const successContainer = document.getElementById('uploadSuccess');
        const successMessage = document.getElementById('uploadSuccessMessage');

        progressContainer.classList.add('d-none');
        successContainer.classList.remove('d-none');

        // Handle both 'name' and 'filename' fields from API response
        const fileName = response.name || response.filename || response.original_name || '未知文件';
        successMessage.textContent = `文件 "${fileName}" 上传成功`;

        this.selectedFileId = response.id || response.file_id;
        this.selectedFileName = fileName;

        this.showFileInfo(this.selectedFileName);

        // Reload existing files list
        this.loadExistingFiles();

        if (this.options.onUploadComplete) {
            this.options.onUploadComplete({
                fileId: this.selectedFileId,
                fileName: this.selectedFileName,
                source: 'new',
                response: response
            });
        }

        if (this.options.onFileSelected) {
            this.options.onFileSelected({
                fileId: this.selectedFileId,
                fileName: this.selectedFileName,
                source: 'new'
            });
        }
    }

    handleUploadError(errorMessage) {
        const progressContainer = document.getElementById('uploadProgress');
        const errorContainer = document.getElementById('uploadError');
        const errorMessageEl = document.getElementById('uploadErrorMessage');

        progressContainer.classList.add('d-none');
        errorContainer.classList.remove('d-none');
        errorMessageEl.textContent = errorMessage;

        if (this.options.onUploadError) {
            this.options.onUploadError(errorMessage);
        }
    }

    showFileInfo(fileName) {
        const fileInfo = document.getElementById('selectedFileInfo');
        const fileNameEl = document.getElementById('selectedFileName');

        if (fileInfo && fileNameEl) {
            fileNameEl.textContent = fileName;
            fileInfo.classList.remove('d-none');
        }
    }

    hideFileInfo() {
        const fileInfo = document.getElementById('selectedFileInfo');
        if (fileInfo) {
            fileInfo.classList.add('d-none');
        }
    }

    showError(message) {
        const errorContainer = document.getElementById('uploadError');
        const errorMessage = document.getElementById('uploadErrorMessage');

        if (errorContainer && errorMessage) {
            errorMessage.textContent = message;
            errorContainer.classList.remove('d-none');
        }
    }

    resetUploadState() {
        const progressContainer = document.getElementById('uploadProgress');
        const successContainer = document.getElementById('uploadSuccess');
        const errorContainer = document.getElementById('uploadError');
        const progressBar = document.getElementById('uploadProgressBar');
        const progressPercentage = document.getElementById('uploadPercentage');

        if (progressContainer) progressContainer.classList.add('d-none');
        if (successContainer) successContainer.classList.add('d-none');
        if (errorContainer) errorContainer.classList.add('d-none');

        if (progressBar) progressBar.style.width = '0%';
        if (progressPercentage) progressPercentage.textContent = '0%';
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }

    getSelectedFileId() {
        return this.selectedFileId;
    }

    getSelectedFileName() {
        return this.selectedFileName;
    }

    reset() {
        this.selectedFileId = null;
        this.selectedFileName = null;
        this.currentFile = null;
        this.resetUploadState();
        this.hideFileInfo();

        const existingFileSelect = document.getElementById('existingFileSelect');
        if (existingFileSelect) {
            existingFileSelect.value = '';
        }

        const newFileInput = document.getElementById('newFileInput');
        if (newFileInput) {
            newFileInput.value = '';
        }
    }
}
