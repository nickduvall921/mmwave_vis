// Display preferences kept in this browser. Storage can be missing or throw
// (private windows, blocked site data), so every access is guarded and the
// page works the same without it.

let store = null;
try {
    store = window.localStorage;
    store.getItem('probe');
} catch (e) {
    store = null;
}

export function get(key) {
    try { return store ? store.getItem(key) : null; } catch (e) { return null; }
}

export function set(key, value) {
    try { if (store) store.setItem(key, String(value)); } catch (e) { /* storage full or blocked */ }
}

export function getBool(key, fallback) {
    const v = get(key);
    return v === null ? fallback : v === 'true';
}

export function getInt(key, fallback) {
    const v = parseInt(get(key), 10);
    return Number.isNaN(v) ? fallback : v;
}
