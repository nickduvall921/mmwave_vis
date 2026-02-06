const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadZonesModule() {
    const scriptPath = path.resolve(__dirname, '../../switch_studio/static/js/app_zones.js');
    const source = fs.readFileSync(scriptPath, 'utf8');
    const events = { status: [], toast: [] };

    const context = {
        window: {},
        document: {
            getElementById: () => null,
        },
        console,
        setTimeout,
        clearTimeout,
    };
    context.global = context;

    vm.createContext(context);
    vm.runInContext(source, context, { filename: scriptPath });

    const zones = context.window.SwitchStudioZones;
    zones.init({
        stateApi: {
            setPacketStatus: (mode, message) => events.status.push({ mode, message }),
            showToast: (mode, message) => events.toast.push({ mode, message }),
        },
        limits: {
            xMin: -200,
            xMax: 200,
            yMin: 0,
            yMax: 300,
            zMin: -50,
            zMax: 200,
            minSpan: 20,
        },
    });

    return { zones, events };
}

test('zone payload builder sorts and maps coordinate fields', () => {
    const { zones } = loadZonesModule();
    const payload = zones.buildAreaPayload('area2', {
        x_min: 120,
        x_max: 40,
        y_min: 250,
        y_max: 50,
        z_min: 100,
        z_max: 0,
    });

    const plainPayload = JSON.parse(JSON.stringify(payload));

    assert.deepEqual(plainPayload, {
        area2: {
            width_min: 40,
            width_max: 120,
            depth_min: 50,
            depth_max: 250,
            height_min: 0,
            height_max: 100,
        },
    });
});

test('zone validation normalizes spans and supports allowZeroSpan mode', () => {
    const { zones } = loadZonesModule();

    const normalized = zones.validateZoneConfig(
        { x_min: 1000, x_max: -900, y_min: -80, y_max: 8, z_min: 11, z_max: 12 },
        { allowZeroSpan: false },
    );
    assert.equal(normalized.valid, true);
    assert.equal(normalized.errors.length, 0);
    assert.ok(normalized.normalized.x_min >= -200);
    assert.ok(normalized.normalized.x_max <= 200);
    assert.ok((normalized.normalized.x_max - normalized.normalized.x_min) >= 20);
    assert.ok((normalized.normalized.y_max - normalized.normalized.y_min) >= 20);
    assert.ok((normalized.normalized.z_max - normalized.normalized.z_min) >= 20);

    const zeroSpan = zones.validateZoneConfig(
        { x_min: 10, x_max: 10, y_min: 20, y_max: 20, z_min: 30, z_max: 30 },
        { allowZeroSpan: true },
    );
    assert.equal(zeroSpan.valid, true);
    assert.equal(zeroSpan.normalized.x_min, 10);
    assert.equal(zeroSpan.normalized.x_max, 10);
    assert.equal(zeroSpan.normalized.y_min, 20);
    assert.equal(zeroSpan.normalized.y_max, 20);
    assert.equal(zeroSpan.normalized.z_min, 30);
    assert.equal(zeroSpan.normalized.z_max, 30);
});

test('interference command lifecycle reports completion and clears pending command id', () => {
    const { zones, events } = loadZonesModule();

    zones.setPendingCommand(3);
    assert.equal(zones.getPendingCommandId(), 3);

    zones.handleInterferenceZones([]);

    assert.equal(zones.getPendingCommandId(), null);
    assert.ok(events.status.some((entry) => entry.message.includes('Interference cleared')));
    assert.ok(events.toast.some((entry) => entry.message.includes('Interference cleared')));
});
