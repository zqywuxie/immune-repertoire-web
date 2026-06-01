# Directory Browser Component Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace manual path text inputs across all analysis pages with a reusable, lazy-loading filesystem tree browser component. Users expand/collapse directories, click to select directories or files, and can type/paste a path to jump directly.

**Architecture:** A new reusable Jinja2 component (`directory_browser.html`) paired with a shared JS module (`directory_browser.js`) and CSS file. The existing `/api/browse-directory` endpoint is enhanced for Linux-friendly defaults and file-type filtering. All analysis pages replace their text-input data source area with this component via Jinja2 `{% include %}`.

**Tech Stack:** Vanilla JS (no framework), Jinja2 templates, Flask, Bootstrap 5 Icons

---

### Task 1: Enhance Backend Browse-Directory API

**Files:**
- Modify: `flask_app/routes/api.py:1277-1362`

- [ ] **Step 1: Replace the `browse_directory` endpoint with Linux-friendly defaults and enhanced filtering**

Replace the entire `browse_directory` function (lines 1277-1362 in api.py):

```python
@api_bp.route('/browse-directory', methods=['GET'])
def browse_directory():
    """
    Browse directories on the server filesystem.
    GET /api/browse-directory?path=/some/path&filter=csv,tsv
    
    Query params:
        path: Absolute path to browse (default: auto-detect Linux root)
        filter: Optional comma-separated file extensions to show (e.g. "csv,tsv,csv.gz")
    """
    import os
    import platform
    from pathlib import Path

    path = request.args.get('path', '')
    file_filter = request.args.get('filter', '')

    # Parse file filter
    allowed_extensions = set()
    if file_filter:
        allowed_extensions = {
            ext.strip().lower() if ext.strip().startswith('.') else f'.{ext.strip().lower()}'
            for ext in file_filter.split(',') if ext.strip()
        }

    # Auto-detect reasonable root on Linux
    if not path:
        if platform.system() == 'Linux':
            candidates = ['/data', '/home', '/mnt', '/opt', '/srv', '/']
        else:
            candidates = [
                str(Path.home() / 'Data'),
                str(Path.home()),
                'C:/Data', 'D:/Data', 'E:/Data',
            ]

        for candidate in candidates:
            p = Path(candidate)
            if p.exists() and p.is_dir():
                path = str(p)
                break
        else:
            path = str(Path.cwd())

    try:
        resolved = Path(path).resolve()

        # Security: block sensitive system paths on Linux
        restricted_prefixes = ['/sys', '/proc', '/dev', '/run', '/boot']
        if platform.system() == 'Linux':
            for prefix in restricted_prefixes:
                if str(resolved).startswith(prefix):
                    return jsonify({
                        'error': 'Access denied: system directory restricted',
                        'current_path': str(resolved),
                        'parent_path': str(resolved.parent) if resolved.parent != resolved else None,
                        'items': [],
                    }), 403

        if not resolved.exists():
            return jsonify({
                'error': 'Directory not found',
                'current_path': str(resolved),
                'parent_path': str(resolved.parent) if resolved.parent != resolved else None,
                'items': [],
            }), 404

        if not resolved.is_dir():
            return jsonify({'error': 'Path is not a directory'}), 400

        items = []
        try:
            for item in sorted(resolved.iterdir()):
                try:
                    is_dir = item.is_dir()
                    suffix = item.suffix.lower()

                    # Apply file filter
                    if not is_dir and allowed_extensions and suffix not in allowed_extensions:
                        continue

                    # Skip hidden items (start with .)
                    if item.name.startswith('.'):
                        continue

                    # Check if directory has children (for expand icon)
                    has_children = False
                    if is_dir:
                        try:
                            has_children = any(
                                not child.name.startswith('.')
                                for child in item.iterdir()
                            )
                        except (PermissionError, OSError):
                            has_children = False

                    item_info = {
                        'name': item.name,
                        'path': str(item),
                        'type': 'directory' if is_dir else 'file',
                        'suffix': suffix if not is_dir else '',
                        'has_children': has_children,
                    }
                    items.append(item_info)
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError) as e:
            return jsonify({'error': f'Cannot read directory: {str(e)}'}), 403

        parent_path = str(resolved.parent) if resolved.parent != resolved else None
        # Don't allow navigating above filesystem root
        if parent_path and not Path(parent_path).exists():
            parent_path = None

        return jsonify({
            'current_path': str(resolved),
            'parent_path': parent_path,
            'items': items,
            'platform': platform.system(),
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

- [ ] **Step 2: Verify the endpoint works**

```bash
# Start the app (or use existing running instance)
curl -s "http://localhost:5000/api/browse-directory" | python -m json.tool | head -20
# Should return the default data directory listing
```

- [ ] **Step 3: Commit**

```bash
git add flask_app/routes/api.py
git commit -m "feat: enhance browse-directory API with Linux defaults and file filtering"
```

---

### Task 2: Create Directory Browser CSS

**Files:**
- Create: `flask_app/static/css/directory_browser.css`

- [ ] **Step 1: Write the CSS file**

```css
/* Directory Browser Component Styles */

