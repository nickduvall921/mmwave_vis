(function () {
    const pendingChanges = new Map();
    const latestConfig = {};
    const inputElements = new Map();

    let socket = null;
    let packetInfoEl = null;
    let dirtyBarEl = null;
    let dirtyTextEl = null;
    let applyBtnEl = null;
    let discardBtnEl = null;
    let toastContainerEl = null;

    function normalizeForCompare(value) {
        if (Array.isArray(value)) {
            return value.map((item) => normalizeForCompare(item));
        }
        if (value && typeof value === 'object') {
            const normalized = {};
            Object.keys(value).sort().forEach((key) => {
                normalized[key] = normalizeForCompare(value[key]);
            });
            return normalized;
        }
        return value;
    }

    function valuesEqual(a, b) {
        if ((a && typeof a === 'object') || (b && typeof b === 'object')) {
            try {
                return JSON.stringify(normalizeForCompare(a)) === JSON.stringify(normalizeForCompare(b));
            } catch (err) {
                return false;
            }
        }

        if (typeof a === 'number' || typeof b === 'number') {
            const an = Number(a);
            const bn = Number(b);
            if (Number.isFinite(an) && Number.isFinite(bn)) return an === bn;
        }
        return String(a) === String(b);
    }

    function syncLedColorSelect(element, value) {
        if (!element || element.tagName !== 'SELECT') return;
        const normalizedValue = value === undefined || value === null ? '' : String(value);

        Array.from(element.options)
            .filter((option) => option.dataset.customColorValue === '1')
            .forEach((option) => option.remove());

        if (!normalizedValue) {
            element.selectedIndex = -1;
            return;
        }

        const existingOption = Array.from(element.options).find((option) => option.value === normalizedValue);
        if (existingOption) {
            element.value = normalizedValue;
            return;
        }

        const customOption = document.createElement('option');
        customOption.value = normalizedValue;
        customOption.textContent = `Current (${normalizedValue})`;
        customOption.dataset.customColorValue = '1';
        element.appendChild(customOption);
        element.value = normalizedValue;
    }

    function refreshLedSliderDisplay(element) {
        if (!element || element.type !== 'range') return;
        const targetId = element.dataset.sliderValueTarget;
        if (!targetId) return;
        const valueElement = document.getElementById(targetId);
        if (!valueElement) return;

        const rawValue = element.value === '' ? '--' : String(element.value);
        const maxValue = Number(element.max);
        if (rawValue !== '--' && maxValue === 101 && Number(rawValue) === 101) {
            valueElement.innerText = 'Sync';
            return;
        }
        valueElement.innerText = rawValue === '--' ? '--' : `${rawValue}%`;
    }

    function setInputValue(element, value) {
        if (!element) return;
        if (element.tagName === 'SPAN') {
            element.innerText = value === undefined || value === null ? '--' : String(value);
            return;
        }
        if (element.tagName === 'SELECT' && element.dataset.ledColorSelect === '1') {
            syncLedColorSelect(element, value);
            return;
        }
        if (element.type === 'checkbox') {
            element.checked = value === true || value === 'ON' || value === 'true';
            return;
        }
        if (Array.isArray(value)) {
            element.value = value.join(', ');
            return;
        }
        if (value && typeof value === 'object') {
            element.value = JSON.stringify(value);
            return;
        }
        if (value === undefined || value === null) {
            element.value = '';
        } else {
            element.value = value;
        }
        if (element.type === 'range' && element.dataset.ledBrightnessSlider === '1') {
            refreshLedSliderDisplay(element);
        }
    }

    function updateDirtyUi() {
        const count = pendingChanges.size;
        const isDirty = count > 0;

        if (dirtyBarEl) {
            dirtyBarEl.classList.toggle('dirty-active', isDirty);
            dirtyBarEl.hidden = !isDirty;
            dirtyBarEl.setAttribute('aria-hidden', String(!isDirty));
        }
        if (typeof document !== 'undefined' && document && document.body && document.body.classList) {
            document.body.classList.toggle('dirty-bar-visible', isDirty);
        }
        if (dirtyTextEl) {
            dirtyTextEl.innerText = isDirty ? `${count} pending change${count === 1 ? '' : 's'}` : 'No pending changes';
        }
        if (applyBtnEl) applyBtnEl.disabled = !isDirty;
        if (discardBtnEl) discardBtnEl.disabled = !isDirty;
    }

    function showToast(type, message, durationMs) {
        if (!toastContainerEl) return;
        const toast = document.createElement('div');
        const normalizedType = type || 'info';
        toast.className = `studio-toast studio-toast-${normalizedType}`;
        toast.innerText = message || '';
        toastContainerEl.appendChild(toast);

        const timeout = Number.isFinite(durationMs) ? durationMs : 2800;
        setTimeout(() => {
            toast.classList.add('fade-out');
            setTimeout(() => {
                if (toast.parentNode) toast.parentNode.removeChild(toast);
            }, 220);
        }, timeout);
    }

    function setPacketStatus(mode, message) {
        if (!packetInfoEl) return;
        if (message) packetInfoEl.innerText = message;

        const colorMap = {
            saved: '#4caf50',
            syncing: '#00bcd4',
            error: '#ff5252',
            info: '#00bcd4'
        };
        packetInfoEl.style.color = colorMap[mode] || '#00bcd4';
    }

    function queueChange(param, value, inputElement) {
        if (!param) return;

        inputElements.set(param, inputElement);
        const baseline = latestConfig[param];

        if (baseline !== undefined && valuesEqual(baseline, value)) {
            pendingChanges.delete(param);
        } else {
            pendingChanges.set(param, value);
        }

        updateDirtyUi();
    }

    function applyPendingChanges() {
        if (!socket || pendingChanges.size === 0) return;

        const entries = Array.from(pendingChanges.entries());
        const batchId = Date.now();
        entries.forEach(([param, value], index) => {
            socket.emit('update_parameter', {
                param: param,
                value: value,
                request_id: `apply-${batchId}-${index}-${param}`
            });
            latestConfig[param] = value;
        });

        pendingChanges.clear();
        updateDirtyUi();
        setPacketStatus('saved', 'Changes sent');
        showToast('saved', `Sent ${entries.length} change${entries.length === 1 ? '' : 's'}.`, 1800);
    }

    function discardPendingChanges() {
        if (pendingChanges.size === 0) return;

        pendingChanges.forEach((_, param) => {
            const input = inputElements.get(param) || document.getElementById(param);
            setInputValue(input, latestConfig[param]);
        });

        pendingChanges.clear();
        updateDirtyUi();
        setPacketStatus('info', 'Pending changes discarded');
        showToast('info', 'Discarded pending changes.', 1800);
    }

    function syncConfig(configPayload) {
        if (!configPayload || typeof configPayload !== 'object') return;

        Object.entries(configPayload).forEach(([key, value]) => {
            latestConfig[key] = value;
            if (pendingChanges.has(key)) return;
            const element = document.getElementById(key);
            if (element) setInputValue(element, value);
        });
    }

    function resetForDeviceChange() {
        pendingChanges.clear();
        inputElements.clear();
        updateDirtyUi();
    }

    function handleCommandResult(result) {
        if (!result || !result.status) return;

        if (result.status === 'error') {
            setPacketStatus('error', result.message ? `Error: ${result.message}` : 'Command failed');
            showToast('error', result.message || 'Command failed', 3200);
            return;
        }

        if (result.action === 'force_sync_get' || result.action === 'force_sync_query_areas') {
            setPacketStatus('syncing', 'Sync requested');
            showToast('syncing', 'Sync request sent.', 1400);
        }
    }

    function init(options) {
        const opts = options || {};
        socket = opts.socket || null;
        packetInfoEl = opts.packetInfoEl || null;
        dirtyBarEl = opts.dirtyBarEl || null;
        dirtyTextEl = opts.dirtyTextEl || null;
        applyBtnEl = opts.applyBtnEl || null;
        discardBtnEl = opts.discardBtnEl || null;
        toastContainerEl = opts.toastContainerEl || null;

        if (applyBtnEl) applyBtnEl.addEventListener('click', applyPendingChanges);
        if (discardBtnEl) discardBtnEl.addEventListener('click', discardPendingChanges);
        updateDirtyUi();
    }

    window.SwitchStudioState = {
        init,
        queueChange,
        applyPendingChanges,
        discardPendingChanges,
        syncConfig,
        resetForDeviceChange,
        showToast,
        setPacketStatus,
        handleCommandResult,
        isPending: (param) => pendingChanges.has(param),
        getPendingCount: () => pendingChanges.size
    };
})();
