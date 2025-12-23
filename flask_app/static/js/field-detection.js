/**
 * 智能字段检测和映射模块
 * 实现三个核心功能:
 * 1. 自动识别并映射默认字段
 * 2. 默认字段强制选择(但支持增删其他字段)
 * 3. 未匹配字段提供用户映射界面
 */

const FieldDetection = {
    // 默认字段配置(必选)
    defaultFieldsConfig: {
        'custom': [],
        'igmetrics': ['D50', 'Gini_index', 'Shannon', 'Reads'],
        'seqdepth': ['Total_Receptor_RNA', 'Reads_per_UMI', 'MigsGood_Total', 'ReadsGood_Total'],
        'seqreads': ['TRA', 'TRB', 'TRD', 'TRG', 'IGH', 'IGK', 'IGL'],
        'bcell_isotype_pdf': []
    },

    /**
     * 智能匹配字段
     * @param {string} defaultField - 默认字段名
     * @param {Array} availableColumns - 可用列名数组
     * @returns {string|null} - 匹配的列名或null
     */
    smartMatch(defaultField, availableColumns) {
        // 1. 精确匹配
        let match = availableColumns.find(col => col === defaultField);
        if (match) return match;

        // 2. 不区分大小写匹配
        match = availableColumns.find(col =>
            col.toLowerCase() === defaultField.toLowerCase()
        );
        if (match) return match;

        // 3. 部分匹配(包含关系)
        match = availableColumns.find(col =>
            col.toLowerCase().includes(defaultField.toLowerCase()) ||
            defaultField.toLowerCase().includes(col.toLowerCase())
        );
        if (match) return match;

        return null;
    },

    /**
     * 检测并映射所有默认字段
     * @param {string} analysisType - 分析类型
     * @param {Array} columns - 可用列名
     * @returns {Object} - 映射结果
     */
    detectFields(analysisType, columns) {
        const requiredDefaults = this.defaultFieldsConfig[analysisType] || [];
        const numericColumns = columns.filter(col =>
            !['Sample', 'sample', 'Chain', 'chain'].includes(col)
        );

        const result = {
            mapped: [],           // 成功映射的字段
            unmapped: [],         // 未映射的默认字段
            fieldMapping: {},     // 默认字段 -> 实际列名的映射
            availableColumns: numericColumns
        };

        requiredDefaults.forEach(defaultField => {
            const matchedColumn = this.smartMatch(defaultField, numericColumns);
            if (matchedColumn) {
                result.mapped.push(matchedColumn);
                result.fieldMapping[defaultField] = matchedColumn;
            } else {
                result.unmapped.push(defaultField);
            }
        });

        return result;
    },

    /**
     * 渲染字段选择UI
     * @param {Object} detectionResult - 检测结果
     * @param {string} containerId - 容器元素ID
     */
    renderFieldSelection(detectionResult, containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const { mapped, unmapped, availableColumns } = detectionResult;
        let html = '';

        // 渲染可用字段复选框
        availableColumns.forEach(column => {
            const isMapped = mapped.includes(column);
            const defaultClass = isMapped ? ' default-field' : '';
            const isDisabled = isMapped; // 必选字段禁用

            html += `
                <div class="form-check${defaultClass}">
                    <input class="form-check-input field-field-checkbox ${isMapped ? 'field-mandatory' : ''}" 
                        type="checkbox" 
                        value="${column}" 
                        ${isMapped ? 'checked disabled' : ''} 
                        onchange="Config.updateFieldSelectedFields()">
                    <label class="form-check-label small">
                        ${column}
                        ${isMapped ? '<i class="bi bi-lock-fill text-warning ms-1" title="必选字段"></i>' : ''}
                    </label>
                </div>
            `;
        });

        // 如果有未映射字段,添加映射界面
        if (unmapped.length > 0) {
            html += `
                <div class="field-mapping-section mt-3">
                    <div class="alert alert-warning py-2 px-3 mb-2" style="font-size: 0.85rem;">
                        <i class="bi bi-exclamation-triangle me-1"></i>
                        <strong>需要映射字段：</strong>以下默认字段未找到，请手动选择对应的列
                    </div>
            `;

            unmapped.forEach(field => {
                html += `
                    <div class="mb-2">
                        <label class="form-label small mb-1"><strong>${field}:</strong></label>
                        <select class="form-select form-select-sm field-mapping-select" 
                                data-default-field="${field}"
                                onchange="FieldDetection.onFieldMapped(this)">
                            <option value="">-- 选择对应列 --</option>
                            ${availableColumns.map(col =>
                    `<option value="${col}">${col}</option>`
                ).join('')}
                        </select>
                    </div>
                `;
            });

            html += '</div>';
        }

        container.innerHTML = html;
    },

    /**
     * 当用户手动映射字段时调用
     * @param {HTMLElement} selectElement - 选择框元素
     */
    onFieldMapped(selectElement) {
        const defaultField = selectElement.dataset.defaultField;
        const mappedColumn = selectElement.value;

        if (mappedColumn) {
            console.log(`Mapped ${defaultField} -> ${mappedColumn}`);

            // 自动勾选映射的列
            const checkbox = document.querySelector(
                `.field-field-checkbox[value="${mappedColumn}"]`
            );
            if (checkbox && !checkbox.disabled) {
                checkbox.checked = true;
                checkbox.disabled = true;
                checkbox.classList.add('field-mandatory');

                // 添加锁图标
                const label = checkbox.nextElementSibling;
                if (label && !label.querySelector('.bi-lock-fill')) {
                    label.innerHTML += ' <i class="bi bi-lock-fill text-warning ms-1" title="必选字段"></i>';
                }

                // 添加默认字段样式
                checkbox.parentElement.classList.add('default-field');
            }

            // 更新已选字段显示
            if (typeof Config !== 'undefined' && Config.updateFieldSelectedFields) {
                Config.updateFieldSelectedFields();
            }
        }
    },

    /**
     * 更新提示文本
     * @param {Object} detectionResult - 检测结果
     * @param {string} hintElementId - 提示元素ID
     */
    updateHint(detectionResult, hintElementId) {
        const hintElement = document.getElementById(hintElementId);
        if (!hintElement) return;

        const { mapped, unmapped } = detectionResult;

        if (mapped.length === 0 && unmapped.length === 0) {
            hintElement.innerHTML = '<i class="bi bi-info-circle me-1"></i><strong>默认字段：</strong>无必选字段，请自由选择';
            return;
        }

        let hintText = '<i class="bi bi-info-circle me-1"></i><strong>默认字段（必选）：</strong>';

        if (mapped.length > 0) {
            hintText += `<span class="text-success">${mapped.join(', ')}</span>`;
        }

        if (unmapped.length > 0) {
            if (mapped.length > 0) hintText += ' ';
            hintText += `<span class="text-danger">未找到: ${unmapped.join(', ')}</span>`;
        }

        hintElement.innerHTML = hintText;
    }
};

// 导出到全局作用域
window.FieldDetection = FieldDetection;
