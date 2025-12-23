/**
 * Sequencing Depth Analysis Page
 * Requirements: 15.1, 15.2, 15.3, 15.4, 15.6, 15.7
 */

// 初始化TabManager
let tabManager;

document.addEventListener('DOMContentLoaded', function () {
    // 初始化Tab管理器
    tabManager = new TabManager('sequencingDepthTabContent');
    tabManager.initialize();

    // 设置默认日期为今天
    document.getElementById('pptDate').valueAsDate = new Date();

    // 初始化FileUploader组件回调
    if (window.FileUploader) {
        window.FileUploader.onFileSelected = function (data) {
            handleFileSelected(data);
        };

        window.FileUploader.onUploadComplete = function (data) {
            handleUploadComplete(data);
        };
    }

    // 初始化各个Tab
    initPptTab();
    initVizTab();
    initChartTab();

    // 监听Tab切换事件
    tabManager.on('tabShown', function (event) {
        console.log('Tab shown:', event.detail.tabId);

        // 检查是否有共享的文件
        const sharedFile = tabManager.getSharedData('uploadedFile');
        if (sharedFile) {
            updateFileInfoForTab(event.detail.tabId, sharedFile);
        }
    });

    // 监听数据共享事件
    tabManager.on('dataShared', function (event) {
        console.log('Data shared:', event.detail.key, event.detail.value);
    });
});

/**
 * 处理文件选择
 */
function handleFileSelected(data) {
    const file = data.file;
    const activeTab = document.querySelector('.tab-pane.active').id;

    // 更新当前tab的文件信息
    updateFileInfoForTab(activeTab, file);

    // 启用相应的生成按钮
    enableGenerateButton(activeTab);

    // 分享文件数据到其他tab
    tabManager.shareData('uploadedFile', file);
}

/**
 * 处理上传完成
 */
function handleUploadComplete(data) {
    const file = data.file;
    const activeTab = document.querySelector('.tab-pane.active').id;

    // 更新文件列表
    if (window.FileUploader) {
        window.FileUploader.loadFileList();
    }

    // 显示成功通知
    showNotification('文件上传成功', 'success');
}

/**
 * 更新tab的文件信息显示
 */
function updateFileInfoForTab(tabId, file) {
    let fileInfoId, fileNameId;

    switch (tabId) {
        case 'ppt-tab':
            fileInfoId = 'pptFileInfo';
            fileNameId = 'pptFileName';
            break;
        case 'viz-tab':
            fileInfoId = 'vizFileInfo';
            fileNameId = 'vizFileName';
            break;
        case 'chart-tab':
            fileInfoId = 'chartFileInfo';
            fileNameId = 'chartFileName';
            break;
    }

    if (fileInfoId && fileNameId) {
        const fileInfo = document.getElementById(fileInfoId);
        const fileName = document.getElementById(fileNameId);

        if (fileInfo && fileName) {
            fileInfo.style.display = 'block';
            fileName.textContent = file.original_name || file.name;
        }
    }
}

/**
 * 启用生成按钮
 */
function enableGenerateButton(tabId) {
    let generateBtnId;

    switch (tabId) {
        case 'ppt-tab':
            generateBtnId = 'generatePptBtn';
            break;
        case 'viz-tab':
            generateBtnId = 'generateVizBtn';
            break;
        case 'chart-tab':
            generateBtnId = 'generateChartBtn';
            break;
    }

    if (generateBtnId) {
        const btn = document.getElementById(generateBtnId);
        if (btn) {
            btn.disabled = false;
        }
    }
}

/**
 * 显示通知
 */
function showNotification(message, type = 'info') {
    // 创建通知元素
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    document.body.appendChild(notification);

    // 自动移除
    setTimeout(() => {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    }, 5000);
}

/**
 * 初始化PPT Tab
 */
