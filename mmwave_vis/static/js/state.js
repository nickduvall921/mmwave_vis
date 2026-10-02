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

export function zoneName(category, area) {
    return ZONE_TYPE[category].name(area.slice(4));
}

export const state = {
    socket: null,
    stack: null,              // 'z2m' | 'zha' | null
    device: '',               // selected device topic
    deviceName: '',           // its friendly name
    zones: emptyZones(),
    zoneReportAt: freshReportTimes(),
    areaOccupied: [false, false, false, false],
    pending: {},              // "category:area" → saved zone (or null for a delete) the switch hasn't confirmed yet
    edit: null,               // { category, area, draft, isNew } while a zone is being edited
    arranging: false,         // room layout mode
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
