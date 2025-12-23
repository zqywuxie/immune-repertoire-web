/**
 * Table Copy Module for the Immune Repertoire Analysis Web Application.
 * Provides clipboard copy and CSV download functionality for data tables.
 * Requirements: 2.6, 3.6, 4.6, 5.6
 * 
 * This module provides:
 * - Copy table contents to clipboard (tab-delimited format)
 * - Download table as CSV file
 * - DataTables integration for sorting and searching
 * - Copy success notifications with Bootstrap Toast
 */

// Module namespace to avoid global pollution
const TableCopy = {
    // Configuration
    config: {
        toastDuration: 2000,
        defaultDelimiter: '\t',
        csvDelimiter: ','
    },

    /**
     * Copy table contents to clipboard in tab-delimited format.
     * @param {string} tableId - The ID of the table element to copy
     * @param {boolean} includeHeaders - Whether to include table headers (default: true)
     * @returns {Promise<boolean>} - Promise resolving to success status
     */
    copyTable(tableId, includeHeaders = true) {
        const table = document.getElementById(tableId);
        if (!table) {
            console.error(`Table with ID '${tableId}' not found`);
            return Promise.resolve(false);
        }

        const text = this.extractTableText(table, includeHeaders, this.config.defaultDelimiter);
        return this.copyToClipboard(text, tableId);
    },

    /**
     * Extract text content from a table element.
     * @param {HTMLTableElement} table - The table element
     * @param {boolean} includeHeaders - Whether to include headers
     * @param {string} delimiter - Column delimiter
     * @returns {string} - Extracted text
     */
    extractTableText(table, includeHeaders, delimiter) {
        let text = '';
        const rows = table.querySelectorAll('tr');

        rows.forEach((row, index) => {
            // Skip header row if not including headers
            if (index === 0 && !includeHeaders) return;

            const cells = row.querySelectorAll('th, td');
            const rowData = Array.from(cells).map(cell => {
                // Get text content, trimming whitespace
                let content = cell.textContent.trim();
                // Handle cells with "-" placeholder for null values
                if (content === '-') content = '';
                return content;
            });
            text += rowData.join(delimiter) + '\n';
        });

        return text;
    },

    /**
     * Copy text to clipboard with fallback support.
     * @param {string} text - Text to copy
     * @param {string} tableId - Table ID for showing success message
     * @returns {Promise<boolean>} - Promise resolving to success status
     */
    copyToClipboard(text, tableId) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text).then(() => {
                this.showCopySuccess(tableId);
                return true;
            }).catch(err => {
                console.error('Failed to copy table:', err);
                return this.fallbackCopy(text, tableId);
            });
        } else {
            return Promise.resolve(this.fallbackCopy(text, tableId));
        }
    },

    /**
     * Fallback copy method for browsers without clipboard API support.
     * @param {string} text - Text to copy
     * @param {string} tableId - Table ID for showing success message
     * @returns {boolean} - Success status
     */
    fallbackCopy(text, tableId) {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-9999px';
        textArea.style.top = '0';
        textArea.setAttribute('readonly', '');
        document.body.appendChild(textArea);
        textArea.select();

        try {
            const success = document.execCommand('copy');
            if (success) {
                this.showCopySuccess(tableId);
            } else {
                this.showCopyError('复制失败，请手动选择并复制');
            }
            return success;
        } catch (err) {
            console.error('Fallback copy failed:', err);
            this.showCopyError('复制失败，请手动选择并复制');
            return false;
        } finally {
            document.body.removeChild(textArea);
        }
    },

    /**
     * Show copy success notification using Bootstrap Toast or fallback.
     * @param {string} tableId - Table ID for finding the associated toast
     */
    showCopySuccess(tableId) {
        // Try to find table-specific toast first
        const toastId = `${tableId}-toast`;
        let toastEl = document.getElementById(toastId);

        // Fall back to generic copy toast
        if (!toastEl) {
            toastEl = document.getElementById('copyToast');
        }

        if (toastEl && typeof bootstrap !== 'undefined' && bootstrap.Toast) {
            const toast = new bootstrap.Toast(toastEl, { delay: this.config.toastDuration });
            toast.show();
        } else {
            // Create a simple notification if Bootstrap Toast is not available
            this.showNotification('表格已复制到剪贴板！', 'success');
        }
    },

    /**
     * Show copy error notification.
     * @param {string} message - Error message to display
     */
    showCopyError(message) {
        this.showNotification(message, 'danger');
    },

    /**
     * Show a notification message.
     * @param {string} message - Message to display
     * @param {string} type - Bootstrap alert type (success, danger, warning, info)
     */
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} position-fixed bottom-0 end-0 m-3 shadow`;
        notification.style.zIndex = '9999';
        notification.style.minWidth = '200px';
        notification.innerHTML = `
            <div class="d-flex align-items-center">
                <i class="bi bi-${type === 'success' ? 'check-circle' : 'exclamation-circle'} me-2"></i>
                <span>${message}</span>
            </div>
        `;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.classList.add('fade');
            setTimeout(() => notification.remove(), 150);
        }, this.config.toastDuration);
    },

    /**
     * Download table contents as CSV file.
     * @param {string} tableId - The ID of the table element to download
     * @param {string} filename - Base filename for the download (without extension)
     */
    downloadCSV(tableId, filename = 'data') {
        const table = document.getElementById(tableId);
        if (!table) {
            console.error(`Table with ID '${tableId}' not found`);
            return;
        }

        let csv = '';
        const rows = table.querySelectorAll('tr');

        rows.forEach(row => {
            const cells = row.querySelectorAll('th, td');
            const rowData = Array.from(cells).map(cell => {
                let content = cell.textContent.trim();
                // Handle cells with "-" placeholder for null values
                if (content === '-') content = '';
                // Escape quotes and wrap in quotes if contains comma, quote, or newline
                if (content.includes(',') || content.includes('"') || content.includes('\n')) {
                    content = '"' + content.replace(/"/g, '""') + '"';
                }
                return content;
            });
            csv += rowData.join(this.config.csvDelimiter) + '\n';
        });

        this.downloadFile(csv, `${filename}.csv`, 'text/csv;charset=utf-8;');
    },

    /**
     * Download content as a file.
     * @param {string} content - File content
     * @param {string} filename - Filename with extension
     * @param {string} mimeType - MIME type
     */
    downloadFile(content, filename, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const link = document.createElement('a');

        if (navigator.msSaveBlob) {
            // IE 10+
            navigator.msSaveBlob(blob, filename);
        } else {
            link.href = URL.createObjectURL(blob);
            link.download = filename;
            link.style.display = 'none';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(link.href);
        }
    },

    /**
     * Copy specific data array to clipboard.
     * @param {Array<Array<any>>} data - 2D array of data to copy
     * @param {Array<string>} headers - Optional header row
     * @returns {Promise<boolean>} - Promise resolving to success status
     */
    copyData(data, headers = null) {
        let text = '';

        if (headers) {
            text += headers.join(this.config.defaultDelimiter) + '\n';
        }

        data.forEach(row => {
            text += row.map(cell => cell ?? '').join(this.config.defaultDelimiter) + '\n';
        });

        return this.copyToClipboard(text, null);
    }
};

// Global function wrappers for backward compatibility
function copyTableToClipboard(tableId, includeHeaders = true) {
    return TableCopy.copyTable(tableId, includeHeaders);
}

/**
 * Show copy success notification (global function for backward compatibility).
 * @param {string} tableId - Table ID for finding the associated toast
 */
function showCopySuccess(tableId) {
    TableCopy.showCopySuccess(tableId);
}

/**
 * Download table contents as CSV file (global function for backward compatibility).
 * @param {string} tableId - The ID of the table element to download
 * @param {string} filename - Base filename for the download (without extension)
 */
function downloadTableAsCSV(tableId, filename = 'data') {
    TableCopy.downloadCSV(tableId, filename);
}

/**
 * Copy specific data to clipboard (global function for backward compatibility).
 * @param {Array<Array<any>>} data - 2D array of data to copy
 * @param {Array<string>} headers - Optional header row
 */
function copyDataToClipboard(data, headers = null) {
    return TableCopy.copyData(data, headers);
}

/**
 * DataTables Integration Module
 * Provides enhanced table functionality with sorting, searching, and pagination.
 * Requirements: 2.5, 3.5, 4.5, 5.5
 */
const DataTableManager = {
    // Store initialized DataTable instances
    instances: {},

    // Default configuration for Chinese locale
    defaultConfig: {
        pageLength: 25,
        lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, '全部']],
        order: [],
        responsive: true,
        dom: '<"row mb-3"<"col-sm-12 col-md-6"l><"col-sm-12 col-md-6"f>>rt<"row mt-3"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
        language: {
            search: '搜索:',
            searchPlaceholder: '输入关键词...',
            lengthMenu: '显示 _MENU_ 条',
            info: '显示第 _START_ 到 _END_ 条，共 _TOTAL_ 条',
            infoEmpty: '没有数据',
            infoFiltered: '(从 _MAX_ 条中筛选)',
            zeroRecords: '没有找到匹配的记录',
            emptyTable: '表格中没有数据',
            paginate: {
                first: '首页',
                previous: '上一页',
                next: '下一页',
                last: '末页'
            },
            loadingRecords: '加载中...',
            processing: '处理中...'
        }
    },

    /**
     * Initialize DataTables on a table element.
     * @param {string} tableId - The ID of the table element
     * @param {Object} options - DataTables configuration options
     * @returns {Object|null} - DataTable instance or null if library not loaded
     */
    init(tableId, options = {}) {
        // Check if DataTables library is loaded
        if (typeof $ === 'undefined' || typeof $.fn.DataTable === 'undefined') {
            console.warn('DataTables library not loaded. Table will display without enhanced features.');
            return null;
        }

        // Check if table exists
        const table = document.getElementById(tableId);
        if (!table) {
            console.error(`Table with ID '${tableId}' not found`);
            return null;
        }

        // Destroy existing instance if any
        if (this.instances[tableId]) {
            this.destroy(tableId);
        }

        // Merge options with defaults
        const mergedOptions = this.mergeOptions(this.defaultConfig, options);

        try {
            const instance = $(`#${tableId}`).DataTable(mergedOptions);
            this.instances[tableId] = instance;
            return instance;
        } catch (error) {
            console.error(`Failed to initialize DataTable for '${tableId}':`, error);
            return null;
        }
    },

    /**
     * Deep merge two option objects.
     * @param {Object} defaults - Default options
     * @param {Object} overrides - Override options
     * @returns {Object} - Merged options
     */
    mergeOptions(defaults, overrides) {
        const result = { ...defaults };

        for (const key in overrides) {
            if (overrides.hasOwnProperty(key)) {
                if (typeof overrides[key] === 'object' && !Array.isArray(overrides[key]) && overrides[key] !== null) {
                    result[key] = this.mergeOptions(defaults[key] || {}, overrides[key]);
                } else {
                    result[key] = overrides[key];
                }
            }
        }

        return result;
    },

    /**
     * Get an existing DataTable instance.
     * @param {string} tableId - The ID of the table element
     * @returns {Object|null} - DataTable instance or null
     */
    get(tableId) {
        return this.instances[tableId] || null;
    },

    /**
     * Destroy a DataTable instance.
     * @param {string} tableId - The ID of the table element
     */
    destroy(tableId) {
        if (this.instances[tableId]) {
            try {
                this.instances[tableId].destroy();
                delete this.instances[tableId];
            } catch (error) {
                console.error(`Failed to destroy DataTable for '${tableId}':`, error);
            }
        }
    },

    /**
     * Refresh/redraw a DataTable.
     * @param {string} tableId - The ID of the table element
     */
    refresh(tableId) {
        const instance = this.get(tableId);
        if (instance) {
            instance.draw();
        }
    },

    /**
     * Initialize all tables with a specific class.
     * @param {string} className - CSS class name to identify tables
     * @param {Object} options - DataTables configuration options
     */
    initAll(className = 'data-table', options = {}) {
        const tables = document.querySelectorAll(`table.${className}`);
        tables.forEach(table => {
            if (table.id) {
                this.init(table.id, options);
            }
        });
    },

    /**
     * Create a DataTable with copy and download buttons.
     * @param {string} tableId - The ID of the table element
     * @param {Object} options - DataTables configuration options
     * @returns {Object|null} - DataTable instance or null
     */
    initWithButtons(tableId, options = {}) {
        const buttonOptions = {
            dom: '<"row mb-3"<"col-sm-12 col-md-4"l><"col-sm-12 col-md-4 text-center"B><"col-sm-12 col-md-4"f>>rt<"row mt-3"<"col-sm-12 col-md-5"i><"col-sm-12 col-md-7"p>>',
            buttons: [
                {
                    text: '<i class="bi bi-clipboard"></i> 复制',
                    className: 'btn btn-sm btn-outline-secondary',
                    action: () => TableCopy.copyTable(tableId)
                },
                {
                    text: '<i class="bi bi-download"></i> CSV',
                    className: 'btn btn-sm btn-outline-secondary',
                    action: () => TableCopy.downloadCSV(tableId, tableId)
                }
            ]
        };

        return this.init(tableId, { ...buttonOptions, ...options });
    }
};

/**
 * Initialize DataTables on a table element (global function for backward compatibility).
 * @param {string} tableId - The ID of the table element
 * @param {Object} options - DataTables configuration options
 * @returns {Object|null} - DataTable instance or null
 */
function initDataTable(tableId, options = {}) {
    return DataTableManager.init(tableId, options);
}

// Auto-initialize DataTables on page load for tables with 'auto-datatable' class
document.addEventListener('DOMContentLoaded', function () {
    DataTableManager.initAll('auto-datatable');
});

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        TableCopy,
        DataTableManager,
        copyTableToClipboard,
        downloadTableAsCSV,
        copyDataToClipboard,
        initDataTable,
        showCopySuccess
    };
}