function initPptTab() {
    const fileInput = document.getElementById('pptFileInput');
    const uploadSection = document.getElementById('pptFileUpload');
    const generateBtn = document.getElementById('generatePptBtn');

    // 文件选择
    fileInput.addEventListener('change', function (e) {
        if (e.target.files.length > 0) {
            const file = e.target.files[0];
            handleFileUpload(file, 'ppt');
        }
    });

    // 拖放支持
    uploadSection.addEventListener('dragover', function (e) {
        e.preventDefault();
        uploadSection.style.borderColor = '#0d6efd';
    });

    uploadSection.addEventListener('dragleave', function (e) {
        e.preventDefault();
        uploadSection.style.borderColor = '#dee2e6';
    });

    uploadSection.addEventListener('drop', function (e) {
        e.preventDefault();
        uploadSection.style.borderColor = '#dee2e6';

        if (e.dataTransfer.files.length > 0) {
            const file = e.dataTransfer.files[0];
            fileInput.files = e.dataTransfer.files;
            handleFileUpload(file, 'ppt');
        }
    });

    // 生成PPT按钮
    generateBtn.addEventListener('click', function () {
        generatePptReport();
    });
}

/**
 * 初始化可视化Tab
 */
function initVizTab() {
    const fileInput = document.getElementById('vizFileInput');
    const uploadSection = document.getElementById('vizFileUpload');
    const generateBtn = document.getElementById('generateVizBtn');

    // 文件选择
    fileInput.addEventListener('change', function (e) {
        if (e.target.files.length > 0) {
            const file = e.target.files[0];
            handleFileUpload(file, 'viz');
        }
    });

    // 拖放支持
    uploadSection.addEventListener('dragover', function (e) {
        e.preventDefault();
        uploadSection.style.borderColor = '#0d6efd';
    });

    uploadSection.addEventListener('dragleave', function (e) {
        e.preventDefault();
        uploadSection.style.borderColor = '#dee2e6';
    });

    uploadSection.addEventListener('drop', function (e) {
        e.preventDefault();
        uploadSection.style.borderColor = '#dee2e6';

        if (e.dataTransfer.files.length > 0) {
            const file = e.dataTransfer.files[0];
            fileInput.files = e.dataTransfer.files;
            handleFileUpload(file, 'viz');
        }
    });

    // 生成可视化按钮
    generateBtn.addEventListener('click', function () {
        generateVisualization();
    });
}

/**
 * 初始化条形图Tab
 */
function initChartTab() {
    const fileInput = document.getElementById('chartFileInput');
    const uploadSection = document.getElementById('chartFileUpload');
    const generateBtn = document.getElementById('generateChartBtn');

    // 文件选择
    fileInput.addEventListener('change', function (e) {
        if (e.target.files.length > 0) {
            const file = e.target.files[0];
            handleFileUpload(file, 'chart');
        }
    });

    // 拖放支持
    uploadSection.addEventListener('dragover', function (e) {
        e.preventDefault();
        uploadSection.style.borderColor = '#0d6efd';
    });

    uploadSection.addEventListener('dragleave', function (e) {
        e.preventDefault();
        uploadSection.style.borderColor = '#dee2e6';
    });

    uploadSection.addEventListener('drop', function (e) {
        e.preventDefault();
        uploadSection.style.borderColor = '#dee2e6';

        if (e.dataTransfer.files.length > 0) {
            const file = e.dataTransfer.files[0];
            fileInput.files = e.dataTransfer.files;
            handleFileUpload(file, 'chart');
        }
    });

    // 生成条形图按钮
    generateBtn.addEventListener('click', function () {
        generateBarChart();
    });
}

/**
 * 处理文件上传
 */
