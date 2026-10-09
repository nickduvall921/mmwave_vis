// State shared by the page's modules, plus a minimal event bus so the map,
// zone list and editor can react to each other without importing each other.

export const ZONE_TYPES = [
    { category: 'mmwave_detection_areas',    group: 'detection',    title: 'Detection',    name: n => `Area ${n}`,         cls: 'det' },
    { category: 'mmwave_interference_areas', group: 'interference', title: 'Interference', name: n => `Interference ${n}`, cls: 'intf' },
    { category: 'mmwave_stay_areas',         group: 'stay',         title: 'Stay',         name: n => `Stay ${n}`,         cls: 'stay' },
];
export const ZONE_TYPE = Object.fromEntries(ZONE_TYPES.map(t => [t.category, t]));
export const AREAS = ['area1', 'area2', 'area3', 'area4'];
export const ZONE_KEYS = ['x_min', 'x_max', 'y_min', 'y_max', 'z_min', 'z_max'];

export function emptyZones() {
    return Object.fromEntries(ZONE_TYPES.map(t => [t.category, Object.fromEntries(AREAS.map(a => [a, null]))]));
}

// When each zone type last arrived from the switch (0 = not since the device was selected).
// An empty [] zone list is the backend's "nothing reported yet" placeholder and doesn't count.
export function freshReportTimes() {
    return Object.fromEntries(ZONE_TYPES.map(t => [t.category, 0]));
}

// The slot's own name ("Area 2"), whatever the user called it
export function slotName(category, area) {
    return ZONE_TYPE[category].name(area.slice(4));
}

// The name the user gave a zone, or ''
export function customName(category, area) {
    return (state.zoneNames && state.zoneNames[`${category}:${area}`]) || '';
}

// For messages and lists: "Couch (Area 2)", or "Area 2" when it has no name
export function zoneName(category, area) {
    const custom = customName(category, area);
    const slot = slotName(category, area);
    return custom ? `${custom} (${slot})` : slot;
}

export const state = {
    socket: null,
    stack: null,              // 'z2m' | 'zha' | null
    device: '',               // selected device topic
    deviceName: '',           // its friendly name
    zones: emptyZones(),
    zoneReportAt: freshReportTimes(),
    zoneNames: {},            // "category:area" → name (display only, saved by the addon)
    areaOccupied: [false, false, false, false],
    occupied: null,           // the switch's overall occupancy: true / false / null (not reported yet)
    occupiedAt: 0,            // when it last changed
    targetCount: 0,           // targets in the latest report
    settings: {},             // the switch's latest reported settings (mmWaveHoldTime, ...)
    deviceInfo: null,         // firmware, link quality and HA entities (device_info event)
    pending: {},              // "category:area" → saved zone (or null for a delete) the switch hasn't confirmed yet
    edit: null,               // { category, area, draft, isNew } while a zone is being edited
    arranging: false,         // room layout mode
    replay: null,             // a recorded clip being played back instead of live data
    restoring: false,         // a backup restore or multi-zone undo is writing slots
    layout: { x: 0, y: 0, rot: 0, room: null },
    stayInvert: false,
    lastCommandId: null,      // 1 = auto-detect interference, 3 = clear interference
    lastCommandAt: 0,
};

const listeners = new Map();

export function on(event, fn) {
    if (!listeners.has(event)) listeners.set(event, new Set());
    listeners.get(event).add(fn);
}

export function emit(event, data) {
    const fns = listeners.get(event);
    if (fns) for (const fn of fns) fn(data);
}
