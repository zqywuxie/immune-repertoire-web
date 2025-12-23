/**
 * TabManager - 管理Tab标签页状态和切换
 * Requirements: 15.3, 15.5, 15.6
 */
class TabManager {
    /**
     * 初始化TabManager
     * @param {string} containerId - Tab容器的ID
     */
    constructor(containerId) {
        this.containerId = containerId;
        this.container = null;
        this.tabs = new Map(); // 存储每个tab的状态
        this.sharedData = {}; // 所有tab共享的数据
        this.activeTabId = null;
        this.storageKey = `tabManager_${containerId}`;
    }

    /**
     * 初始化Tab管理器
     */
    initialize() {
        this.container = document.getElementById(this.containerId);
        if (!this.container) {
            console.error(`Tab container with id "${this.containerId}" not found`);
            return;
        }

        // 获取所有tab元素
        const tabElements = this.container.querySelectorAll('[data-bs-toggle="tab"]');

        // 为每个tab添加事件监听
        tabElements.forEach(tabElement => {
            const tabId = tabElement.getAttribute('href').substring(1); // 移除#号

            // 初始化tab状态
            this.tabs.set(tabId, {
                id: tabId,
                state: {},
                initialized: false
            });

            // 添加tab切换事件监听
            tabElement.addEventListener('shown.bs.tab', (event) => {
                this.onTabShown(tabId);
            });

            tabElement.addEventListener('hidden.bs.tab', (event) => {
                this.onTabHidden(tabId);
            });
        });

        // 恢复上次的tab状态
        this.restoreLastActiveTab();

        console.log('TabManager initialized with tabs:', Array.from(this.tabs.keys()));
    }

    /**
     * 切换到指定Tab
     * @param {string} tabId - Tab的ID
     */
    switchTab(tabId) {
        if (!this.tabs.has(tabId)) {
            console.error(`Tab with id "${tabId}" not found`);
            return;
        }

        // 使用Bootstrap的tab API切换
        const tabElement = this.container.querySelector(`[href="#${tabId}"]`);
        if (tabElement) {
            const tab = new bootstrap.Tab(tabElement);
            tab.show();
        }
    }

    /**
     * Tab显示时的回调
     * @param {string} tabId - Tab的ID
     */
    onTabShown(tabId) {
        this.activeTabId = tabId;

        // 恢复tab状态
        const tabInfo = this.tabs.get(tabId);
        if (tabInfo && !tabInfo.initialized) {
            this.restoreTabState(tabId);
            tabInfo.initialized = true;
        }

        // 保存当前活动tab
        this.saveActiveTab(tabId);

        // 触发自定义事件
        this.dispatchTabEvent('tabShown', tabId);
    }

    /**
     * Tab隐藏时的回调
     * @param {string} tabId - Tab的ID
     */
    onTabHidden(tabId) {
        // 保存tab状态
        this.saveTabState(tabId, this.tabs.get(tabId).state);

        // 触发自定义事件
        this.dispatchTabEvent('tabHidden', tabId);
    }

    /**
     * 保存Tab状态
     * @param {string} tabId - Tab的ID
     * @param {Object} state - 要保存的状态对象
     */
    saveTabState(tabId, state) {
        if (!this.tabs.has(tabId)) {
            console.error(`Tab with id "${tabId}" not found`);
            return;
        }

        // 更新内存中的状态
        this.tabs.get(tabId).state = { ...state };

        // 保存到sessionStorage
        try {
            const allStates = this.getAllTabStates();
            sessionStorage.setItem(this.storageKey, JSON.stringify(allStates));
        } catch (error) {
            console.error('Failed to save tab state:', error);
        }
    }

    /**
     * 恢复Tab状态
     * @param {string} tabId - Tab的ID
     * @returns {Object} 恢复的状态对象
     */
    restoreTabState(tabId) {
        if (!this.tabs.has(tabId)) {
            console.error(`Tab with id "${tabId}" not found`);
            return {};
        }

        try {
            const savedStates = sessionStorage.getItem(this.storageKey);
            if (savedStates) {
                const allStates = JSON.parse(savedStates);
                if (allStates[tabId]) {
                    this.tabs.get(tabId).state = allStates[tabId];
                    return allStates[tabId];
                }
            }
        } catch (error) {
            console.error('Failed to restore tab state:', error);
        }

        return {};
    }

    /**
     * 获取所有Tab的状态
     * @returns {Object} 所有tab的状态对象
     */
    getAllTabStates() {
        const states = {};
        this.tabs.forEach((tabInfo, tabId) => {
            states[tabId] = tabInfo.state;
        });
        return states;
    }

