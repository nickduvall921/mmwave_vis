// Small DOM helpers: element builder, toasts, notices above the map,
// confirmation dialog, popovers and number formatting.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function h(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
        if (v == null || v === false) continue;
        if (k === 'class') node.className = v;
        else if (k === 'dataset') Object.assign(node.dataset, v);
        else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v === true ? '' : v);
    }
    for (const c of children.flat()) {
        if (c == null || c === false) continue;
        node.append(c instanceof Node ? c : String(c));
    }
    return node;
}

// Set text only when it changed, so 10 Hz updates don't touch the DOM needlessly
export function setText(node, text) {
    if (node.textContent !== text) node.textContent = text;
}

const MINUS = '−';
export function num(v) {
    const n = Math.round(Number(v));
    return n < 0 ? MINUS + Math.abs(n) : String(n);
}
export function span(a, b) {
    return `${num(a)} to ${num(b)}`;
}
export function plural(n, word) {
    return `${n} ${word}${n === 1 ? '' : 's'}`;
}

// --- Toasts ---------------------------------------------------------------

export function toast(message, type = 'info', duration = 4000) {
    const root = $('#toasts');
    const node = h('div', { class: `toast ${type}`, role: type === 'error' ? 'alert' : 'status' }, message);
    root.append(node);
    while (root.children.length > 4) root.firstElementChild.remove();
    setTimeout(() => {
        node.classList.add('leaving');
        setTimeout(() => node.remove(), 250);
    }, duration);
}

// --- Notices: persistent messages above the map, one per key ---------------

const notices = new Map();   // key → { sig, node, action }

// Callers repeat a notice on every packet, so an unchanged one is left alone: replacing it
// would restart its role=alert/status announcement and drop focus from its button.
export function setNotice(key, { tone = 'info', title, text, action, link }) {
    const sig = JSON.stringify([tone, title, text, action && action.label, link && link.href, link && link.label]);
    const old = notices.get(key);
    if (old && old.sig === sig) {
        old.action = action;
        return;
    }
    const entry = { sig, node: null, action };
    const body = h('div', { class: 'notice-body' },
        title ? h('strong', null, title) : null,
        text ? h('span', null, ' ' + text) : null,
        link ? h('a', { href: link.href, target: '_blank', rel: 'noopener' }, link.label) : null);
    entry.node = h('div', { class: `notice ${tone}`, role: tone === 'danger' ? 'alert' : 'status' }, body,
        action ? h('button', { class: 'btn small', type: 'button', onclick: () => entry.action.onClick() }, action.label) : null);
    if (old) old.node.replaceWith(entry.node);
    else $('#notices').append(entry.node);
    notices.set(key, entry);
}

export function clearNotice(key) {
    const entry = notices.get(key);
    if (entry) {
        entry.node.remove();
        notices.delete(key);
    }
}

// --- Files -------------------------------------------------------------------

export function downloadBlob(blob, filename) {
    const link = h('a', { href: URL.createObjectURL(blob), download: filename });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
}

// A switch name made safe for a file name
export function fileSafe(name, fallback) {
    return String(name || '').replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '') || fallback;
}

// --- Confirmation dialog ---------------------------------------------------

export function confirmAction(message, { confirm = 'Continue', danger = false } = {}) {
    const dialog = $('#confirmDialog');
    if (!dialog || typeof dialog.showModal !== 'function') {
        return Promise.resolve(window.confirm(message));
    }
    $('#confirmText').textContent = message;
    const ok = $('#confirmOk');
    ok.textContent = confirm;
    ok.classList.toggle('danger', danger);
    ok.classList.toggle('primary', !danger);
    return new Promise(resolve => {
        dialog.addEventListener('close', () => resolve(dialog.returnValue === 'ok'), { once: true });
        dialog.returnValue = '';
        dialog.showModal();
        ok.focus();
    });
}

// --- Popovers and menus ----------------------------------------------------

let openPopover = null;

export function closePopover() {
    if (!openPopover) return;
    openPopover.panel.hidden = true;
    openPopover.button.setAttribute('aria-expanded', 'false');
    openPopover = null;
}

export function togglePopover(button, panel, onOpen) {
    const wasOpen = openPopover && openPopover.panel === panel;
    closePopover();
    if (wasOpen) return;
    panel.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    openPopover = { button, panel };
    if (onOpen) onOpen();
}

export function bindPopover(button, panel, onOpen) {
    button.addEventListener('click', e => {
        e.stopPropagation();
        togglePopover(button, panel, onOpen);
    });
}

document.addEventListener('click', e => {
    if (openPopover && !openPopover.panel.contains(e.target) && !openPopover.button.contains(e.target)) closePopover();
});
document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && openPopover && !e.defaultPrevented) {
        const button = openPopover.button;
        closePopover();
        button.focus();
        e.preventDefault();   // this Escape is used up; other handlers (layout mode) leave it be
    }
});