function handleFileUpload(file, tabType) {
    console.log('File uploaded:', file.name, 'for tab:', tabType);

    // 验证文件类型
    const validExtensions = ['.csv', '.xlsx', '.txt'];
    const fileExtension = '.' + file.name.split('.').pop().toLowerCase();

    if (!validExtensions.includes(fileExtension)) {
        showError(`不支持的文件格式: ${fileExtension}`, tabType);
        return;
    }

    // 更新UI
    const uploadSection = document.getElementById(`${tabType}FileUpload`);
    const fileInfo = document.getElementById(`${tabType}FileInfo`);
    const fileName = document.getElementById(`${tabType}FileName`);
    const generateBtn = document.getElementById(`generate${capitalize(tabType)}Btn`);

    uploadSection.classList.add('has-file');
    fileInfo.style.display = 'block';
    fileName.textContent = file.name;
    generateBtn.disabled = false;

    // 共享文件信息到所有Tab
    const fileData = {
        name: file.name,
        size: file.size,
        type: file.type,
        file: file
    };
    tabManager.shareData('uploadedFile', fileData);

    // 保存当前Tab的状态
    const currentTabId = tabManager.getActiveTabId();
    const currentState = tabManager.getTabState(currentTabId);
    currentState.file = fileData;
    tabManager.saveTabState(currentTabId, currentState);
}

/**
 * 更新指定Tab的文件信息
 */
function updateFileInfoForTab(tabId, fileData) {
    const tabPrefix = tabId.replace('-tab', '');
    const fileInfo = document.getElementById(`${tabPrefix}FileInfo`);
    const fileName = document.getElementById(`${tabPrefix}FileName`);
    const uploadSection = document.getElementById(`${tabPrefix}FileUpload`);
    const generateBtn = document.getElementById(`generate${capitalize(tabPrefix)}Btn`);

    if (fileInfo && fileName && uploadSection && generateBtn) {
        uploadSection.classList.add('has-file');
        fileInfo.style.display = 'block';
        fileName.textContent = fileData.name;
        generateBtn.disabled = false;
    }
}

/**
 * 生成PPT报告
 */
async function generatePptReport() {
    const fileData = tabManager.getSharedData('uploadedFile');
    if (!fileData) {
        showError('请先上传数据文件', 'ppt');
        return;
    }

    const title = document.getElementById('pptTitle').value || '测序深度分析报告';
    const author = document.getElementById('pptAuthor').value || '';
    const date = document.getElementById('pptDate').value;

    // 显示进度
    document.getElementById('pptProgress').style.display = 'block';
    document.getElementById('generatePptBtn').disabled = true;

    try {
        // 创建FormData
        const formData = new FormData();
        formData.append('file', fileData.file);
        formData.append('title', title);
        formData.append('author', author);
        formData.append('date', date);

        // 发送请求
        const response = await fetch('/api/sequencing-depth/ppt', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('生成PPT失败');
        }

        const result = await response.json();

        // 显示结果
        displayPptResult(result);

        // 保存状态
        const currentState = tabManager.getTabState('ppt-tab');
        currentState.result = result;
        tabManager.saveTabState('ppt-tab', currentState);

    } catch (error) {
        console.error('Error generating PPT:', error);
        showError('生成PPT报告时出错: ' + error.message, 'ppt');
    } finally {
        document.getElementById('pptProgress').style.display = 'none';
        document.getElementById('generatePptBtn').disabled = false;
    }
}

/**
 * 生成可视化
 */
async function generateVisualization() {
    const fileData = tabManager.getSharedData('uploadedFile');
    if (!fileData) {
        showError('请先上传数据文件', 'viz');
        return;
    }

    const colorScheme = document.getElementById('vizColorScheme').value;
    const width = document.getElementById('vizWidth').value;
    const height = document.getElementById('vizHeight').value;

    // 显示进度
    document.getElementById('vizProgress').style.display = 'block';
    document.getElementById('generateVizBtn').disabled = true;

    try {
        // 创建FormData
        const formData = new FormData();
        formData.append('file', fileData.file);
        formData.append('color_scheme', colorScheme);
        formData.append('width', width);
        formData.append('height', height);

        // 发送请求
        const response = await fetch('/api/sequencing-depth/visualization', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('生成可视化失败');
        }

        const result = await response.json();

        // 显示结果
        displayVizResult(result);

        // 保存状态
        const currentState = tabManager.getTabState('viz-tab');
        currentState.result = result;
        tabManager.saveTabState('viz-tab', currentState);

    } catch (error) {
        console.error('Error generating visualization:', error);
        showError('生成可视化时出错: ' + error.message, 'viz');
    } finally {
        document.getElementById('vizProgress').style.display = 'none';
        document.getElementById('generateVizBtn').disabled = false;
    }
}

