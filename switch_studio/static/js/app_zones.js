(function () {
    const DEFAULT_LIMITS = {
        xMin: -900,
        xMax: 900,
        yMin: -200,
        yMax: 1400,
        zMin: -500,
        zMax: 500,
        minSpan: 20
    };

    let chartEl = null;
    let dataTableBodyEl = null;
    let zoneStatusEl = null;
    let commandLogEl = null;
    let stateApi = null;
    let updateTimestampFn = null;
    let getLayoutFn = null;
    let getIsEditingFn = null;
    let getIsInteractingFn = null;
    let shouldRenderTargetsFn = null;
    let limits = { ...DEFAULT_LIMITS };

    let targetHistory = {};
    let historyLength = 15;
    let lastCommandId = null;
    let hideZoneStatusTimer = null;
    let targetsSuppressedByGate = false;

    function toRoundedInt(value, fallback) {
        const parsed = Number(value);
        if (!Number.isFinite(parsed)) return fallback;
        return Math.round(parsed);
    }

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function enforceMinSpan(minVal, maxVal, boundMin, boundMax, minSpan) {
        if ((maxVal - minVal) >= minSpan) {
            return { minVal, maxVal };
        }

        let center = Math.round((minVal + maxVal) / 2);
        minVal = center - Math.floor(minSpan / 2);
        maxVal = minVal + minSpan;

        if (minVal < boundMin) {
            minVal = boundMin;
            maxVal = minVal + minSpan;
        }
        if (maxVal > boundMax) {
            maxVal = boundMax;
            minVal = maxVal - minSpan;
        }

        return { minVal, maxVal };
    }

    function sortPair(a, b) {
        const low = Math.min(a, b);
        const high = Math.max(a, b);
        return [low, high];
    }

    function normalizeZoneConfig(rawConfig, options) {
        const opts = options || {};
        const clampToBounds = opts.clampToBounds !== false;
        const allowZeroSpan = opts.allowZeroSpan === true;

        let xMin = toRoundedInt(rawConfig?.x_min, 0);
        let xMax = toRoundedInt(rawConfig?.x_max, 0);
        let yMin = toRoundedInt(rawConfig?.y_min, 0);
        let yMax = toRoundedInt(rawConfig?.y_max, 0);
        let zMin = toRoundedInt(rawConfig?.z_min, 0);
        let zMax = toRoundedInt(rawConfig?.z_max, 0);

        [xMin, xMax] = sortPair(xMin, xMax);
        [yMin, yMax] = sortPair(yMin, yMax);
        [zMin, zMax] = sortPair(zMin, zMax);

        if (clampToBounds) {
            xMin = clamp(xMin, limits.xMin, limits.xMax);
            xMax = clamp(xMax, limits.xMin, limits.xMax);
            yMin = clamp(yMin, limits.yMin, limits.yMax);
            yMax = clamp(yMax, limits.yMin, limits.yMax);
            zMin = clamp(zMin, limits.zMin, limits.zMax);
            zMax = clamp(zMax, limits.zMin, limits.zMax);
            [xMin, xMax] = sortPair(xMin, xMax);
            [yMin, yMax] = sortPair(yMin, yMax);
            [zMin, zMax] = sortPair(zMin, zMax);
        }

        if (!allowZeroSpan) {
            ({ minVal: xMin, maxVal: xMax } = enforceMinSpan(xMin, xMax, limits.xMin, limits.xMax, limits.minSpan));
            ({ minVal: yMin, maxVal: yMax } = enforceMinSpan(yMin, yMax, limits.yMin, limits.yMax, limits.minSpan));
            ({ minVal: zMin, maxVal: zMax } = enforceMinSpan(zMin, zMax, limits.zMin, limits.zMax, limits.minSpan));
        }

        return {
            x_min: xMin,
            x_max: xMax,
            y_min: yMin,
            y_max: yMax,
            z_min: zMin,
            z_max: zMax
        };
    }

    function validateZoneConfig(rawConfig, options) {
        const opts = options || {};
        const allowZeroSpan = opts.allowZeroSpan === true;
        const normalized = normalizeZoneConfig(rawConfig, {
            allowZeroSpan: allowZeroSpan,
            clampToBounds: true
        });
        const errors = [];

        const width = normalized.x_max - normalized.x_min;
        const depth = normalized.y_max - normalized.y_min;
        const height = normalized.z_max - normalized.z_min;

        if (!allowZeroSpan) {
            if (width < limits.minSpan) errors.push(`Width span must be at least ${limits.minSpan} cm.`);
            if (depth < limits.minSpan) errors.push(`Depth span must be at least ${limits.minSpan} cm.`);
            if (height < limits.minSpan) errors.push(`Height span must be at least ${limits.minSpan} cm.`);
        }

        if (normalized.x_min < limits.xMin || normalized.x_max > limits.xMax) {
            errors.push(`Width must stay within ${limits.xMin} to ${limits.xMax} cm.`);
        }
        if (normalized.y_min < limits.yMin || normalized.y_max > limits.yMax) {
            errors.push(`Depth must stay within ${limits.yMin} to ${limits.yMax} cm.`);
        }
        if (normalized.z_min < limits.zMin || normalized.z_max > limits.zMax) {
            errors.push(`Height must stay within ${limits.zMin} to ${limits.zMax} cm.`);
        }

        return {
            valid: errors.length === 0,
            errors: errors,
            normalized: normalized
        };
    }

    function buildAreaPayload(areaKey, zoneConfig) {
        const normalized = normalizeZoneConfig(zoneConfig, { allowZeroSpan: false, clampToBounds: true });
        const payload = {};
        payload[areaKey] = {
            width_min: normalized.x_min,
            width_max: normalized.x_max,
            depth_min: normalized.y_min,
            depth_max: normalized.y_max,
            height_min: normalized.z_min,
            height_max: normalized.z_max
        };
        return payload;
    }

    function appendCommandLog(message, type) {
        if (!commandLogEl || !message) return;

        const empty = commandLogEl.querySelector('.command-log-empty');
        if (empty) empty.remove();

        const entry = document.createElement('div');
        const normalizedType = type || 'info';
        const now = new Date().toLocaleTimeString([], { hour12: false });
        entry.className = `command-log-entry log-${normalizedType}`;
        entry.innerText = `[${now}] ${message}`;
        commandLogEl.appendChild(entry);

        while (commandLogEl.children.length > 40) {
            commandLogEl.removeChild(commandLogEl.firstChild);
        }
        commandLogEl.scrollTop = commandLogEl.scrollHeight;
    }

    function setPacketStatus(mode, message) {
        if (stateApi && typeof stateApi.setPacketStatus === 'function') {
            stateApi.setPacketStatus(mode, message);
        }
    }

    function showToast(mode, message, timeoutMs) {
        if (stateApi && typeof stateApi.showToast === 'function') {
            stateApi.showToast(mode, message, timeoutMs);
        }
    }

    function showZoneStatus(message, type) {
        if (!zoneStatusEl) return;

        const backgroundMap = {
            saved: 'rgba(76, 175, 80, 0.9)',
            syncing: 'rgba(0, 188, 212, 0.92)',
            info: 'rgba(255, 152, 0, 0.95)',
            error: 'rgba(255, 82, 82, 0.95)'
        };
        zoneStatusEl.style.background = backgroundMap[type] || backgroundMap.info;
        zoneStatusEl.innerText = message;
        zoneStatusEl.style.display = 'block';

        if (hideZoneStatusTimer) clearTimeout(hideZoneStatusTimer);
        hideZoneStatusTimer = setTimeout(() => {
            zoneStatusEl.style.display = 'none';
        }, 5000);
    }

    function setPendingCommand(actionId) {
        const parsedId = Number(actionId);
        if (!Number.isFinite(parsedId)) return;
        lastCommandId = parsedId;

        const labelMap = {
            1: 'Auto-Config Interference',
            3: 'Clear Interference',
            4: 'Reset Detection Zones',
            5: 'Clear Stay Zones'
        };
        const statusMap = {
            1: 'Scanning for interference...',
            3: 'Clearing interference zones...',
            4: 'Resetting detection zones...',
            5: 'Clearing stay zones...'
        };
        const label = labelMap[parsedId] || `Command ${parsedId}`;
        const status = statusMap[parsedId] || `Sending ${label}...`;

        setPacketStatus('syncing', status);
        appendCommandLog(`Sent ${label}`, 'syncing');
    }

    function handleCommandResult(result) {
        if (!result || !result.action) return;
        if (result.action !== 'send_command') return;

        const payload = result.payload || {};
        const controlID = payload.controlID || 'unknown_command';
        const actionId = payload.action_id;

        if (result.status === 'sent') {
            appendCommandLog(`Accepted ${controlID} (${actionId})`, 'saved');
            showToast('saved', `Command queued: ${controlID}`, 1600);
            return;
        }

        if (result.status === 'error') {
            const message = result.message || 'Command failed';
            appendCommandLog(`Failed ${controlID}: ${message}`, 'error');
            setPacketStatus('error', `Error: ${message}`);
            showToast('error', message, 3000);
        }
    }

    function handleInterferenceZones(zones) {
        if (lastCommandId === null) return;

        const zoneCount = Array.isArray(zones) ? zones.length : 0;
        let message = '';
        let type = 'info';

        if (lastCommandId === 1) {
            if (zoneCount === 0) {
                message = 'Scan complete: no active interference found.';
                type = 'saved';
            } else {
                message = `Auto-config complete: found ${zoneCount} interference zone${zoneCount === 1 ? '' : 's'}.`;
                type = 'info';
            }
        } else if (lastCommandId === 3) {
            if (zoneCount === 0) {
                message = 'Interference cleared: zones reset.';
                type = 'saved';
            } else {
                message = `Clear command finished but ${zoneCount} zone${zoneCount === 1 ? '' : 's'} still reported.`;
                type = 'error';
            }
        } else if (lastCommandId === 4) {
            message = 'Detection zone reset command completed.';
            type = 'saved';
        } else if (lastCommandId === 5) {
            message = 'Stay zone clear command completed.';
            type = 'saved';
        } else {
            message = 'Command completed.';
            type = 'info';
        }

        showZoneStatus(message, type);
        appendCommandLog(message, type);

        const packetMode = type === 'error' ? 'error' : (type === 'saved' ? 'saved' : 'info');
        setPacketStatus(packetMode, message);
        showToast(type === 'error' ? 'error' : packetMode, message, 2200);

        lastCommandId = null;
    }

    function clearPendingCommand() {
        lastCommandId = null;
    }

    function getPendingCommandId() {
        return lastCommandId;
    }

    function resetHistory() {
        targetHistory = {};
        targetsSuppressedByGate = false;
        if (dataTableBodyEl) {
            dataTableBodyEl.innerHTML = '<tr><td colspan="5" class="no-data">No targets detected</td></tr>';
        }
    }

    function clearTargetVisualization(message) {
        targetHistory = {};
        const notice = message || 'No targets detected';

        if (chartEl && window.Plotly) {
            try {
                window.Plotly.restyle(chartEl, { x: [[]], y: [[]], text: [[]] }, [0]);
                window.Plotly.restyle(chartEl, { x: [[]], y: [[]] }, [1]);
            } catch (err) {
                // Ignore render failures during transient chart states.
            }
        }

        if (dataTableBodyEl) {
            dataTableBodyEl.innerHTML = `<tr><td colspan="5" class="no-data">${notice}</td></tr>`;
        }
    }

    function normalizeTarget(target) {
        return {
            id: toRoundedInt(target?.id, 0),
            x: toRoundedInt(target?.x, 0),
            y: toRoundedInt(target?.y, 0),
            z: toRoundedInt(target?.z, 0),
            dop: toRoundedInt(target?.dop, 0)
        };
    }

    function getMotionLabelFromDoppler(doppler) {
        const dop = Number(doppler) || 0;
        if (dop > 10 || dop < -10) return 'Moving';
        return 'Stationary';
    }

    function getFriendlyTargetLabel(idValue) {
        const id = Number(idValue) || 0;
        const prefix = `D${id}`;
        if (id === 1) return `${prefix} (Primary)`;
        return `${prefix} (Secondary)`;
    }

    function handleNewData(msg, currentTopic) {
        if (!msg || !msg.topic || !msg.payload) return false;
        if (!currentTopic || msg.topic !== currentTopic) return false;
        if (!chartEl || !window.Plotly) return false;

        const shouldRenderTargets = typeof shouldRenderTargetsFn === 'function'
            ? !!shouldRenderTargetsFn()
            : true;
        if (!shouldRenderTargets) {
            if (!targetsSuppressedByGate) {
                clearTargetVisualization('Standby: all occupancy areas clear.');
                setPacketStatus('info', 'Standby: all occupancy areas clear');
            }
            targetsSuppressedByGate = true;
            return true;
        }
        targetsSuppressedByGate = false;

        const payload = msg.payload;
        const targets = Array.isArray(payload.targets) ? payload.targets.map(normalizeTarget) : [];
        const data = { targets: targets };

        if (typeof updateTimestampFn === 'function') {
            updateTimestampFn();
        }
        setPacketStatus('info', `Targets Visible: ${data.targets.length}`);

        const currentIds = new Set(data.targets.map((t) => t.id));
        Object.keys(targetHistory).forEach((id) => {
            if (!currentIds.has(Number(id))) delete targetHistory[id];
        });

        data.targets.forEach((target) => {
            if (!targetHistory[target.id]) targetHistory[target.id] = [];
            targetHistory[target.id].push({ x: target.x, y: target.y });
            if (targetHistory[target.id].length > historyLength) targetHistory[target.id].shift();
        });

        const historyX = [];
        const historyY = [];
        Object.values(targetHistory).forEach((points) => {
            points.forEach((point) => {
                historyX.push(point.x);
                historyY.push(point.y);
            });
            historyX.push(null);
            historyY.push(null);
        });

        const sizes = data.targets.map((target) => Math.max(8, Math.min(40, 10 + (target.z / 5))));
        const isEditing = typeof getIsEditingFn === 'function' ? !!getIsEditingFn() : false;
        const isInteracting = typeof getIsInteractingFn === 'function' ? !!getIsInteractingFn() : false;

        if (isEditing) {
            if (isInteracting) return true;
            window.Plotly.restyle(chartEl, {
                x: [data.targets.map((t) => t.x), historyX],
                y: [data.targets.map((t) => t.y), historyY],
                text: [data.targets.map((t) => `${getFriendlyTargetLabel(t.id)}<br>${getMotionLabelFromDoppler(t.dop)}`), null],
                'marker.size': [sizes, null]
            }, [0, 1]);
        } else {
            const layout = typeof getLayoutFn === 'function' ? getLayoutFn() : undefined;
            window.Plotly.react(chartEl, [
                {
                    x: data.targets.map((t) => t.x),
                    y: data.targets.map((t) => t.y),
                    text: data.targets.map((t) => `${getFriendlyTargetLabel(t.id)}<br>${getMotionLabelFromDoppler(t.dop)}`),
                    mode: 'markers+text',
                    textposition: 'top center',
                    marker: { size: sizes, color: '#1bd2dc', line: { color: '#dcfaff', width: 1.2 } },
                    textfont: { color: '#bde8ef', size: 10, family: 'DM Sans, sans-serif' },
                    type: 'scatter'
                },
                { x: historyX, y: historyY, mode: 'lines', line: { color: '#2e93bc', width: 1.6 }, opacity: 0.2, type: 'scatter' }
            ], layout);
        }

        if (!dataTableBodyEl) return true;
        if (data.targets.length === 0) {
            dataTableBodyEl.innerHTML = '<tr><td colspan="5" class="no-data">Scanning for motion...</td></tr>';
            return true;
        }

        dataTableBodyEl.innerHTML = '';
        data.targets.forEach((target) => {
            let dopStatus = 'Stationary';
            let dopClass = 'doppler-stationary';
            if (target.dop > 10) {
                dopStatus = 'Moving';
                dopClass = 'doppler-moving';
            } else if (target.dop < -10) {
                dopStatus = 'Approaching';
                dopClass = 'doppler-approaching';
            }
            const targetLabel = getFriendlyTargetLabel(target.id);
            const targetClass = Number(target.id) === 1 ? 'target-primary' : 'target-secondary';
            dataTableBodyEl.innerHTML += `<tr><td class="target-id-cell"><span class="target-id-tag ${targetClass}"><span class="target-id-dot"></span>${targetLabel}</span></td><td class="target-num">${target.x}</td><td class="target-num">${target.y}</td><td class="target-num">${target.z}</td><td class="doppler-cell"><span class="doppler-badge ${dopClass}">${dopStatus}</span></td></tr>`;
        });

        return true;
    }

    function init(options) {
        const opts = options || {};
        chartEl = opts.chartEl || document.getElementById(opts.chartId || 'chart');
        dataTableBodyEl = opts.dataTableBodyEl || document.getElementById(opts.dataTableBodyId || 'dataTableBody');
        zoneStatusEl = opts.zoneStatusEl || document.getElementById(opts.zoneStatusId || 'zoneStatus');
        commandLogEl = opts.commandLogEl || document.getElementById(opts.commandLogId || 'commandLog');
        stateApi = opts.stateApi || null;
        updateTimestampFn = opts.updateTimestamp || null;
        getLayoutFn = opts.getLayout || null;
        getIsEditingFn = opts.getIsEditing || null;
        getIsInteractingFn = opts.getIsInteracting || null;
        shouldRenderTargetsFn = opts.shouldRenderTargets || null;
        historyLength = Number.isFinite(opts.historyLength) ? opts.historyLength : 15;
        limits = {
            xMin: Number.isFinite(opts.limits?.xMin) ? opts.limits.xMin : DEFAULT_LIMITS.xMin,
            xMax: Number.isFinite(opts.limits?.xMax) ? opts.limits.xMax : DEFAULT_LIMITS.xMax,
            yMin: Number.isFinite(opts.limits?.yMin) ? opts.limits.yMin : DEFAULT_LIMITS.yMin,
            yMax: Number.isFinite(opts.limits?.yMax) ? opts.limits.yMax : DEFAULT_LIMITS.yMax,
            zMin: Number.isFinite(opts.limits?.zMin) ? opts.limits.zMin : DEFAULT_LIMITS.zMin,
            zMax: Number.isFinite(opts.limits?.zMax) ? opts.limits.zMax : DEFAULT_LIMITS.zMax,
            minSpan: Number.isFinite(opts.limits?.minSpan) ? opts.limits.minSpan : DEFAULT_LIMITS.minSpan
        };
        return window.SwitchStudioZones;
    }

    window.SwitchStudioZones = {
        init,
        normalizeZoneConfig,
        validateZoneConfig,
        buildAreaPayload,
        setPendingCommand,
        handleCommandResult,
        handleInterferenceZones,
        clearPendingCommand,
        getPendingCommandId,
        resetHistory,
        clearTargetVisualization,
        handleNewData,
        appendCommandLog
    };
})();
