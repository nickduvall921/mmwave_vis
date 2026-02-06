(function () {
    const STORAGE_KEY = 'switchStudio.activeTab';
    let tabButtons = [];
    let tabPanels = [];
    let activeTab = null;

    function parsePanelList(raw) {
        if (!raw) return [];
        return raw
            .split(',')
            .map((item) => item.trim())
            .filter(Boolean);
    }

    function normalizeTabName(tabName) {
        if (tabName === 'live') return 'zones';
        return tabName;
    }

    function applyTab(tabName) {
        const normalizedTab = normalizeTabName(tabName);
        if (!normalizedTab) return;
        activeTab = normalizedTab;

        tabButtons.forEach((button) => {
            const isActive = button.getAttribute('data-tab-target') === normalizedTab;
            button.classList.toggle('active', isActive);
            button.setAttribute('aria-selected', String(isActive));
        });

        tabPanels.forEach((panel) => {
            const targets = parsePanelList(panel.getAttribute('data-tab-panels'));
            const shouldShow = targets.length === 0 || targets.includes(normalizedTab);
            panel.style.display = shouldShow ? '' : 'none';
        });

        try {
            localStorage.setItem(STORAGE_KEY, normalizedTab);
        } catch (err) {
            // Ignore storage errors (private mode / restricted browser context)
        }
    }

    function getInitialTab(defaultTab) {
        try {
            const stored = normalizeTabName(localStorage.getItem(STORAGE_KEY));
            if (stored && tabButtons.some((button) => button.getAttribute('data-tab-target') === stored)) {
                return stored;
            }
        } catch (err) {
            // Ignore storage errors
        }

        const normalizedDefaultTab = normalizeTabName(defaultTab);
        if (normalizedDefaultTab && tabButtons.some((button) => button.getAttribute('data-tab-target') === normalizedDefaultTab)) {
            return normalizedDefaultTab;
        }

        if (tabButtons.length > 0) {
            return tabButtons[0].getAttribute('data-tab-target');
        }
        return null;
    }

    function init(options) {
        const opts = options || {};
        const root = opts.root || document;
        tabButtons = Array.from(root.querySelectorAll('[data-tab-target]'));
        tabPanels = Array.from(root.querySelectorAll('[data-tab-panels]'));

        tabButtons.forEach((button) => {
            button.addEventListener('click', () => {
                const nextTab = button.getAttribute('data-tab-target');
                if (!nextTab || nextTab === activeTab) return;
                applyTab(nextTab);
                if (typeof opts.onTabChange === 'function') {
                    opts.onTabChange(nextTab);
                }
            });
        });

        const initial = getInitialTab(opts.defaultTab || 'zones');
        applyTab(initial);
        if (initial && typeof opts.onTabChange === 'function') {
            opts.onTabChange(initial);
        }
    }

    window.SwitchStudioTabs = {
        init,
        setActiveTab: applyTab,
        getActiveTab: () => activeTab
    };
})();
