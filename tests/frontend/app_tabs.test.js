const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class MockClassList {
    constructor() {
        this.values = new Set();
    }

    toggle(name, force) {
        if (typeof force === 'undefined') {
            if (this.values.has(name)) {
                this.values.delete(name);
            } else {
                this.values.add(name);
            }
            return;
        }
        if (force) {
            this.values.add(name);
        } else {
            this.values.delete(name);
        }
    }

    contains(name) {
        return this.values.has(name);
    }
}

class MockElement {
    constructor(attributes) {
        this.attributes = { ...(attributes || {}) };
        this.classList = new MockClassList();
        this.style = { display: '' };
        this.listeners = {};
    }

    getAttribute(name) {
        return this.attributes[name] ?? null;
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }

    addEventListener(type, callback) {
        this.listeners[type] = callback;
    }

    click() {
        if (this.listeners.click) {
            this.listeners.click();
        }
    }
}

function loadTabsModule(options) {
    const scriptPath = path.resolve(__dirname, '../../switch_studio/static/js/app_tabs.js');
    const source = fs.readFileSync(scriptPath, 'utf8');

    const storageMap = new Map();
    if (options && options.storedTab) {
        storageMap.set('switchStudio.activeTab', options.storedTab);
    }

    const localStorage = {
        getItem: (key) => (storageMap.has(key) ? storageMap.get(key) : null),
        setItem: (key, value) => storageMap.set(key, String(value)),
    };

    const buttons = [
        new MockElement({ 'data-tab-target': 'presence' }),
        new MockElement({ 'data-tab-target': 'zones' }),
        new MockElement({ 'data-tab-target': 'load' }),
    ];
    const panels = [
        new MockElement({ 'data-tab-panels': 'presence' }),
        new MockElement({ 'data-tab-panels': 'zones' }),
        new MockElement({ 'data-tab-panels': 'load' }),
        new MockElement({ 'data-tab-panels': '' }),
    ];

    const root = {
        querySelectorAll: (selector) => {
            if (selector === '[data-tab-target]') return buttons;
            if (selector === '[data-tab-panels]') return panels;
            return [];
        },
    };

    const context = {
        window: {},
        document: {},
        localStorage,
        console,
    };
    context.global = context;

    vm.createContext(context);
    vm.runInContext(source, context, { filename: scriptPath });

    return {
        tabs: context.window.SwitchStudioTabs,
        buttons,
        panels,
        storageMap,
        root,
    };
}

test('tab module applies default tab, toggles panels, and persists on click', () => {
    const { tabs, buttons, panels, storageMap, root } = loadTabsModule();
    tabs.init({ root, defaultTab: 'live' });

    assert.equal(tabs.getActiveTab(), 'zones');
    assert.equal(buttons[1].classList.contains('active'), true);
    assert.equal(buttons[0].classList.contains('active'), false);
    assert.equal(panels[1].style.display, '');
    assert.equal(panels[0].style.display, 'none');
    assert.equal(storageMap.get('switchStudio.activeTab'), 'zones');

    buttons[0].click();
    assert.equal(tabs.getActiveTab(), 'presence');
    assert.equal(buttons[0].classList.contains('active'), true);
    assert.equal(buttons[1].classList.contains('active'), false);
    assert.equal(panels[1].style.display, 'none');
    assert.equal(panels[0].style.display, '');
    assert.equal(storageMap.get('switchStudio.activeTab'), 'presence');
});

test('tab module restores persisted tab from storage', () => {
    const { tabs, buttons, panels, root } = loadTabsModule({ storedTab: 'live' });
    tabs.init({ root, defaultTab: 'live' });

    assert.equal(tabs.getActiveTab(), 'zones');
    assert.equal(buttons[1].classList.contains('active'), true);
    assert.equal(panels[1].style.display, '');
    assert.equal(panels[0].style.display, 'none');
    assert.equal(panels[2].style.display, 'none');
});
