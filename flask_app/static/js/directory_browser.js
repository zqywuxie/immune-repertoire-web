/**
 * Directory Browser Component
 * Provides directory browsing and selection functionality
 * Requirements: 12.2, 12.3, 12.4, 12.5
 */

class DirectoryBrowser {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            throw new Error(`Container element not found: ${containerId}`);
        }

        this.options = {
            onSelect: options.onSelect || null,
            onCancel: options.onCancel || null,
            showCreateButton: options.showCreateButton || false,
            ...options
        };

        this.currentPath = null;
        this.selectedPath = null;

        this.init();
    }

    init() {
        this.render();
        this.loadRootDirectories();
    }

    render() {
        this.container.innerHTML = `
            <div class="directory-browser">
                <div class="directory-browser-header">
                    <div class="current-path">
                        <i class="bi bi-folder me-2"></i>
                        <span id="currentPathDisplay">选择目录</span>
                    </div>
                    <button class="btn btn-sm btn-outline-secondary" id="parentDirBtn" disabled>
                        <i class="bi bi-arrow-up"></i> 上级目录
                    </button>
                </div>
                <div class="directory-browser-body" id="directoryList">
                    <div class="text-center py-3">
                        <div class="spinner-border spinner-border-sm" role="status"></div>
                        <p class="text-muted mt-2">加载目录中...</p>
                    </div>
                </div>
                <div class="directory-browser-footer">
                    <button class="btn btn-sm btn-primary" id="selectDirBtn" disabled>
                        <i class="bi bi-check"></i> 选择此目录
                    </button>
                    <button class="btn btn-sm btn-secondary" id="cancelDirBtn">
                        <i class="bi bi-x"></i> 取消
                    </button>
                    ${this.options.showCreateButton ? `
                        <button class="btn btn-sm btn-outline-primary" id="createDirBtn">
                            <i class="bi bi-folder-plus"></i> 新建文件夹
                        </button>
                    ` : ''}
                </div>
            </div>
        `;

        this.bindEvents();
    }

    bindEvents() {
        // Parent directory button
        const parentBtn = document.getElementById('parentDirBtn');
        if (parentBtn) {
            parentBtn.addEventListener('click', () => this.navigateToParent());
        }

        // Select button
        const selectBtn = document.getElementById('selectDirBtn');
        if (selectBtn) {
            selectBtn.addEventListener('click', () => this.selectDirectory());
        }

        // Cancel button
        const cancelBtn = document.getElementById('cancelDirBtn');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => this.cancel());
        }

        // Create directory button
        const createBtn = document.getElementById('createDirBtn');
        if (createBtn) {
            createBtn.addEventListener('click', () => this.createDirectory());
        }
    }

    async loadRootDirectories() {
        try {
            const response = await fetch('/api/directories');
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || 'Failed to load directories');
            }

            this.displayDirectories(data);

        } catch (error) {
            console.error('Error loading root directories:', error);
            this.showError('加载目录失败: ' + error.message);
        }
    }

    async loadDirectory(path) {
        try {
            const response = await fetch(`/api/directories?parent_path=${encodeURIComponent(path)}`);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || 'Failed to load directory');
            }

            this.displayDirectories(data);

        } catch (error) {
            console.error('Error loading directory:', error);
            this.showError('加载目录失败: ' + error.message);
        }
    }

    displayDirectories(data) {
        this.currentPath = data.current_path;
        this.parentPath = data.parent_path;

        // Update current path display
        const pathDisplay = document.getElementById('currentPathDisplay');
        if (pathDisplay) {
            pathDisplay.textContent = this.currentPath || '根目录';
        }

        // Enable/disable parent button
        const parentBtn = document.getElementById('parentDirBtn');
        if (parentBtn) {
            parentBtn.disabled = !this.parentPath;
        }

        // Enable select button if we have a current path
        const selectBtn = document.getElementById('selectDirBtn');
        if (selectBtn) {
            selectBtn.disabled = !this.currentPath;
        }

        // Display directories
        const listContainer = document.getElementById('directoryList');
        if (!listContainer) return;

        if (data.directories.length === 0) {
            listContainer.innerHTML = `
                <div class="text-center py-3">
                    <i class="bi bi-folder-x text-muted" style="font-size: 2rem;"></i>
                    <p class="text-muted mt-2">此目录为空</p>
                </div>
            `;
            return;
        }

        listContainer.innerHTML = '';

        data.directories.forEach(dir => {
            const dirItem = document.createElement('div');
            dirItem.className = 'directory-item';
            dirItem.innerHTML = `
                <i class="bi bi-folder-fill text-warning me-2"></i>
                <span class="directory-name">${this.escapeHtml(dir.name)}</span>
                ${dir.has_children ? '<i class="bi bi-chevron-right ms-auto"></i>' : ''}
            `;

            dirItem.addEventListener('click', () => {
                this.loadDirectory(dir.path);
            });

            listContainer.appendChild(dirItem);
        });
    }

    navigateToParent() {
        if (this.parentPath) {
            this.loadDirectory(this.parentPath);
        }
    }

    selectDirectory() {
        if (!this.currentPath) {
            alert('请选择一个目录');
            return;
        }

        this.selectedPath = this.currentPath;

        if (this.options.onSelect) {
            this.options.onSelect(this.selectedPath);
        }
    }

    cancel() {
        this.selectedPath = null;

        if (this.options.onCancel) {
            this.options.onCancel();
        }
    }

    async createDirectory() {
        const dirName = prompt('请输入新文件夹名称:');
        if (!dirName) return;

        if (!this.currentPath) {
            alert('请先选择一个父目录');
            return;
        }

        const newPath = `${this.currentPath}/${dirName}`;

        try {
            const response = await fetch('/api/directories/create', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    path: newPath
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || 'Failed to create directory');
            }

            // Reload current directory
            this.loadDirectory(this.currentPath);

        } catch (error) {
            console.error('Error creating directory:', error);
            alert('创建文件夹失败: ' + error.message);
        }
    }

    showError(message) {
        const listContainer = document.getElementById('directoryList');
        if (listContainer) {
            listContainer.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    ${this.escapeHtml(message)}
                </div>
            `;
        }
    }

    getSelectedPath() {
        return this.selectedPath;
    }

    refresh() {
        if (this.currentPath) {
            this.loadDirectory(this.currentPath);
        } else {
            this.loadRootDirectories();
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DirectoryBrowser;
}