    /**
     * 在所有Tab间共享数据
     * @param {string} key - 数据键
     * @param {*} value - 数据值
     */
    shareData(key, value) {
        this.sharedData[key] = value;

        // 保存到sessionStorage
        try {
            sessionStorage.setItem(`${this.storageKey}_shared`, JSON.stringify(this.sharedData));
        } catch (error) {
            console.error('Failed to save shared data:', error);
        }

        // 触发数据共享事件
        this.dispatchTabEvent('dataShared', null, { key, value });
    }

    /**
     * 获取共享数据
     * @param {string} key - 数据键
     * @returns {*} 数据值
     */
    getSharedData(key) {
        // 首先尝试从内存获取
        if (key in this.sharedData) {
            return this.sharedData[key];
        }

        // 尝试从sessionStorage恢复
        try {
            const savedSharedData = sessionStorage.getItem(`${this.storageKey}_shared`);
            if (savedSharedData) {
                this.sharedData = JSON.parse(savedSharedData);
                return this.sharedData[key];
            }
        } catch (error) {
            console.error('Failed to get shared data:', error);
        }

        return undefined;
    }

    /**
     * 清除共享数据
     * @param {string} key - 数据键（可选，不提供则清除所有）
     */
    clearSharedData(key = null) {
        if (key) {
            delete this.sharedData[key];
        } else {
            this.sharedData = {};
        }

        // 更新sessionStorage
        try {
            sessionStorage.setItem(`${this.storageKey}_shared`, JSON.stringify(this.sharedData));
        } catch (error) {
            console.error('Failed to clear shared data:', error);
        }
    }

    /**
     * 保存当前活动的tab
     * @param {string} tabId - Tab的ID
     */
    saveActiveTab(tabId) {
        try {
            sessionStorage.setItem(`${this.storageKey}_active`, tabId);
        } catch (error) {
            console.error('Failed to save active tab:', error);
        }
    }

    /**
     * 恢复上次活动的tab
     */
    restoreLastActiveTab() {
        try {
            const lastActiveTab = sessionStorage.getItem(`${this.storageKey}_active`);
            if (lastActiveTab && this.tabs.has(lastActiveTab)) {
                this.switchTab(lastActiveTab);
            }
        } catch (error) {
            console.error('Failed to restore last active tab:', error);
        }
    }

    /**
     * 获取当前活动的tab ID
     * @returns {string|null} 当前活动的tab ID
     */
    getActiveTabId() {
        return this.activeTabId;
    }

    /**
     * 获取指定tab的状态
     * @param {string} tabId - Tab的ID
     * @returns {Object} Tab的状态对象
     */
    getTabState(tabId) {
        if (!this.tabs.has(tabId)) {
            console.error(`Tab with id "${tabId}" not found`);
            return {};
        }
        return { ...this.tabs.get(tabId).state };
    }

    /**
     * 清除所有tab状态
     */
    clearAllStates() {
        this.tabs.forEach((tabInfo) => {
            tabInfo.state = {};
            tabInfo.initialized = false;
        });
        this.sharedData = {};

        try {
            sessionStorage.removeItem(this.storageKey);
            sessionStorage.removeItem(`${this.storageKey}_shared`);
            sessionStorage.removeItem(`${this.storageKey}_active`);
        } catch (error) {
            console.error('Failed to clear all states:', error);
        }
    }

    /**
     * 触发自定义tab事件
     * @param {string} eventName - 事件名称
     * @param {string|null} tabId - Tab的ID
     * @param {Object} detail - 事件详情
     */
    dispatchTabEvent(eventName, tabId, detail = {}) {
        const event = new CustomEvent(eventName, {
            detail: {
                tabId,
                tabManager: this,
                ...detail
            }
        });
        this.container.dispatchEvent(event);
    }

    /**
     * 监听tab事件
     * @param {string} eventName - 事件名称
     * @param {Function} callback - 回调函数
     */
    on(eventName, callback) {
        this.container.addEventListener(eventName, callback);
    }

    /**
     * 移除tab事件监听
     * @param {string} eventName - 事件名称
     * @param {Function} callback - 回调函数
     */
    off(eventName, callback) {
        this.container.removeEventListener(eventName, callback);
    }
}

// 导出为全局变量（用于非模块环境）
if (typeof window !== 'undefined') {
    window.TabManager = TabManager;
}
