/**
 * Directory Browser - Reusable lazy-loading filesystem tree component.
 *
 * Usage (single-select, default):
 *   DirectoryBrowser.init({
 *       container: '#my-browser',
 *       onSelect: (path, type) => { ... },
 *   });
 *
 * Usage (multi-select):
 *   DirectoryBrowser.init({
 *       container: '#my-browser',
 *       multiSelect: true,
 *       fileFilter: 'csv,tsv',
 *       onSelect: (paths) => { ... },  // paths: [{path, type}, ...]
 *   });
 */
const DirectoryBrowser = (() => {
    'use strict';

    const DEFAULT_OPTIONS = {
        container: '#dirBrowser',
        onSelect: null,           // callback — in multiSelect: (paths[]), single: (path, type)
        fileFilter: '',           // comma-separated extensions e.g. "csv,tsv,csv.gz"
        allowFileSelect: true,    // whether clicking a file triggers onSelect
        multiSelect: false,       // toggle multi-path selection
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
            this.selectedPaths = new Set();    // Set of paths (multi-select)
            this.selectedPathsOrder = [];      // ordered list for display
            this.treeNodes = {};
            this.container = null;
            this.built = false;
        }

        /* ── Public API ── */

        build() {
            const el = document.querySelector(this.opts.container);
            if (!el) throw new Error(`DirectoryBrowser: container "${this.opts.container}" not found`);
            this.container = el;
            this.container.innerHTML = this._html();
            this._bindEvents();
            this.built = true;
            return this;
        }

        async goTo(path) {
            if (!this.built) this.build();
            // If no explicit path, let the backend auto-detect the root filesystem
            await this._loadPath(path || this.opts.defaultPath || '');
        }

        /** Single-select: get currently selected path. */
        getSelected() {
            if (this.opts.multiSelect) {
                return this.selectedPathsOrder.map(p => ({ path: p, type: this.treeNodes[p]?.type || 'directory' }));
            }
            return { path: this.selectedPath, type: this.selectedType };
        }

        /** Multi-select: get all selected paths. */
        getSelectedPaths() {
            return this.selectedPathsOrder.map(p => ({ path: p, type: this.treeNodes[p]?.type || 'directory' }));
        }

        /** Multi-select: remove a path from the selection. */
        removeSelected(path) {
            this.selectedPaths.delete(path);
            this.selectedPathsOrder = this.selectedPathsOrder.filter(p => p !== path);
            this._renderTree();
            this._updateSelectedDisplay();
            this._notify();
        }

        /** Single-select: set selected path programmatically. */
        setSelected(path, type = 'directory') {
            if (this.opts.multiSelect) {
                this._toggleMulti(path, type);
                return;
            }
            this.selectedPath = path;
            this.selectedType = type;
            this._updateSelectedDisplay();
            this._highlightSelected();
            // Auto-expand if it's an unloaded directory — show user the contents immediately
            if (type === 'directory') {
                const node = this.treeNodes[path];
                if (node && node.hasChildren && !node.childrenLoaded) {
                    this._loadChildren(path);
                }
            }
            if (this.opts.onSelect) this.opts.onSelect(path, type);
        }

        _toggleMulti(path, type) {
            if (this.selectedPaths.has(path)) {
                this.selectedPaths.delete(path);
                this.selectedPathsOrder = this.selectedPathsOrder.filter(p => p !== path);
            } else {
                this.selectedPaths.add(path);
                this.selectedPathsOrder.push(path);
            }
            this._renderTree();
            this._updateSelectedDisplay();
            this._notify();
        }

        _notify() {
            if (!this.opts.onSelect) return;
            if (this.opts.multiSelect) {
                this.opts.onSelect(this.getSelectedPaths());
            }
        }

        destroy() {
            if (this.container) this.container.innerHTML = '';
            this.built = false;
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
        <div class="dir-browser-path-bar" data-role="pathBar">
            <span class="dir-browser-path-seg">/</span>
        </div>
        <button class="dir-browser-tool-btn" data-action="refresh" title="刷新">
            <i class="bi bi-arrow-clockwise"></i>
        </button>
    </div>
    <div class="dir-browser-tree" data-role="tree">
        </button>
    </div>
    <div class="dir-browser-tree" data-role="tree">
        <div class="dir-browser-empty">
            <i class="bi bi-folder2-open"></i>加载中...
        </div>
    </div>
    <div class="dir-browser-selected is-empty" data-role="selected">
        <i class="bi bi-chevron-right"></i><span>未选择</span>
    </div>
</div>`;
        }

        /* ── Event bindings ── */
        _bindEvents() {
            const root = document.getElementById(this.id);
            if (!root) return;

            root.querySelector('[data-action="home"]').addEventListener('click', () => {
                this.goTo(this.opts.defaultPath || '/');
            });
            root.querySelector('[data-action="refresh"]').addEventListener('click', async () => {
                await this._loadPath(this.currentPath);
            });
        }

        /* ── Core: load a directory listing ── */
        async _loadPath(path) {
            if (!this.built) return;
            const treeEl = this.container.querySelector('[data-role="tree"]');

            treeEl.innerHTML = '<div class="dir-browser-loading"><span class="spinner-border"></span>加载中...</div>';

            try {
                const params = new URLSearchParams();
                if (path) params.set('path', path);
                if (this.opts.fileFilter) params.set('filter', this.opts.fileFilter);

                const resp = await fetch(`${this.opts.browseApi}?${params.toString()}`);
                const data = await resp.json();

                if (!resp.ok && data.error) {
                    if (resp.status === 404 && path) {
                        this.currentPath = path;
                        this._renderPathBar();
                        await this._loadPath('');
                        return;
                    }
                    treeEl.innerHTML = `<div class="dir-browser-empty"><i class="bi bi-exclamation-triangle"></i>${this._escapeHtml(data.error)}</div>`;
                    return;
                }

                this.currentPath = data.current_path || path;
                this._renderPathBar();

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
            }
        }

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
                // Refresh the selected bar so the child count badge updates
                this._updateSelectedDisplay();
            } catch (err) {
                // silently fail — user can retry
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

            if (this.opts.multiSelect) {
                this._highlightMultiSelected();
            } else {
                this._highlightSelected();
            }
        }

        _renderNode(node, depth, isRoot = false) {
            const isDir = node.type === 'directory';
            const multi = this.opts.multiSelect;
            const isSingleSelected = !multi && (node.path === this.selectedPath);
            const isMultiSelected = multi && this.selectedPaths.has(node.path);

            const row = document.createElement('div');
            row.className = 'dir-node'
                + (isSingleSelected ? ' is-selected' : '')
                + (isMultiSelected ? ' is-checked' : '');
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
                        node._collapsed = !node._collapsed;
                    }
                    this._renderTree();
                });
            } else {
                toggle.classList.add('is-hidden');
            }
            row.appendChild(toggle);

            // Checkmark for multi-select
            if (multi) {
                const chk = document.createElement('span');
                chk.className = 'dir-node-check';
                chk.innerHTML = isMultiSelected ? '<i class="bi bi-check-circle-fill"></i>' : '<i class="bi bi-circle"></i>';
                chk.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this._toggleMulti(node.path, node.type);
                });
                row.appendChild(chk);
            }

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

            if (isDir && node.childrenLoaded && !node._collapsed && node.childrenPaths.length > 0) {
                const childrenContainer = document.createElement('div');
                childrenContainer.className = 'dir-node-children';

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

        _renderPathBar() {
            var bar = this.container.querySelector('[data-role="pathBar"]');
            if (!bar) return;
            var p = this.currentPath;
            if (!p || p === '/') {
                bar.innerHTML = '<span class="dir-browser-path-seg">/</span>';
                return;
            }
            // Split into segments. On Windows, handle drive letters (C:) as first segment.
            var isWin = /^[a-zA-Z]:/.test(p);
            var parts;
            if (isWin) {
                var normalized = p.replace(/\\/g, '/');
                var match = normalized.match(/^([a-zA-Z]:)(.*)/);
                parts = [match[1]];
                var rest = match[2].replace(/\/+$/, '').split('/').filter(Boolean);
                parts = parts.concat(rest);
            } else {
                parts = p.replace(/\/+$/, '').split('/').filter(Boolean);
                parts.unshift('/');
            }
            var html = '';
            var accum = isWin ? '' : '';
            for (var i = 0; i < parts.length; i++) {
                if (i === 0 && !isWin) {
                    accum = '/';
                } else if (i === 0 && isWin) {
                    accum = parts[0];
                } else {
                    accum = accum.replace(/\/+$/, '') + '/' + parts[i];
                }
                html += '<span class="dir-browser-path-sep">' + String.fromCharCode(8250) + '</span>';
                html += '<span class="dir-browser-path-seg" data-nav-path="' + this._escapeHtml(accum) + '">' + this._escapeHtml(parts[i]) + '</span>';
            }
            bar.innerHTML = html;
            var self = this;
            bar.querySelectorAll('.dir-browser-path-seg[data-nav-path]').forEach(function(seg) {
                seg.addEventListener('click', function() { self._loadPath(seg.dataset.navPath); });
            });
        }

        _updateSelectedDisplay() {
            const selEl = this.container.querySelector('[data-role="selected"]');
            if (!selEl) return;

            if (this.opts.multiSelect) {
                const count = this.selectedPathsOrder.length;
                if (count === 0) {
                    selEl.className = 'dir-browser-selected is-empty';
                    selEl.innerHTML = '<i class="bi bi-chevron-right"></i><span>未选择</span>';
                } else {
                    selEl.className = 'dir-browser-selected';
                    selEl.innerHTML = '<i class="bi bi-check-circle-fill"></i>' +
                        this.selectedPathsOrder.slice(-3).reverse().map(p =>
                            `<span class="dir-browser-chip" title="${this._escapeHtml(p)}">${this._escapeHtml(this.treeNodes[p]?.name || p.split('/').filter(Boolean).pop() || p)}<button class="dir-browser-chip-x" data-remove-path="${this._escapeHtml(p)}">&times;</button></span>`
                        ).join('') +
                        (count > 3 ? `<span class="dir-browser-chip-more">+${count - 3}</span>` : '') +
                        `<span class="dir-browser-chip-count">共 ${count} 项</span>`;
                    // Bind remove buttons
                    selEl.querySelectorAll('[data-remove-path]').forEach(btn => {
                        btn.addEventListener('click', (e) => {
                            e.stopPropagation();
                            this.removeSelected(btn.dataset.removePath);
                        });
                    });
                }
                return;
            }

            if (this.selectedPath) {
                selEl.classList.remove('is-empty');
                const node = this.treeNodes[this.selectedPath];
                const basename = node?.name || this.selectedPath.split('/').filter(Boolean).pop() || this.selectedPath;
                const icon = this.selectedType === 'directory' ? 'bi-folder2-open' : 'bi-file-earmark';
                // Show child count if children are loaded, or "has items" hint
                let childHtml = '';
                if (node && node.type === 'directory') {
                    if (node.childrenLoaded) {
                        childHtml = `<span class="dir-browser-badge">${node.childrenPaths.length} 项</span>`;
                    } else if (node.hasChildren) {
                        childHtml = '<span class="dir-browser-badge">含子项</span>';
                    }
                }
                selEl.innerHTML = `<i class="bi ${icon}"></i><strong>${this._escapeHtml(basename)}</strong>${childHtml}`;
            } else {
                selEl.classList.add('is-empty');
                selEl.innerHTML = '<i class="bi bi-chevron-right"></i><span>未选择</span>';
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

        _highlightMultiSelected() {
            const treeEl = this.container.querySelector('[data-role="tree"]');
            if (!treeEl) return;
            treeEl.querySelectorAll('.dir-node.is-checked').forEach(el => el.classList.remove('is-checked'));
            this.selectedPaths.forEach(p => {
                const match = treeEl.querySelector(`[data-path="${p.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"]`);
                if (match) match.classList.add('is-checked');
            });
        }

        _escapeHtml(str) {
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        }
    }

    /* ── Resolve dotted callback ── */
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

    /* ── Auto-init from data-dir-browser elements ── */
    function autoInit() {
        const elements = document.querySelectorAll('[data-dir-browser]');
        elements.forEach(el => {
            const opts = {
                container: '#' + el.id,
                defaultPath: el.dataset.defaultPath || '',
                fileFilter: el.dataset.fileFilter || '',
                allowFileSelect: el.dataset.allowFileSelect === 'true',
                multiSelect: el.dataset.multiSelect === 'true',
                onSelect: null,
            };
            const cbName = el.dataset.onSelect || '';
            const jsVar = el.dataset.jsVar || '';
            const cb = _resolveCallback(cbName);
            if (cb) opts.onSelect = cb;

            const instance = new Instance(opts);
            instance.build();
            instance.goTo(opts.defaultPath);

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

    return {
        init(opts) {
            return new Instance(opts);
        },
    };
})();
