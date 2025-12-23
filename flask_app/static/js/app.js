/**
 * Main JavaScript module for Immune Repertoire Analysis Web Application
 */

// Application state management
const AppState = {
    currentFile: null,
    analysisConfig: {
        type: null,
        fileId: null,
        fieldMapping: {},
        chartConfig: {}
    },
    userConfig: {
        defaultColorScheme: 'viridis',
        defaultFigureSize: [10, 8],
        defaultFontSize: 12,
        locale: 'zh-CN'
    },

    // Load user configuration from localStorage
    loadConfig() {
        const saved = localStorage.getItem('userConfig');
        if (saved) {
            try {
                this.userConfig = JSON.parse(saved);
            } catch (e) {
                console.error('Failed to load user config:', e);
            }
        }
    },

    // Save user configuration to localStorage
    saveConfig() {
        localStorage.setItem('userConfig', JSON.stringify(this.userConfig));
    }
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
    AppState.loadConfig();
    initializeSidebar();
    initializeSidebarCollapse();
    initializeResponsiveCharts();
    handleWindowResize();
});

// Sidebar toggle for mobile and tablet
function initializeSidebar() {
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');

    if (sidebarToggle && sidebar) {
        // Toggle sidebar on button click
        sidebarToggle.addEventListener('click', function (e) {
            e.stopPropagation();
            toggleSidebar();
        });

        // Close sidebar when clicking overlay
        if (sidebarOverlay) {
            sidebarOverlay.addEventListener('click', function () {
                closeSidebar();
            });
        }

        // Close sidebar when clicking a nav link on mobile
        const navLinks = sidebar.querySelectorAll('.nav-link');
        navLinks.forEach(link => {
            link.addEventListener('click', function () {
                if (window.innerWidth < 992) {
                    closeSidebar();
                }
            });
        });

        // Close sidebar on escape key
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && sidebar.classList.contains('show')) {
                closeSidebar();
            }
        });

        // Handle swipe gestures for mobile
        let touchStartX = 0;
        let touchEndX = 0;

        document.addEventListener('touchstart', function (e) {
            touchStartX = e.changedTouches[0].screenX;
        }, { passive: true });

        document.addEventListener('touchend', function (e) {
            touchEndX = e.changedTouches[0].screenX;
            handleSwipe();
        }, { passive: true });

        function handleSwipe() {
            const swipeThreshold = 50;
            const swipeDistance = touchEndX - touchStartX;

            // Swipe right to open sidebar (from left edge)
            if (swipeDistance > swipeThreshold && touchStartX < 50 && !sidebar.classList.contains('show')) {
                openSidebar();
            }
            // Swipe left to close sidebar
            else if (swipeDistance < -swipeThreshold && sidebar.classList.contains('show')) {
                closeSidebar();
            }
        }
    }
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const sidebarToggle = document.getElementById('sidebarToggle');

    if (sidebar) {
        const isOpen = sidebar.classList.toggle('show');

        if (sidebarOverlay) {
            sidebarOverlay.classList.toggle('show', isOpen);
        }

        if (sidebarToggle) {
            sidebarToggle.setAttribute('aria-expanded', isOpen);
        }

        // Prevent body scroll when sidebar is open on mobile
        if (window.innerWidth < 768) {
            document.body.style.overflow = isOpen ? 'hidden' : '';
        }
    }
}

function openSidebar() {
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const sidebarToggle = document.getElementById('sidebarToggle');

    if (sidebar && !sidebar.classList.contains('show')) {
        sidebar.classList.add('show');
        if (sidebarOverlay) sidebarOverlay.classList.add('show');
        if (sidebarToggle) sidebarToggle.setAttribute('aria-expanded', 'true');

        if (window.innerWidth < 768) {
            document.body.style.overflow = 'hidden';
        }
    }
}

function closeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const sidebarToggle = document.getElementById('sidebarToggle');

    if (sidebar && sidebar.classList.contains('show')) {
        sidebar.classList.remove('show');
        if (sidebarOverlay) sidebarOverlay.classList.remove('show');
        if (sidebarToggle) sidebarToggle.setAttribute('aria-expanded', 'false');
        document.body.style.overflow = '';
    }
}