/**
 * 生成条形图
 */
async function generateBarChart() {
    const fileData = tabManager.getSharedData('uploadedFile');
    if (!fileData) {
        showError('请先上传数据文件', 'chart');
        return;
    }

    const title = document.getElementById('chartTitle').value || '测序Reads条形图';
    const orientation = document.getElementById('chartOrientation').value;
    const color = document.getElementById('chartColor').value;

    // 显示进度
    document.getElementById('chartProgress').style.display = 'block';
    document.getElementById('generateChartBtn').disabled = true;

    try {
        // 创建FormData
        const formData = new FormData();
        formData.append('file', fileData.file);
        formData.append('title', title);
        formData.append('orientation', orientation);
        formData.append('color', color);

        // 发送请求
        const response = await fetch('/api/sequencing-depth/bar-chart', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error('生成条形图失败');
        }

        const result = await response.json();

        // 显示结果
        displayChartResult(result);

        // 保存状态
        const currentState = tabManager.getTabState('chart-tab');
        currentState.result = result;
        tabManager.saveTabState('chart-tab', currentState);

    } catch (error) {
        console.error('Error generating bar chart:', error);
        showError('生成条形图时出错: ' + error.message, 'chart');
    } finally {
        document.getElementById('chartProgress').style.display = 'none';
        document.getElementById('generateChartBtn').disabled = false;
    }
}

/**
 * 显示PPT结果
 */
function displayPptResult(result) {
    const resultDiv = document.getElementById('pptResult');
    resultDiv.classList.add('has-result');

    resultDiv.innerHTML = `
        <div class="alert alert-success">
            <i class="bi bi-check-circle"></i> PPT报告生成成功！
        </div>
        <div class="card">
            <div class="card-body">
                <h5 class="card-title"><i class="bi bi-file-earmark-ppt"></i> ${result.filename || 'report.pptx'}</h5>
                <p class="card-text text-muted">文件大小: ${formatFileSize(result.size || 0)}</p>
                <a href="${result.download_url}" class="btn btn-primary download-link" download>
                    <i class="bi bi-download"></i> 下载PPT报告
                </a>
            </div>
        </div>
    `;
}

/**
 * 显示可视化结果
 */
function displayVizResult(result) {
    const resultDiv = document.getElementById('vizResult');
    resultDiv.classList.add('has-result');

    resultDiv.innerHTML = `
        <div class="alert alert-success">
            <i class="bi bi-check-circle"></i> 可视化生成成功！
        </div>
        <div class="text-center">
            <img src="${result.image_url}" class="img-fluid" alt="可视化结果" style="max-width: 100%; border-radius: 0.5rem;">
        </div>
        <div class="mt-3">
            <a href="${result.download_url}" class="btn btn-primary download-link" download>
                <i class="bi bi-download"></i> 下载图像
            </a>
        </div>
    `;
}

/**
 * 显示条形图结果
 */
function displayChartResult(result) {
    const resultDiv = document.getElementById('chartResult');
    resultDiv.classList.add('has-result');

    resultDiv.innerHTML = `
        <div class="alert alert-success">
            <i class="bi bi-check-circle"></i> 条形图生成成功！
        </div>
        <div class="text-center">
            <img src="${result.image_url}" class="img-fluid" alt="条形图结果" style="max-width: 100%; border-radius: 0.5rem;">
        </div>
        <div class="mt-3">
            <a href="${result.download_url}" class="btn btn-primary download-link" download>
                <i class="bi bi-download"></i> 下载图像
            </a>
        </div>
    `;
}

/**
 * 显示错误消息
 */
function showError(message, tabType) {
    const resultDiv = document.getElementById(`${tabType}Result`);
    resultDiv.innerHTML = `
        <div class="alert alert-danger">
            <i class="bi bi-exclamation-triangle"></i> ${message}
        </div>
    `;
}

/**
 * 格式化文件大小
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

/**
 * 首字母大写
 */
function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}