.dir-browser {
    border: 1px solid #d7e2ea;
    border-radius: 16px;
    background: #fbfdfe;
    overflow: hidden;
}

/* ── Toolbar ── */
.dir-browser-toolbar {
    display: flex;
    align-items: center;
    gap: .5rem;
    padding: .75rem 1rem;
    border-bottom: 1px solid #e8edf2;
    background: #f8fafb;
}

.dir-browser-path-input {
    flex: 1;
    border: 1px solid #d7e2ea;
    border-radius: 10px;
    padding: .45rem .75rem;
    font-size: .88rem;
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    color: #163247;
    background: #fff;
    transition: border-color .15s, box-shadow .15s;
}

.dir-browser-path-input:focus {
    outline: none;
    border-color: #11597c;
    box-shadow: 0 0 0 3px rgba(17, 89, 124, 0.1);
}

.dir-browser-tool-btn {
    width: 34px;
    height: 34px;
    border: 1px solid #d7e2ea;
    border-radius: 10px;
    background: #fff;
    color: #61778a;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: border-color .15s, color .15s, background .15s;
    flex-shrink: 0;
}

.dir-browser-tool-btn:hover {
    border-color: #11597c;
    color: #11597c;
    background: #e9f6ff;
}

.dir-browser-tool-btn.is-active {
    background: #11597c;
    color: #fff;
    border-color: #11597c;
}

/* ── Tree Panel ── */
.dir-browser-tree {
    max-height: 320px;
    overflow-y: auto;
    padding: .5rem 0;
}

.dir-browser-tree::-webkit-scrollbar {
    width: 6px;
}

.dir-browser-tree::-webkit-scrollbar-thumb {
    background: #c5d2db;
    border-radius: 3px;
}

.dir-browser-tree::-webkit-scrollbar-track {
    background: transparent;
}

/* ── Tree Nodes ── */
.dir-node {
    display: flex;
    align-items: center;
    gap: .35rem;
    padding: .32rem .75rem;
    cursor: pointer;
    transition: background .12s;
    user-select: none;
    border-left: 3px solid transparent;
}

.dir-node:hover {
    background: #f0f5f9;
}

.dir-node.is-selected {
    background: #e9f6ff;
    border-left-color: #11597c;
}

.dir-node.is-selected .dir-node-name {
    color: #11597c;
    font-weight: 600;
}

/* ── Toggle Arrow ── */
.dir-node-toggle {
    width: 18px;
    height: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    color: #8ea4b6;
    font-size: 10px;
    transition: transform .15s;
    border-radius: 4px;
}

.dir-node-toggle:hover {
    background: #dde7ee;
    color: #163247;
}

.dir-node-toggle.is-expanded {
    transform: rotate(90deg);
}

.dir-node-toggle.is-hidden {
    visibility: hidden;
}

/* ── Icon ── */
.dir-node-icon {
    font-size: 1rem;
    flex-shrink: 0;
}

.dir-node-icon.folder {
    color: #c8960c;
}

.dir-node-icon.file {
    color: #8ea4b6;
}

/* ── Name ── */
.dir-node-name {
    flex: 1;
    font-size: .87rem;
    color: #163247;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* ── Children Container ── */
.dir-node-children {
    /* indent by 1.2rem per level */
    padding-left: 1.2rem;
}

.dir-node-children.is-collapsed {
    display: none;
}

/* ── Empty / Loading State ── */
.dir-browser-empty {
    padding: 2rem 1rem;
    text-align: center;
    color: #8ea4b6;
    font-size: .87rem;
}

.dir-browser-empty i {
    font-size: 2rem;
    display: block;
    margin-bottom: .5rem;
    opacity: .5;
}

.dir-browser-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: .5rem;
    padding: 1.5rem;
    color: #8ea4b6;
    font-size: .85rem;
}

