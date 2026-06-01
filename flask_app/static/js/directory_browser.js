/**
 * Directory Browser - Reusable lazy-loading filesystem tree component.
 * Usage:
 *   const browser = DirectoryBrowser.init({
 *       container: '#my-browser',
 *       onSelect: (path, type) => { console.log(path, type); },
 *       fileFilter: 'csv,tsv',
 *       allowFileSelect: true,
 *   });
 */
const DirectoryBrowser = (() => {
    'use strict';

    const DEFAULT_OPTIONS = {
        container: '#dirBrowser',
        onSelect: null,           // callback(path, type) — type: 'directory' | 'file'
        fileFilter: '',           // comma-separated extensions e.g. "csv,tsv,csv.gz"
        allowFileSelect: true,    // whether clicking a file triggers onSelect
        defaultPath: '',          // initial path to browse
        browseApi: '/api/browse-directory',
    };

    let uidCounter = 0;

    class Instance {
        constructor(opts) {
            this.opts = Object.assign({}, DEFAULT_OPTIONS, opts);
            this.id = `dirBrowser_${++uidCounter}`;
            this.currentPath = '';
            this.selectedPath = '';
            this.selectedType = 'directory';
            this.treeNodes = {};   // path -> { name, type, hasChildren, childrenLoaded, childrenPaths }
            this.container = null;
            this.built = false;
        }

        /* ── Public API ── */

        /** Build and render the browser into the container. Call once. */
        build() {
            const el = document.querySelector(this.opts.container);
            if (!el) throw new Error(`DirectoryBrowser: container "${this.opts.container}" not found`);
            this.container = el;
            this.container.innerHTML = this._html();
            this._bindEvents();
            this.built = true;
            return this;
        }

        /** Navigate to a path and reload the tree. */
        async goTo(path) {
            if (!this.built) this.build();
            this.currentPath = path || this.opts.defaultPath || '/';
            await this._loadPath(this.currentPath);
        }

        /** Get currently selected path. */
        getSelected() {
            return { path: this.selectedPath, type: this.selectedType };
        }

        /** Set selected path programmatically. */
        setSelected(path, type = 'directory') {
            this.selectedPath = path;
            this.selectedType = type;
            this._updateSelectedDisplay();
            this._highlightSelected();
            if (this.opts.onSelect) this.opts.onSelect(path, type);
        }

        /* ── HTML template ── */
        _html() {
            const id = this.id;
            return `
<div class="dir-browser" id="${id}">
    <div class="dir-browser-toolbar">
        <button class="dir-browser-tool-btn" data-action="home" title="回到根目录">
            <i class="bi bi-house-door"></i>
        </button>
        <button class="dir-browser-tool-btn" data-action="up" title="上一级">
            <i class="bi bi-arrow-up"></i>
        </button>
        <input class="dir-browser-path-input" data-action="pathInput"
               type="text" placeholder="输入路径后按 Enter 跳转..."
               title="当前路径。输入新路径后按 Enter 跳转">
        <button class="dir-browser-tool-btn" data-action="refresh" title="刷新">
            <i class="bi bi-arrow-clockwise"></i>
        </button>
    </div>
    <div class="dir-browser-tree" data-role="tree">
        <div class="dir-browser-empty">
            <i class="bi bi-folder2-open"></i>加载中...
        </div>
    </div>
    <div class="dir-browser-selected is-empty" data-role="selected">
        <i class="bi bi-chevron-right"></i><span>未选择目录</span>
    </div>
</div>`;
        }

        /* ── Event bindings ── */
        _bindEvents() {
            const root = document.getElementById(this.id);
            if (!root) return;

            // Toolbar buttons
            root.querySelector('[data-action="home"]').addEventListener('click', () => {
                this.goTo(this.opts.defaultPath || '/');
            });
            root.querySelector('[data-action="up"]').addEventListener('click', async () => {
                const parent = this._getParentPath(this.currentPath);
                if (parent) await this._loadPath(parent);
            });
            root.querySelector('[data-action="refresh"]').addEventListener('click', async () => {
                await this._loadPath(this.currentPath);
            });

            // Path input - Enter to jump
            const pathInput = root.querySelector('[data-action="pathInput"]');
            pathInput.addEventListener('keydown', async (e) => {
                if (e.key === 'Enter') {
                    const targetPath = pathInput.value.trim();
                    if (targetPath) {
                        await this._loadPath(targetPath);
                    }
                }
            });
        }

        /* ── Core: load a directory listing ── */
        async _loadPath(path) {
            if (!this.built) return;
            const treeEl = this.container.querySelector('[data-role="tree"]');
            const pathInput = this.container.querySelector('[data-action="pathInput"]');

            treeEl.innerHTML = '<div class="dir-browser-loading"><span class="spinner-border"></span>加载中...</div>';

            try {
                const params = new URLSearchParams();
                if (path) params.set('path', path);
                if (this.opts.fileFilter) params.set('filter', this.opts.fileFilter);

                const resp = await fetch(`${this.opts.browseApi}?${params.toString()}`);
                const data = await resp.json();

                if (!resp.ok && data.error) {
                    // If directory not found, try auto-detection (no path param)
                    if (resp.status === 404 && path) {
                        this.currentPath = path;
                        pathInput.value = path;
                        // Retry without path — server will auto-detect a valid root
                        await this._loadPath('');
                        return;
                    }
                    treeEl.innerHTML = `<div class="dir-browser-empty"><i class="bi bi-exclamation-triangle"></i>${this._escapeHtml(data.error)}</div>`;
                    if (path) pathInput.value = path;
                    return;
                }

                this.currentPath = data.current_path || path;
                pathInput.value = this.currentPath;

                // Build tree nodes from items
                this.treeNodes = {};
                const rootNode = {
                    name: this.currentPath === '/' ? '/' : (this.currentPath.split('/').filter(Boolean).pop() || '/'),
                    path: this.currentPath,
                    type: 'directory',
                    hasChildren: data.items.length > 0,
                    childrenLoaded: true,
                    childrenPaths: [],
                };

                for (const item of data.items) {
                    rootNode.childrenPaths.push(item.path);
                    this.treeNodes[item.path] = {
                        name: item.name,
                        path: item.path,
                        type: item.type,
                        hasChildren: item.has_children || false,
                        childrenLoaded: false,
                        childrenPaths: [],
                    };
                }
                this.treeNodes[this.currentPath] = rootNode;

                this._renderTree();
            } catch (err) {
                treeEl.innerHTML = `<div class="dir-browser-empty"><i class="bi bi-exclamation-triangle"></i>${this._escapeHtml(err.message)}</div>`;
                if (path) pathInput.value = path;
            }
        }

        /** Load children of a specific directory node (lazy). */
        async _loadChildren(dirPath) {
            const node = this.treeNodes[dirPath];
            if (!node || node.type !== 'directory' || node.childrenLoaded) return;

            try {
                const params = new URLSearchParams({ path: dirPath });
                if (this.opts.fileFilter) params.set('filter', this.opts.fileFilter);

                const resp = await fetch(`${this.opts.browseApi}?${params.toString()}`);
                const data = await resp.json();

                if (!resp.ok) return;

                node.childrenPaths = [];
                for (const item of data.items) {
                    const childPath = item.path;
                    node.childrenPaths.push(childPath);
                    if (!this.treeNodes[childPath]) {
                        this.treeNodes[childPath] = {
                            name: item.name,
                            path: childPath,
                            type: item.type,
                            hasChildren: item.has_children || false,
                            childrenLoaded: false,
                            childrenPaths: [],
                        };
                    }
                }
                node.childrenLoaded = true;
                this._renderTree();
            } catch (err) {
                // silently fail — user can retry by toggling again
            }
        }

        /* ── Render tree ── */
        _renderTree() {
            const treeEl = this.container.querySelector('[data-role="tree"]');
            if (!treeEl) return;

            const rootNode = this.treeNodes[this.currentPath];
            if (!rootNode) {
                treeEl.innerHTML = '<div class="dir-browser-empty"><i class="bi bi-folder2-open"></i>目录为空</div>';
                return;
            }

            treeEl.innerHTML = '';
            const rootEl = this._renderNode(rootNode, 0, true);
            if (rootEl) treeEl.appendChild(rootEl);

            // Re-highlight selected
            this._highlightSelected();
        }

        _renderNode(node, depth, isRoot = false) {
            const isDir = node.type === 'directory';
            const isSelected = (node.path === this.selectedPath);

            const row = document.createElement('div');
            row.className = 'dir-node' + (isSelected ? ' is-selected' : '');
            row.dataset.path = node.path;
            row.dataset.type = node.type;
            row.style.paddingLeft = `${0.75 + depth * 1.2}rem`;

            // Toggle arrow
            const toggle = document.createElement('span');
            toggle.className = 'dir-node-toggle';
            if (isDir && node.hasChildren) {
                if (node.childrenLoaded) toggle.classList.add('is-expanded');
                toggle.innerHTML = '<i class="bi bi-chevron-right"></i>';
                toggle.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    if (!node.childrenLoaded) {
                        await this._loadChildren(node.path);
                    } else {
                        // Toggle collapse/expand
                        node._collapsed = !node._collapsed;
                    }
                    this._renderTree();
                });
            } else if (isDir && !node.hasChildren) {
                toggle.classList.add('is-hidden');
            } else {
                toggle.classList.add('is-hidden');
            }
            row.appendChild(toggle);

            // Icon
            const icon = document.createElement('span');
            icon.className = 'dir-node-icon ' + (isDir ? 'folder' : 'file');
            icon.innerHTML = isDir
                ? (node.childrenLoaded && !node._collapsed ? '<i class="bi bi-folder2-open"></i>' : '<i class="bi bi-folder"></i>')
                : '<i class="bi bi-file-earmark"></i>';
            row.appendChild(icon);

            // Name
            const name = document.createElement('span');
            name.className = 'dir-node-name';
            name.textContent = node.name;
            name.title = node.path;
            row.appendChild(name);

            // Click to select
            row.addEventListener('click', () => {
                if (isDir || this.opts.allowFileSelect) {
                    this.setSelected(node.path, node.type);
                }
            });

            const wrapper = document.createElement('div');

            // Children container
            if (isDir && node.childrenLoaded && !node._collapsed && node.childrenPaths.length > 0) {
                const childrenContainer = document.createElement('div');
                childrenContainer.className = 'dir-node-children';

                // Sort: directories first, then files
                const sorted = [...node.childrenPaths].sort((a, b) => {
                    const na = this.treeNodes[a];
                    const nb = this.treeNodes[b];
                    if (!na || !nb) return 0;
                    if (na.type !== nb.type) return na.type === 'directory' ? -1 : 1;
                    return na.name.localeCompare(nb.name);
                });

                for (const childPath of sorted) {
                    const childNode = this.treeNodes[childPath];
                    if (!childNode) continue;
                    const childEl = this._renderNode(childNode, depth + 1);
                    if (childEl) childrenContainer.appendChild(childEl);
                }
                wrapper.appendChild(row);
                wrapper.appendChild(childrenContainer);
            } else {
                wrapper.appendChild(row);
            }

            return wrapper;
        }

        /* ── Helpers ── */
        _getParentPath(p) {
            if (!p || p === '/') return null;
            const parts = p.replace(/\/+$/, '').split('/').filter(Boolean);
            if (parts.length === 0) return '/';
            parts.pop();
            return '/' + parts.join('/');
        }

        _updateSelectedDisplay() {
            const selEl = this.container.querySelector('[data-role="selected"]');
            if (!selEl) return;
            if (this.selectedPath) {
                selEl.classList.remove('is-empty');
                const icon = this.selectedType === 'directory' ? 'bi-folder2-open' : 'bi-file-earmark';
                selEl.innerHTML = `<i class="bi ${icon}"></i><span>${this._escapeHtml(this.selectedPath)}</span>`;
            } else {
                selEl.classList.add('is-empty');
                selEl.innerHTML = '<i class="bi bi-chevron-right"></i><span>未选择目录</span>';
            }
        }

        _highlightSelected() {
            const treeEl = this.container.querySelector('[data-role="tree"]');
            if (!treeEl) return;
            treeEl.querySelectorAll('.dir-node.is-selected').forEach(el => el.classList.remove('is-selected'));
            if (this.selectedPath) {
                const match = treeEl.querySelector(`[data-path="${this.selectedPath.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"]`);
                if (match) match.classList.add('is-selected');
            }
        }

        _escapeHtml(str) {
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        }

        /** Destroy the browser instance and clean up DOM. */
        destroy() {
            if (this.container) {
                this.container.innerHTML = '';
            }
            this.built = false;
        }
    }

    /* ── Resolve a dotted callback string like "ScriptHubPage.onPepBrowserSelect" ── */
    function _resolveCallback(name) {
        if (!name) return null;
        const parts = name.split('.');
        let fn = window;
        for (const part of parts) {
            fn = fn[part];
            if (!fn) return null;
        }
        return typeof fn === 'function' ? fn : null;
    }

    /* ── Auto-initialize from data-dir-browser elements on DOM ready ── */
    function autoInit() {
        const elements = document.querySelectorAll('[data-dir-browser]');
        elements.forEach(el => {
            const opts = {
                container: '#' + el.id,
                defaultPath: el.dataset.defaultPath || '',
                fileFilter: el.dataset.fileFilter || '',
                allowFileSelect: el.dataset.allowFileSelect === 'true',
                onSelect: null,
            };
            const cbName = el.dataset.onSelect || '';
            const jsVar = el.dataset.jsVar || '';
            const cb = _resolveCallback(cbName);
            if (cb) opts.onSelect = cb;

            const instance = new Instance(opts);
            instance.build();
            instance.goTo(opts.defaultPath);

            // Expose instance on window if js_var is specified
            if (jsVar) {
                const parts = jsVar.split('.');
                let target = window;
                for (let i = 0; i < parts.length - 1; i++) {
                    if (!target[parts[i]]) target[parts[i]] = {};
                    target = target[parts[i]];
                }
                target[parts[parts.length - 1]] = instance;
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', autoInit);
    } else {
        autoInit();
    }

    /* ── Static factory ── */
    return {
        init(opts) {
            return new Instance(opts);
        },
    };
})();
