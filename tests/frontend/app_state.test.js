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
            if (this.values.has(name)) this.values.delete(name);
            else this.values.add(name);
            return;
        }
        if (force) this.values.add(name);
        else this.values.delete(name);
    }

    contains(name) {
        return this.values.has(name);
    }
}

class MockElement {
    constructor(tagName, id) {
        this.tagName = String(tagName || 'div').toUpperCase();
        this.id = id || '';
        this.dataset = {};
        this.attributes = {};
        this.style = {};
        this.listeners = {};
        this.classList = new MockClassList();
        this.children = [];
        this.options = [];
        this.parentNode = null;
        this.disabled = false;
        this.hidden = false;
        this.innerText = '';
        this.textContent = '';
        this.value = '';
        this.type = '';
        this.selectedIndex = 0;
    }

    addEventListener(type, callback) {
        this.listeners[type] = callback;
    }

    click() {
        if (this.listeners.click) this.listeners.click();
    }

    appendChild(child) {
        child.parentNode = this;
        this.children.push(child);
        if (this.tagName === 'SELECT' && child.tagName === 'OPTION') {
            this.options.push(child);
        }
        return child;
    }

    removeChild(child) {
        this.children = this.children.filter((item) => item !== child);
        if (this.tagName === 'SELECT' && child.tagName === 'OPTION') {
            this.options = this.options.filter((item) => item !== child);
        }
        child.parentNode = null;
    }

    remove() {
        if (this.parentNode) {
            this.parentNode.removeChild(this);
        }
    }

    setAttribute(name, value) {
        this.attributes[name] = String(value);
    }

    getAttribute(name) {
        if (Object.prototype.hasOwnProperty.call(this.attributes, name)) {
            return this.attributes[name];
        }
        return null;
    }
}

class MockDocument {
    constructor() {
        this.registry = new Map();
    }

    createElement(tagName) {
        return new MockElement(tagName);
    }

    getElementById(id) {
        return this.registry.get(id) || null;
    }

    register(element) {
        if (element && element.id) this.registry.set(element.id, element);
        return element;
    }
}

function createElement(document, tagName, id, props) {
    const element = new MockElement(tagName, id);
    Object.assign(element, props || {});
    document.register(element);
    return element;
}

function appendOption(document, select, value, label) {
    const option = document.createElement('option');
    option.value = String(value);
    option.textContent = label || String(value);
    select.appendChild(option);
    return option;
}

function loadStateModule(document) {
    const scriptPath = path.resolve(__dirname, '../../switch_studio/static/js/app_state.js');
    const source = fs.readFileSync(scriptPath, 'utf8');

    const context = {
        window: {},
        document,
        console,
        setTimeout,
        clearTimeout,
    };
    context.global = context;

    vm.createContext(context);
    vm.runInContext(source, context, { filename: scriptPath });
    return context.window.SwitchStudioState;
}

function initState(document) {
    const state = loadStateModule(document);
    state.init({
        socket: { emit: () => {} },
        packetInfoEl: createElement(document, 'span', 'packetInfo'),
        dirtyBarEl: createElement(document, 'div', 'dirtyBar'),
        dirtyTextEl: createElement(document, 'span', 'dirtyText'),
        applyBtnEl: createElement(document, 'button', 'applyBtn'),
        discardBtnEl: createElement(document, 'button', 'discardBtn'),
        toastContainerEl: null,
    });
    return state;
}

test('state sync keeps LED color preset select aligned and supports non-preset values', () => {
    const document = new MockDocument();
    const ledColorSelect = createElement(document, 'select', 'ledColorWhenOn');
    ledColorSelect.dataset.ledColorSelect = '1';
    appendOption(document, ledColorSelect, 0, 'Red');
    appendOption(document, ledColorSelect, 21, 'Orange');
    appendOption(document, ledColorSelect, 170, 'Blue');

    const state = initState(document);
    state.syncConfig({ ledColorWhenOn: 99 });
    assert.equal(ledColorSelect.value, '99');
    assert.equal(ledColorSelect.options.some((option) => option.dataset.customColorValue === '1'), true);

    state.syncConfig({ ledColorWhenOn: 21 });
    assert.equal(ledColorSelect.value, '21');
    assert.equal(ledColorSelect.options.some((option) => option.dataset.customColorValue === '1'), false);
});

test('discard restores LED brightness slider and refreshes Sync label', () => {
    const document = new MockDocument();
    const slider = createElement(document, 'input', 'ledIntensityWhenOn', { type: 'range', max: '101' });
    slider.dataset.ledBrightnessSlider = '1';
    slider.dataset.sliderValueTarget = 'ledIntensityWhenOn__value';
    const sliderLabel = createElement(document, 'span', 'ledIntensityWhenOn__value');

    const state = initState(document);
    state.syncConfig({ ledIntensityWhenOn: 101 });
    assert.equal(slider.value, 101);
    assert.equal(sliderLabel.innerText, 'Sync');

    slider.value = 12;
    state.queueChange('ledIntensityWhenOn', 12, slider);
    assert.equal(state.getPendingCount(), 1);

    state.discardPendingChanges();
    assert.equal(state.getPendingCount(), 0);
    assert.equal(slider.value, 101);
    assert.equal(sliderLabel.innerText, 'Sync');
});

test('dirty bar is only visible while pending changes exist', () => {
    const document = new MockDocument();
    const slider = createElement(document, 'input', 'ledIntensityWhenOn', { type: 'range' });
    const dirtyBar = createElement(document, 'div', 'dirtyBar');

    const state = loadStateModule(document);
    state.init({
        socket: { emit: () => {} },
        packetInfoEl: createElement(document, 'span', 'packetInfo'),
        dirtyBarEl: dirtyBar,
        dirtyTextEl: createElement(document, 'span', 'dirtyText'),
        applyBtnEl: createElement(document, 'button', 'applyBtn'),
        discardBtnEl: createElement(document, 'button', 'discardBtn'),
        toastContainerEl: null,
    });

    assert.equal(dirtyBar.hidden, true);
    assert.equal(dirtyBar.classList.contains('dirty-active'), false);

    state.syncConfig({ ledIntensityWhenOn: 90 });
    state.queueChange('ledIntensityWhenOn', 50, slider);
    assert.equal(dirtyBar.hidden, false);
    assert.equal(dirtyBar.classList.contains('dirty-active'), true);

    state.discardPendingChanges();
    assert.equal(dirtyBar.hidden, true);
    assert.equal(dirtyBar.classList.contains('dirty-active'), false);
});