.dir-browser-loading .spinner-border {
    width: 1.2rem;
    height: 1.2rem;
    border-width: .15rem;
}

/* ── Selected Path Display ── */
.dir-browser-selected {
    padding: .6rem 1rem;
    border-top: 1px solid #e8edf2;
    background: #f8fafb;
    font-size: .82rem;
    color: #11597c;
    display: flex;
    align-items: center;
    gap: .4rem;
}

.dir-browser-selected i {
    font-size: .9rem;
    color: #c8960c;
}

.dir-browser-selected.is-empty {
    color: #8ea4b6;
    font-style: italic;
}
```

- [ ] **Step 2: Commit**

```bash
git add flask_app/static/css/directory_browser.css
git commit -m "feat: add directory browser CSS styles"
```

---

### Task 3: Create Directory Browser JavaScript Module

**Files:**
- Create: `flask_app/static/js/directory_browser.js`

- [ ] **Step 1: Write the JS module**

```javascript
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
        onSelect: null,          // callback(path, type) — type: 'directory' | 'file'
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
                const params = new URLSearchParams({ path: path });
                if (this.opts.fileFilter) params.set('filter', this.opts.fileFilter);

                const resp = await fetch(`${this.opts.browseApi}?${params.toString()}`);
                const data = await resp.json();

                if (!resp.ok && data.error) {
                    treeEl.innerHTML = `<div class="dir-browser-empty"><i class="bi bi-exclamation-triangle"></i>${data.error}</div>`;
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
                treeEl.innerHTML = `<div class="dir-browser-empty"><i class="bi bi-exclamation-triangle"></i>无法加载: ${err.message}</div>`;
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
                toggle.classList.add(node.childrenLoaded ? 'is-expanded' : '');
                toggle.innerHTML = '<i class="bi bi-chevron-right"></i>';
                toggle.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    if (!node.childrenLoaded) {
                        await this._loadChildren(node.path);
                    }
                    node.childrenLoaded = !node.childrenLoaded; // toggle visibility
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
                ? (node.childrenLoaded ? '<i class="bi bi-folder2-open"></i>' : '<i class="bi bi-folder"></i>')
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
            if (isDir && node.childrenLoaded && node.childrenPaths.length > 0) {
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
                selEl.innerHTML = `<i class="bi ${icon}"></i><span>${this.selectedPath}</span>`;
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
                const match = treeEl.querySelector(`[data-path="${CSS.escape(this.selectedPath)}"]`);
                if (match) match.classList.add('is-selected');
            }
        }

        /** Destroy the browser instance and clean up DOM. */
        destroy() {
            if (this.container) {
                this.container.innerHTML = '';
            }
            this.built = false;
        }
    }

    /* ── Static factory ── */
    return {
        init(opts) {
            return new Instance(opts);
        },
    };
})();
```

- [ ] **Step 2: Commit**

```bash
git add flask_app/static/js/directory_browser.js
git commit -m "feat: add directory browser JS module with lazy loading and path jump"
```

---

### Task 4: Create Directory Browser Jinja2 Component

**Files:**
- Create: `flask_app/templates/components/directory_browser.html`

- [ ] **Step 1: Write the Jinja2 component template**

```html
{# 
    Directory Browser Component
    ===========================
    Parameters:
        browser_id:       Unique DOM id for this browser instance (required)
        js_var:           JS variable name to store the instance (e.g. "window._pepBrowser")
        default_path:     Initial path to browse (default: auto via API)
        file_filter:      Comma-separated extensions e.g. "csv,tsv,csv.gz" (default: "")
        allow_file_select: Whether files are selectable (default: true)
        on_select:        JS callback function name (e.g. "onPepPathSelected")
        label:            Label text above the browser (default: "数据源目录")
#}
{% set bid = browser_id|default('dirBrowser') %}
{% set jsv = js_var|default('window._dirBrowser') %}
{% set dp = default_path|default('') %}
{% set ff = file_filter|default('') %}
{% set afs = 'true' if allow_file_select|default(true) else 'false' %}
{% set nos = on_select|default('null') %}

<div class="mb-3">
    <label class="form-label fw-semibold">{{ label|default('数据源目录') }}</label>
    <div id="{{ bid }}"></div>
</div>

<script>
(function() {
    if (typeof DirectoryBrowser === 'undefined') {
        console.error('DirectoryBrowser module not loaded. Include directory_browser.js first.');
        return;
    }
    {{ jsv }} = DirectoryBrowser.init({
        container: '#{{ bid }}',
        fileFilter: '{{ ff }}',
        allowFileSelect: {{ afs }},
        defaultPath: '{{ dp }}',
        onSelect: function(path, type) {
            {% if nos and nos != 'null' %}
            {{ nos }}(path, type);
            {% endif %}
        },
    });
    {{ jsv }}.build();
    // Auto-load the default or root path
    {{ jsv }}.goTo('{{ dp }}');
})();
</script>
```

- [ ] **Step 2: Add CSS and JS includes to base.html**

Read `flask_app/templates/base.html` and add the new CSS/JS includes within `{% block extra_head %}` or in the analysis pages' `{% block extra_css %}` / `{% block extra_js %}`.

Since this is a component, each analysis page that uses it needs to include the CSS and JS. Add to each page's `{% block extra_css %}`:
```html
<link href="{{ url_for('static', filename='css/directory_browser.css') }}" rel="stylesheet">
```

And at the bottom of each page's content block or in a `{% block extra_js %}`:
```html
<script src="{{ url_for('static', filename='js/directory_browser.js') }}"></script>
```

- [ ] **Step 3: Commit**

```bash
git add flask_app/templates/components/directory_browser.html
git commit -m "feat: add directory browser Jinja2 reusable component"
```

---

### Task 5: Integrate into Script Hub Page

**Files:**
- Modify: `flask_app/templates/analysis/script_hub.html`

- [ ] **Step 1: Add CSS and JS includes to script_hub.html**

In `script_hub.html`, find the `{% block extra_css %}` (around line 4). Add at the top of the style block, before the inline `<style>`:

```html
{% block extra_css %}
<link href="{{ url_for('static', filename='css/directory_browser.css') }}" rel="stylesheet">
<style>
    ...existing styles...
```

- [ ] **Step 2: Replace the data source section (Stage 02) with the browser component**

Replace the "PEP 文件路径" subpanel (`#scriptHubPepCheckboxList` + `#scriptHubPepCustomPaths` textarea) and the hidden `#scriptHubBasePath` with the directory browser. 

Find the section around line 714-756 (the PEP path subpanel and Profile selection). Replace the PEP path subpanel:

```html
<!-- PEP Path Selection -->
<div class="sh-subpanel mb-3">
    <h3 class="sh-subpanel-title">PEP 文件路径 <span class="text-muted small">(多选)</span></h3>
    <p class="sh-subpanel-copy">从下方目录树中选择 PEP 文件所在目录，或输入路径后按 Enter 跳转。</p>
    {% set pep_browser_config = {
        'browser_id': 'scriptHubPepBrowser',
        'js_var': 'window._pepBrowser',
        'file_filter': 'csv,tsv,csv.gz',
        'allow_file_select': True,
        'default_path': '/data',
        'on_select': 'ScriptHub.onPepBrowserSelect',
        'label': 'PEP 数据目录',
    } %}
    {% include 'components/directory_browser.html' %}
    <div class="sh-pep-checkbox-list mb-2" id="scriptHubPepCheckboxList">
        <span class="text-muted small">选择项目后自动显示可用的 PEP 路径。</span>
    </div>
    <label for="scriptHubPepCustomPaths" class="form-label small mt-2">手动输入路径 <span class="text-muted">(每行一个，或用逗号分隔)</span></label>
    <textarea class="form-control" id="scriptHubPepCustomPaths" rows="2"
              placeholder="E:\Data\pep_root&#10;/data/projects/pep_data"></textarea>
</div>
```

- [ ] **Step 3: Add the `onPepBrowserSelect` handler to script_hub.js**

In `script_hub.js`, add a new method to the `ScriptHub` object:

```javascript
onPepBrowserSelect(path, type) {
    // When user selects a directory/file from the browser, update the hidden basePath
    document.getElementById('scriptHubBasePath').value = path;
    this.showSourceFeedback(`已选择: ${path}`, 'info');
    // Auto-inspect if module is already selected
    if (this.activeModule) {
        this.inspectBasePath(path);
    }
},
```

- [ ] **Step 4: Add JS include for directory_browser.js**

At the bottom of the `{% block content %}` in `script_hub.html`, before the `{% endblock %}`, add:

```html
<script src="{{ url_for('static', filename='js/directory_browser.js') }}"></script>
```

- [ ] **Step 5: Commit**

```bash
git add flask_app/templates/analysis/script_hub.html flask_app/static/js/script_hub.js
git commit -m "feat: integrate directory browser into Script Hub data selection"
```

---

### Task 6: Integrate into Combined Analysis Page

**Files:**
- Modify: `flask_app/templates/analysis/combined_analysis.html`
- Modify: `flask_app/static/js/combined_analysis.js`

- [ ] **Step 1: Replace text input with directory browser in combined_analysis.html**

Find the `#chartLocalPathRow` section (around line 122-131). Replace:

```html
<div class="chart-subpanel" id="chartLocalSourcePanel">
    {% set combined_browser_config = {
        'browser_id': 'combinedDirBrowser',
        'js_var': 'window._combinedBrowser',
        'file_filter': 'csv,tsv,csv.gz',
        'allow_file_select': False,
        'default_path': '/data',
        'on_select': 'CombinedAnalysis.onBrowserSelect',
        'label': '输入数据目录',
    } %}
    {% include 'components/directory_browser.html' %}
    <div class="d-grid mt-2">
        <button class="btn btn-primary" id="chartScanButton" onclick="CombinedAnalysis.scanFolder()">
            <i class="bi bi-search me-1"></i>扫描目录
        </button>
    </div>
</div>
```

- [ ] **Step 2: Add onBrowserSelect to combined_analysis.js**

```javascript
onBrowserSelect(path, type) {
    document.getElementById('basePath').value = path;
},
```

- [ ] **Step 3: Ensure scanFolder reads from basePath (already reads from #basePath input, keep that)**

Keep the hidden `#basePath` input synced. Add sync logic in `onBrowserSelect`.

- [ ] **Step 4: Add CSS/JS includes**

Add to `{% block extra_css %}`:
```html
<link href="{{ url_for('static', filename='css/directory_browser.css') }}" rel="stylesheet">
```

Add at bottom of content block:
```html
<script src="{{ url_for('static', filename='js/directory_browser.js') }}"></script>
```

- [ ] **Step 5: Commit**

```bash
git add flask_app/templates/analysis/combined_analysis.html flask_app/static/js/combined_analysis.js
git commit -m "feat: integrate directory browser into Combined Analysis"
```

---

### Task 7: Integrate into Treemap, Chord, Similarity Heatmap, Pipeline Comparison Pages

**Files:**
- Modify: `flask_app/templates/analysis/treemap.html`
- Modify: `flask_app/templates/analysis/chord_diagram.html`
- Modify: `flask_app/templates/analysis/similarity_heatmap.html`
- Modify: `flask_app/templates/analysis/pipeline_comparison.html`
- Modify: `flask_app/static/js/treemap_analysis.js`
- Modify: `flask_app/static/js/chord_diagram_analysis.js`
- Modify: `flask_app/static/js/similarity_heatmap.js`
- Modify: `flask_app/static/js/pipeline_comparison.js`

- [ ] **Step 1: Apply the same pattern to treemap.html**

Replace the local source panel text input row with the directory browser component (same pattern as Task 6). The treemap page has its text input in `#localSourcePanel` around line 44-56.

```html
<div id="localSourcePanel">
    {% set treemap_browser_config = {
        'browser_id': 'treemapDirBrowser',
        'js_var': 'window._treemapBrowser',
        'file_filter': 'csv,tsv,csv.gz',
        'allow_file_select': False,
        'default_path': '/data',
        'on_select': 'TreemapAnalysis.onBrowserSelect',
        'label': '输入数据目录',
    } %}
    {% include 'components/directory_browser.html' %}
    <div class="d-grid mt-2">
        <button class="btn btn-primary" onclick="TreemapAnalysis.scanFolder()">
            <i class="bi bi-search me-1"></i>扫描目录
        </button>
    </div>
</div>
```

Add to `treemap_analysis.js`:
```javascript
onBrowserSelect(path, type) {
    document.getElementById('basePath').value = path;
},
```

Add CSS/JS includes at top and bottom of the template.

- [ ] **Step 2: Apply same pattern to chord_diagram.html**

Replace `#localSourcePanel` text input. Add `onBrowserSelect` to `chord_diagram_analysis.js`. Add CSS/JS includes.

- [ ] **Step 3: Apply same pattern to similarity_heatmap.html**

Replace `#localSourcePanel` text input. Add `onBrowserSelect` to `similarity_heatmap.js`. Add CSS/JS includes.

- [ ] **Step 4: Apply same pattern to pipeline_comparison.html**

Replace local source text input. Add `onBrowserSelect` to `pipeline_comparison.js`. Add CSS/JS includes.

- [ ] **Step 5: Update analysis_source_panel.html to use the directory browser**

Replace the text input in the shared component with the directory browser, parameterized via Jinja2 variables:

```html
<div id="localSourcePanel">
    {% set panel_browser_config = {
        'browser_id': browser_id|default('sourceDirBrowser'),
        'js_var': browser_js_var|default('window._sourceBrowser'),
        'file_filter': browser_filter|default('csv,tsv,csv.gz'),
        'allow_file_select': browser_allow_file|default(false),
        'default_path': browser_default_path|default('/data'),
        'on_select': browser_on_select|default('null'),
        'label': browser_label|default('输入数据目录'),
    } %}
    {% include 'components/directory_browser.html' %}
    <div class="d-grid mt-2">
        <button class="btn btn-primary" onclick="{{ analysis_js_object }}.scanFolder()">
            <i class="bi bi-search me-1"></i>{{ scan_button_label|default('扫描目录') }}
        </button>
    </div>
</div>
```

- [ ] **Step 6: Commit**

```bash
git add flask_app/templates/analysis/treemap.html flask_app/templates/analysis/chord_diagram.html flask_app/templates/analysis/similarity_heatmap.html flask_app/templates/analysis/pipeline_comparison.html flask_app/templates/components/analysis_source_panel.html flask_app/static/js/treemap_analysis.js flask_app/static/js/chord_diagram_analysis.js flask_app/static/js/similarity_heatmap.js flask_app/static/js/pipeline_comparison.js
git commit -m "feat: integrate directory browser into all remaining analysis pages"
```

---

### Task 8: Final Verification

- [ ] **Step 1: Verify all Python files compile**

```bash
cd /path/to/project
python -m py_compile flask_app/routes/api.py
echo "api.py OK"
python -m py_compile flask_app/app.py
echo "app.py OK"
```

- [ ] **Step 2: Verify no JS syntax errors (quick check)**

```bash
node --check flask_app/static/js/directory_browser.js && echo "directory_browser.js syntax OK"
# Check other modified JS files too
node --check flask_app/static/js/script_hub.js && echo "script_hub.js OK"
node --check flask_app/static/js/combined_analysis.js && echo "combined_analysis.js OK"
node --check flask_app/static/js/treemap_analysis.js && echo "treemap_analysis.js OK"
node --check flask_app/static/js/chord_diagram_analysis.js && echo "chord_diagram_analysis.js OK"
node --check flask_app/static/js/similarity_heatmap.js && echo "similarity_heatmap.js OK"
node --check flask_app/static/js/pipeline_comparison.js && echo "pipeline_comparison.js OK"
```

- [ ] **Step 3: Start the app and test the browser endpoint**

```bash
# Start Flask app
python flask_app/app.py &
sleep 3

# Test default browse (should find /data or /home on Linux)
curl -s "http://localhost:5000/api/browse-directory" | python -m json.tool | head -30

# Test with filter
curl -s "http://localhost:5000/api/browse-directory?filter=csv,tsv" | python -m json.tool | head -20

# Test specific path
curl -s "http://localhost:5000/api/browse-directory?path=/data" | python -m json.tool | head -20
```

- [ ] **Step 4: Manual browser test**

Open `http://192.168.31.67:5000/analysis/script-hub` in a browser and verify:
- The directory browser renders with toolbar (🏠 ⬆ 🔄) and path input
- Clicking expand arrow next to a folder loads its children
- Typing a path and pressing Enter navigates to that directory
- Clicking a directory selects it (blue highlight + bottom bar updates)
- The "扫描目录" pattern still works (if retained alongside the browser)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: final verification and cleanup for directory browser integration"
```