// Sidebar collapse functionality for desktop
function initializeSidebarCollapse() {
    const collapseBtn = document.getElementById('sidebarCollapseBtn');
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('mainContent');
    const collapseIcon = document.getElementById('collapseIcon');

    if (!collapseBtn || !sidebar) return;

    // Load saved collapse state
    const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
    if (isCollapsed && window.innerWidth >= 992) {
        sidebar.classList.add('collapsed');
        if (mainContent) mainContent.classList.add('sidebar-collapsed');
        if (collapseIcon) collapseIcon.classList.replace('bi-chevron-left', 'bi-chevron-right');
    }

    // Toggle collapse on button click
    collapseBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();

        // Only allow collapse on desktop
        if (window.innerWidth < 992) return;

        const isCurrentlyCollapsed = sidebar.classList.toggle('collapsed');

        if (mainContent) {
            mainContent.classList.toggle('sidebar-collapsed', isCurrentlyCollapsed);
        }

        if (collapseIcon) {
            if (isCurrentlyCollapsed) {
                collapseIcon.classList.replace('bi-chevron-left', 'bi-chevron-right');
            } else {
                collapseIcon.classList.replace('bi-chevron-right', 'bi-chevron-left');
            }
        }

        // Save state
        localStorage.setItem('sidebarCollapsed', isCurrentlyCollapsed);

        // Trigger resize event for charts
        window.dispatchEvent(new Event('resize'));
    });

    // Reset collapse state on mobile
    window.addEventListener('resize', function () {
        if (window.innerWidth < 992) {
            sidebar.classList.remove('collapsed');
            if (mainContent) mainContent.classList.remove('sidebar-collapsed');
            if (collapseIcon) collapseIcon.classList.replace('bi-chevron-right', 'bi-chevron-left');
        }
    });
}

// Initialize responsive chart containers
function initializeResponsiveCharts() {
    const chartContainers = document.querySelectorAll('.chart-container');

    chartContainers.forEach(container => {
        // Add responsive class
        container.classList.add('chart-responsive');

        // If using ECharts, set up resize observer
        if (typeof echarts !== 'undefined') {
            const chartInstance = echarts.getInstanceByDom(container);
            if (chartInstance) {
                // Resize chart when container size changes
                const resizeObserver = new ResizeObserver(() => {
                    chartInstance.resize();
                });
                resizeObserver.observe(container);
            }
        }
    });
}

// Handle window resize events
function handleWindowResize() {
    let resizeTimeout;

    window.addEventListener('resize', function () {
        // Debounce resize events
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function () {
            // Close sidebar on resize to larger screen
            if (window.innerWidth >= 992) {
                const sidebar = document.getElementById('sidebar');
                const sidebarOverlay = document.getElementById('sidebarOverlay');

                if (sidebar) sidebar.classList.remove('show');
                if (sidebarOverlay) sidebarOverlay.classList.remove('show');
                document.body.style.overflow = '';
            }

            // Resize all ECharts instances
            if (typeof echarts !== 'undefined') {
                const chartContainers = document.querySelectorAll('.chart-container');
                chartContainers.forEach(container => {
                    const chartInstance = echarts.getInstanceByDom(container);
                    if (chartInstance) {
                        chartInstance.resize();
                    }
                });
            }
        }, 250);
    });
}

// Utility function to get current breakpoint
function getCurrentBreakpoint() {
    const width = window.innerWidth;
    if (width < 576) return 'xs';
    if (width < 768) return 'sm';
    if (width < 992) return 'md';
    if (width < 1200) return 'lg';
    if (width < 1400) return 'xl';
    return 'xxl';
}

// Check if device is touch-enabled
function isTouchDevice() {
    return ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);
}

// API helper functions
const API = {
    baseUrl: '/api',

    async get(endpoint) {
        const response = await fetch(`${this.baseUrl}${endpoint}`);
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        return response.json();
    },

    async post(endpoint, data) {
        const response = await fetch(`${this.baseUrl}${endpoint}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        return response.json();
    },

    async delete(endpoint) {
        const response = await fetch(`${this.baseUrl}${endpoint}`, {
            method: 'DELETE'
        });
        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }
        return response.json();
    }
};

// Utility functions
const Utils = {
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleString(AppState.userConfig.locale);
    },

    showToast(message, type = 'info') {
        // Simple toast notification
        const toast = document.createElement('div');
        toast.className = `alert alert-${type} position-fixed top-0 end-0 m-3`;
        toast.style.zIndex = '9999';
        toast.textContent = message;
        document.body.appendChild(toast);

        setTimeout(() => {
            toast.remove();
        }, 3000);
    }
};
