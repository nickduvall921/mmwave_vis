// The radar map: an SVG drawn in screen pixels so text and lines stay crisp
// at any zoom. Everything the switch reports (zones, targets, field of view)
// lives in the sensor's own frame; the room layout places the sensor in the
// room ("world") frame, and the view maps the world onto the screen.

import { ZONE_TYPES, AREAS } from './state.js';
import { num } from './ui.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const DEG = Math.PI / 180;

export const FOV_RATED = 60;       // degrees either side of straight ahead
export const FOV_EXTENDED = 75;
export const FOV_RANGE = 600;      // cm
export const DEFAULT_RANGE = { xMin: -600, xMax: 600, yMin: -100, yMax: 650 };

const PAD = 16;                    // px kept clear around the requested range
const MIN_SPAN = 60;               // cm, closest zoom
const MAX_SPAN = 8000;             // cm, furthest zoom
const REC_CHUNK = 500;             // recorded points per <path>
const LAYERS = ['grid', 'room', 'zones', 'recording', 'trails', 'targets', 'edit', 'sensor'];
const WALL_SNAP_PX = 12;
const sensorHit = () => coarse.matches ? 24 : 16;   // px radius for grabbing the switch

const coarse = window.matchMedia('(pointer: coarse)');
const wide = window.matchMedia('(min-width: 901px)');

function el(tag, attrs, parent) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const k in attrs) if (attrs[k] != null) node.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(node);
    return node;
}

const r1 = v => Math.round(v * 10) / 10;
const pts = list => list.map(p => `${r1(p[0])},${r1(p[1])}`).join(' ');
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

function metres(cm) {
    return (cm / 100).toFixed(2).replace(/\.?0+$/, '') + ' m';
}

const CORNERS = [['x_min', 'y_min'], ['x_max', 'y_min'], ['x_max', 'y_max'], ['x_min', 'y_max']];
// Resize handles: which edges each one moves
const HANDLES = [
    ['x_min', 'y_min'], ['x_max', 'y_min'], ['x_max', 'y_max'], ['x_min', 'y_max'],
    [null, 'y_min'], ['x_max', null], [null, 'y_max'], ['x_min', null],
];
function handlePoint(rect, xe, ye) {
    const x = xe ? rect[xe] : (rect.x_min + rect.x_max) / 2;
    const y = ye ? rect[ye] : (rect.y_min + rect.y_max) / 2;
    return [x, y];
}
function normalizeRect(r) {
    if (r.x_min > r.x_max) [r.x_min, r.x_max] = [r.x_max, r.x_min];
    if (r.y_min > r.y_max) [r.y_min, r.y_max] = [r.y_max, r.y_min];
}

export class Radar {
    constructor(svg, callbacks) {
        this.svg = svg;
        this.cb = callbacks;
        this.W = 0;
        this.H = 0;
        this.range = { ...DEFAULT_RANGE };
        this.layout = { x: 0, y: 0, rot: 0, room: null };
        this.zones = null;
        this.pending = new Set();
        this.vis = { grid: true, labels: true, heights: false, detection: true, det: [true, true, true, true], stay: true, interference: true };
        this.occupied = [false, false, false, false];
        this.targets = [];
        this.history = {};
        this.rec = { slots: [], pad: 0 };
        this.recNodes = [];
        this.edit = null;
        this.arranging = false;

        this.dirty = new Set();
        this.frame = 0;
        this.targetNodes = new Map();
        this.trailNodes = new Map();
        this.pointers = new Map();
        this.drag = null;
        this.pinch = null;
        this.hoverFrame = 0;
        this.viewTimer = 0;

        const defs = el('defs', {}, svg);
        const hatch = el('pattern', { id: 'hatch-intf', width: 10, height: 10, patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, defs);
        el('rect', { class: 'hatch-bg', width: 10, height: 10 }, hatch);
        el('line', { class: 'hatch-line', x1: 0, y1: 0, x2: 0, y2: 10 }, hatch);
        this.layers = {};
        for (const name of LAYERS) this.layers[name] = el('g', { class: `layer-${name}` }, svg);

        new ResizeObserver(entries => {
            const box = entries[0].contentRect;
            if (box.width === this.W && box.height === this.H) return;
            this.W = box.width;
            this.H = box.height;
            this.invalidate('all');
        }).observe(svg);

        svg.addEventListener('pointerdown', e => this._down(e));
        svg.addEventListener('pointermove', e => this._move(e));
        svg.addEventListener('pointerup', e => this._up(e, false));
        svg.addEventListener('pointercancel', e => this._up(e, true));
        // Capture can end without a pointerup (capture released, element removed); treat it as a cancel
        svg.addEventListener('lostpointercapture', e => { if (this.pointers.has(e.pointerId)) this._up(e, true); });
        svg.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse' && !this.drag) this.cb.onPointer(null); });
        svg.addEventListener('wheel', e => this._wheel(e), { passive: false });
        svg.addEventListener('contextmenu', e => { if (this.drag) e.preventDefault(); });
    }

    // --- Inputs from the page ---------------------------------------------

    setRange(range) {
        if (!(range.xMax > range.xMin && range.yMax > range.yMin)) return;
        this.range = { ...range };
        this.invalidate('all');
    }

    setLayout(layout) {
        if (this.drag && ['sensor', 'rotate'].includes(this.drag.kind)) return;
        if (this.drag && this.drag.owner === 'room') return;
        this.layout = { x: layout.x || 0, y: layout.y || 0, rot: layout.rot || 0, room: layout.room ? { ...layout.room } : null };
        this.invalidate('all');
    }

    // `pending` holds "category:area" keys the switch hasn't confirmed yet; they're drawn dashed
    setZones(zones, pending) { this.zones = zones; this.pending = pending || new Set(); this.invalidate('zones'); }
    setVisibility(vis) { this.vis = { ...this.vis, ...vis, det: vis.det ? [...vis.det] : this.vis.det }; this.invalidate('grid', 'zones', 'edit'); }

    setOccupied(list) {
        if (list.every((v, i) => v === this.occupied[i])) return;
        this.occupied = [...list];
        this.invalidate('zones');
    }

    setTargets(targets, history) {
        this.targets = targets;
        this.history = history;
        this.invalidate('targets', 'trails');
    }

    setRecording(slots, pad) { this.rec = { slots, pad }; this.invalidate('recData'); }
    recordingGrew() { this.invalidate('recAppend'); }
    setRecordingPad(pad) { this.rec.pad = pad; this.invalidate('recording'); }

    setEdit(edit) {
        // The draft being dragged was saved or dropped; let go of it
        if (this.drag && this.drag.owner === 'draft' && edit !== this.edit) this._dropDrag();
        this.edit = edit;
        this._syncCapture();
        this.invalidate('zones', 'edit');
    }
    draftChanged() { this.invalidate('edit'); }

    setArranging(on) {
        // Layout mode ended mid-drag (Escape, Done): keep where the switch or wall got to
        if (!on && this.drag && (this.drag.kind === 'sensor' || this.drag.kind === 'rotate' || this.drag.owner === 'room')) {
            const d = this._dropDrag();
            this._finishDrag(d);
        }
        this.arranging = on;
        this._syncCapture();
        this.invalidate('all');
    }

    // Editing and arranging need every touch on the map; otherwise let the page scroll
    _syncCapture() {
        this.svg.classList.toggle('capture', !!this.edit || this.arranging);
    }

    // --- View helpers -----------------------------------------------------

    visibleRange() {
        const r = v => Math.round(v);
        if (!this._measure()) {
            const q = this.range;
            return { xMin: r(q.xMin), xMax: r(q.xMax), yMin: r(q.yMin), yMax: r(q.yMax) };
        }
        this._computeTransform();
        const hw = (this.W / 2 - PAD) / this.k, hh = (this.H / 2 - PAD) / this.k;
        return { xMin: r(this.cx - hw), xMax: r(this.cx + hw), yMin: r(this.cy - hh), yMax: r(this.cy + hh) };
    }

    // Box (in the world frame) around points given in the sensor frame plus the room
    _worldBox(sensorPts, buffer) {
        const xs = [], ys = [];
        for (const p of sensorPts) { const w = this.s2w(p[0], p[1]); xs.push(w[0]); ys.push(w[1]); }
        const room = this.layout.room;
        if (room) { xs.push(room.x_min, room.x_max); ys.push(room.y_min, room.y_max); }
        if (!xs.length) return null;
        return {
            xMin: Math.round(Math.min(...xs) - buffer), xMax: Math.round(Math.max(...xs) + buffer),
            yMin: Math.round(Math.min(...ys) - buffer), yMax: Math.round(Math.max(...ys) + buffer),
        };
    }

    // The default view, turned and moved with the switch
    fullRange() {
        const d = DEFAULT_RANGE;
        this._computeTransform();
        return this._worldBox([[d.xMin, d.yMin], [d.xMax, d.yMin], [d.xMax, d.yMax], [d.xMin, d.yMax]], 0);
    }

    // Every zone (shown or not) plus 1 m, like the old auto-scale; the full view if there are none
    zonesRange(zones) {
        this._computeTransform();
        const corners = [];
        for (const t of ZONE_TYPES) {
            for (const a of AREAS) {
                const z = zones[t.category][a];
                if (z && (z.x_min || z.x_max || z.y_min || z.y_max)) {
                    for (const [xe, ye] of CORNERS) corners.push([z[xe], z[ye]]);
                }
            }
        }
        if (!corners.length) return this.fullRange();
        return this._worldBox(corners, 100);
    }

    // World-frame box around sensor-frame points (used to size a new room outline)
    boxAround(sensorPts) {
        this._computeTransform();
        const xs = [], ys = [];
        for (const p of sensorPts) { const w = this.s2w(p[0], p[1]); xs.push(w[0]); ys.push(w[1]); }
        return { x_min: Math.min(...xs), x_max: Math.max(...xs), y_min: Math.min(...ys), y_max: Math.max(...ys) };
    }

    zoomBy(factor) {
        if (!this._measure()) return;
        this._computeTransform();
        this._zoomAt(this.W / 2, this.H / 2, factor);
        this._viewSettled();
    }

    // Make sure W/H are current; ResizeObserver doesn't report while hidden. False if there's no room to draw.
    _measure() {
        if (this.W <= 2 * PAD || this.H <= 2 * PAD) {
            const box = this.svg.getBoundingClientRect();
            this.W = box.width;
            this.H = box.height;
        }
        return this.W > 2 * PAD && this.H > 2 * PAD;
    }

    // --- Transforms -------------------------------------------------------

    _computeTransform() {
        const r = this.range;
        const W = Math.max(this.W, 2 * PAD + 1), H = Math.max(this.H, 2 * PAD + 1);
        this.k = Math.max(1e-4, Math.min((W - 2 * PAD) / (r.xMax - r.xMin), (H - 2 * PAD) / (r.yMax - r.yMin)));
        this.cx = (r.xMin + r.xMax) / 2;
        this.cy = (r.yMin + r.yMax) / 2;
        const t = (this.layout.rot || 0) * DEG;
        this.cs = Math.cos(t);
        this.sn = Math.sin(t);
    }

    w2p(wx, wy) { return [this.W / 2 + (wx - this.cx) * this.k, this.H / 2 - (wy - this.cy) * this.k]; }
    p2w(px, py) { return [this.cx + (px - this.W / 2) / this.k, this.cy - (py - this.H / 2) / this.k]; }
    s2w(x, y) { return [x * this.cs - y * this.sn + this.layout.x, x * this.sn + y * this.cs + this.layout.y]; }
    w2s(wx, wy) {
        const dx = wx - this.layout.x, dy = wy - this.layout.y;
        return [dx * this.cs + dy * this.sn, -dx * this.sn + dy * this.cs];
    }
    s2p(x, y) { const w = this.s2w(x, y); return this.w2p(w[0], w[1]); }
    p2s(px, py) { const w = this.p2w(px, py); return this.w2s(w[0], w[1]); }

    // --- Rendering --------------------------------------------------------

    invalidate(...layers) {
        for (const l of layers) {
            if (l === 'all') LAYERS.forEach(n => this.dirty.add(n));
            else this.dirty.add(l);
        }
        if (!this.frame) this.frame = requestAnimationFrame(() => this._render());
    }

    _render() {
        this.frame = 0;
        if (!this.W || !this.H) return;          // hidden; the ResizeObserver will bring us back
        this._computeTransform();
        const d = this.dirty;
        this.dirty = new Set();
        if (d.has('grid')) this._renderGrid();
        if (d.has('room')) this._renderRoom();
        if (d.has('zones')) this._renderZones();
        if (d.has('recData')) this._renderRecording();
        else if (d.has('recAppend')) this._appendRecording();
        if (d.has('recData') || d.has('recAppend') || d.has('recording')) this._placeRecording();
        if (d.has('trails')) this._renderTrails();
        if (d.has('targets')) this._renderTargets();
        if (d.has('edit')) this._renderEdit();
        if (d.has('sensor')) this._renderSensor();
    }

    _renderGrid() {
        const g = this.layers.grid;
        g.replaceChildren();
        const { W, H, k } = this;
        // The viewport in sensor coordinates, so the grid follows the switch's axes
        const c = [[0, 0], [W, 0], [0, H], [W, H]].map(p => this.p2s(p[0], p[1]));
        const x0 = Math.min(...c.map(p => p[0])), x1 = Math.max(...c.map(p => p[0]));
        const y0 = Math.min(...c.map(p => p[1])), y1 = Math.max(...c.map(p => p[1]));
        const step = [25, 50, 100, 200, 500, 1000, 2000].find(s => s * k >= 36) || 5000;
        let minor = '', axes = '';
        const seg = (a, b) => `M${r1(a[0])} ${r1(a[1])}L${r1(b[0])} ${r1(b[1])}`;
        for (let x = Math.ceil(x0 / step) * step; x <= x1; x += step) {
            const s = seg(this.s2p(x, y0), this.s2p(x, y1));
            if (x === 0) axes += s; else minor += s;
        }
        for (let y = Math.ceil(y0 / step) * step; y <= y1; y += step) {
            const s = seg(this.s2p(x0, y), this.s2p(x1, y));
            if (y === 0) axes += s; else minor += s;
        }
        el('path', { class: 'grid', d: minor }, g);
        el('path', { class: 'grid-axis', d: axes }, g);

        // cm ticks along the switch's wall (x) and straight out from it (y)
        const every = step * k >= 52 ? step : step * 2;
        const inView = p => p[0] > 4 && p[0] < W - 4 && p[1] > 4 && p[1] < H - 4;
        for (let x = Math.ceil(x0 / every) * every; x <= x1; x += every) {
            if (x === 0) continue;
            const p = this.s2p(x, -14 / k);
            if (inView(p)) el('text', { class: 'tick', x: r1(p[0]), y: r1(p[1]), 'text-anchor': 'middle', 'dominant-baseline': 'middle' }, g).textContent = num(x);
        }
        // Depth ticks sit at the map's edge rather than on the centre line, where zones and people are.
        // Lines of equal depth run along the switch's x axis; label each where it leaves the left
        // edge (switch facing up or down the screen) or the top edge (facing sideways).
        const dir = [this.cs, -this.sn];                    // sensor x axis on screen
        const leftEdge = Math.abs(dir[0]) >= Math.abs(dir[1]);
        for (let y = Math.ceil(y0 / every) * every; y <= y1; y += every) {
            const o = this.s2p(0, y);
            if (leftEdge) {
                const py = o[1] + (8 - o[0]) * dir[1] / dir[0];
                if (py > 12 && py < H - 34) el('text', { class: 'tick', x: 8, y: r1(py - 4) }, g).textContent = num(y);
            } else {
                const px = o[0] + (14 - o[1]) * dir[0] / dir[1];
                if (px > 20 && px < W - 20) el('text', { class: 'tick', x: r1(px + 4), y: 14, 'dominant-baseline': 'middle' }, g).textContent = num(y);
            }
        }

        if (!this.vis.grid) return;
        const o = this.s2p(0, 0);
        const at = (r, deg) => this.s2p(r * Math.sin(deg * DEG), r * Math.cos(deg * DEG));
        const arc = (r, a, b) => { const p = at(r, a), q = at(r, b), R = r1(r * k); return `M${r1(p[0])} ${r1(p[1])}A${R} ${R} 0 0 1 ${r1(q[0])} ${r1(q[1])}`; };
        const ext = `M${r1(o[0])} ${r1(o[1])}L${pts([at(FOV_RANGE, -FOV_EXTENDED)])}M${r1(o[0])} ${r1(o[1])}L${pts([at(FOV_RANGE, FOV_EXTENDED)])}` + arc(FOV_RANGE, -FOV_EXTENDED, FOV_EXTENDED);
        el('path', { class: 'fov-ext', d: ext }, g);
        const a = at(FOV_RANGE, -FOV_RATED);
        el('path', { class: 'fov', d: `M${r1(o[0])} ${r1(o[1])}L${r1(a[0])} ${r1(a[1])}` + arc(FOV_RANGE, -FOV_RATED, FOV_RATED).replace(/^M[^A]+/, '') + 'Z' }, g);
        let rings = '';
        for (let r = 100; r < FOV_RANGE; r += 100) rings += arc(r, -FOV_RATED, FOV_RATED);
        el('path', { class: 'ring', d: rings }, g);
        if (100 * k >= 22) {
            for (let r = 100; r <= FOV_RANGE; r += 100) {
                const p = at(r, FOV_RATED + 4);
                el('text', { class: 'ring-label', x: r1(p[0]), y: r1(p[1]), 'dominant-baseline': 'middle' }, g).textContent = `${r / 100} m`;
            }
        }
    }

    _renderRoom() {
        const g = this.layers.room;
        g.replaceChildren();
        const room = this.layout.room;
        if (!room) return;
        const corners = CORNERS.map(([xe, ye]) => this.w2p(room[xe], room[ye]));
        el('polygon', { class: 'room', points: pts(corners) }, g);
        if (!this.arranging) return;
        const top = this.w2p((room.x_min + room.x_max) / 2, room.y_max);
        const right = this.w2p(room.x_max, (room.y_min + room.y_max) / 2);
        el('text', { class: 'dim-label', x: r1(top[0]), y: r1(top[1] - 10), 'text-anchor': 'middle' }, g).textContent = metres(room.x_max - room.x_min);
        el('text', { class: 'dim-label', x: r1(right[0] + 10), y: r1(right[1]), 'dominant-baseline': 'middle' }, g).textContent = metres(room.y_max - room.y_min);
    }

    _zoneVisible(type, i) {
        if (type.group === 'detection') return this.vis.detection && this.vis.det[i];
        return type.group === 'stay' ? this.vis.stay : this.vis.interference;
    }

    _zoneLabel(g, rect, text, cls) {
        if (!this.vis.labels) return;
        const c = this.s2p((rect.x_min + rect.x_max) / 2, (rect.y_min + rect.y_max) / 2);
        const t = el('text', { class: `zone-label ${cls}`, x: r1(c[0]), y: r1(c[1]), 'text-anchor': 'middle', 'dominant-baseline': 'middle' }, g);
        t.textContent = text;
        if (this.vis.heights && rect.z_min != null) {
            t.setAttribute('y', r1(c[1] - 7));
            const z = el('tspan', { x: r1(c[0]), dy: 15, class: 'zone-z' }, t);
            z.textContent = `z ${num(rect.z_min)} to ${num(rect.z_max)}`;
        }
    }

    _renderZones() {
        const g = this.layers.zones;
        g.replaceChildren();
        if (!this.zones) return;
        const busy = !!this.edit || this.arranging;
        const items = [];
        ZONE_TYPES.forEach(type => AREAS.forEach((area, i) => {
            const z = this.zones[type.category][area];
            if (!z || !this._zoneVisible(type, i)) return;
            if (this.edit && this.edit.category === type.category && this.edit.area === area) return;
            items.push({ type, area, i, z, size: Math.abs((z.x_max - z.x_min) * (z.y_max - z.y_min)) });
        }));
        items.sort((a, b) => b.size - a.size);   // small zones on top so they stay clickable
        for (const { type, area, i, z } of items) {
            let cls = `zone ${type.cls}`;
            if (type.group === 'detection' && this.occupied[i]) cls += ' occupied';
            if (this.pending.has(`${type.category}:${area}`)) cls += ' pending';
            if (busy) cls += ' dim';
            el('polygon', {
                class: cls,
                points: pts(CORNERS.map(([xe, ye]) => this.s2p(z[xe], z[ye]))),
                fill: type.cls === 'intf' ? 'url(#hatch-intf)' : null,
                'data-zone': busy ? null : `${type.category}:${area}`,
            }, g);
            this._zoneLabel(g, z, type.name(i + 1), type.cls + (busy ? ' dim' : ''));
        }
    }

    // Recorded dots are drawn in sensor centimetres inside a transformed group, so panning,
    // zooming or moving the switch only changes one transform instead of rebuilding up to
    // 15,000 dots. Their stroke doesn't scale (CSS vector-effect), so dots keep their pixel size.
    _recPath(points) {
        let d = '';
        for (const p of points) d += `M${Math.round(p.x)} ${Math.round(p.y)}h0`;
        return d;
    }

    _renderRecording() {
        const g = this.layers.recording;
        g.replaceChildren();
        this.recNodes = this.rec.slots.map((slot, i) => {
            const group = el('g', { class: `rec rec-${i + 1}` }, g);
            const node = { dots: el('g', {}, group), chunks: [], count: 0, bounds: el('polygon', { class: 'rec-bounds' }, group) };
            for (let at = 0; at < slot.points.length; at += REC_CHUNK) {
                node.chunks.push(el('path', { class: 'rec-dots', d: this._recPath(slot.points.slice(at, at + REC_CHUNK)) }, node.dots));
            }
            node.count = slot.points.length;
            return node;
        });
    }

    // Only add what was recorded since the last frame; earlier chunks stay untouched
    _appendRecording() {
        const slots = this.rec.slots;
        if (this.recNodes.length !== slots.length || slots.some((s, i) => s.points.length < this.recNodes[i].count)) {
            return this._renderRecording();
        }
        slots.forEach((slot, i) => {
            const node = this.recNodes[i];
            while (node.count < slot.points.length) {
                const chunkIndex = Math.floor(node.count / REC_CHUNK);
                const end = Math.min(slot.points.length, (chunkIndex + 1) * REC_CHUNK);
                const d = this._recPath(slot.points.slice(node.count, end));
                let path = node.chunks[chunkIndex];
                if (!path) {
                    path = el('path', { class: 'rec-dots', d: '' }, node.dots);
                    node.chunks.push(path);
                }
                path.setAttribute('d', path.getAttribute('d') + d);
                node.count = end;
            }
        });
    }

    // Follow the view and the switch's pose, and redraw the padded outlines (cheap: 4 points each)
    _placeRecording() {
        const { k, cs, sn, W, H, cx, cy } = this;
        const { x, y } = this.layout;
        // sensor (x, y) → screen: the same maths as s2p, as an SVG matrix
        const m = [k * cs, -k * sn, -k * sn, -k * cs, W / 2 + (x - cx) * k, H / 2 + (cy - y) * k];
        const transform = `matrix(${m.map(v => +v.toFixed(5)).join(' ')})`;
        const pad = this.rec.pad;
        this.rec.slots.forEach((slot, i) => {
            const node = this.recNodes[i];
            if (!node) return;
            node.dots.setAttribute('transform', transform);
            const b = slot.bounds;
            if (!b) {
                node.bounds.removeAttribute('points');
                return;
            }
            const r = { x_min: b.x_min - pad, x_max: b.x_max + pad, y_min: b.y_min - pad, y_max: b.y_max + pad };
            node.bounds.setAttribute('points', pts(CORNERS.map(([xe, ye]) => this.s2p(r[xe], r[ye]))));
        });
    }

    _renderTrails() {
        const g = this.layers.trails;
        const seen = new Set();
        for (const [id, list] of Object.entries(this.history)) {
            if (list.length < 2) continue;
            seen.add(id);
            let line = this.trailNodes.get(id);
            if (!line) {
                line = el('polyline', { class: 'trail' }, g);
                this.trailNodes.set(id, line);
            }
            line.setAttribute('points', pts(list.map(p => this.s2p(p.x, p.y))));
        }
        for (const [id, line] of this.trailNodes) {
            if (!seen.has(id)) { line.remove(); this.trailNodes.delete(id); }
        }
    }

    _renderTargets() {
        const g = this.layers.targets;
        const seen = new Set();
        for (const t of this.targets) {
            const key = String(t.id);
            seen.add(key);
            let node = this.targetNodes.get(key);
            if (!node) {
                const group = el('g', { class: 'target' }, g);
                node = {
                    group,
                    dot: el('circle', { class: 'target-dot' }, group),
                    label: el('text', { class: 'target-label', 'dominant-baseline': 'middle' }, group),
                };
                node.id = el('tspan', { class: 'target-id' }, node.label);
                node.z = el('tspan', { class: 'target-z' }, node.label);
                this.targetNodes.set(key, node);
            }
            const p = this.s2p(t.x, t.y);
            // Same size rule as before: 8–40 px across, bigger the higher the target
            const r = Math.max(8, Math.min(40, 10 + t.z / 5)) / 2;
            node.dot.setAttribute('cx', r1(p[0]));
            node.dot.setAttribute('cy', r1(p[1]));
            node.dot.setAttribute('r', r1(r));
            node.label.setAttribute('x', r1(p[0] + r + 5));
            node.label.setAttribute('y', r1(p[1] - r - 2));
            if (node.id.textContent !== key) node.id.textContent = key;
            const z = ` z ${num(t.z)}`;
            if (node.z.textContent !== z) node.z.textContent = z;
        }
        for (const [key, node] of this.targetNodes) {
            if (!seen.has(key)) { node.group.remove(); this.targetNodes.delete(key); }
        }
    }

    _handles(g, rect, toPx, owner, avoid) {
        const hit = coarse.matches ? 22 : 11;
        for (const [xe, ye] of HANDLES) {
            const [x, y] = handlePoint(rect, xe, ye);
            const p = toPx(x, y);
            // A handle the switch sits on can't be grabbed (the switch is on top) and hides it
            if (avoid && Math.hypot(p[0] - avoid[0], p[1] - avoid[1]) < avoid[2]) continue;
            const edges = [xe, ye].filter(Boolean).join(',');
            el('circle', { class: 'handle', cx: r1(p[0]), cy: r1(p[1]), r: xe && ye ? 6 : 5 }, g);
            el('circle', { class: 'hit', cx: r1(p[0]), cy: r1(p[1]), r: hit, 'data-drag': 'handle', 'data-owner': owner, 'data-edges': edges }, g);
        }
    }

    _renderEdit() {
        const g = this.layers.edit;
        g.replaceChildren();
        if (this.edit && this.edit.draft) {
            const d = this.edit.draft;
            const type = ZONE_TYPES.find(t => t.category === this.edit.category);
            el('polygon', {
                class: `zone ${type.cls} draft`,
                points: pts(CORNERS.map(([xe, ye]) => this.s2p(d[xe], d[ye]))),
                fill: type.cls === 'intf' ? 'url(#hatch-intf)' : null,
                'data-drag': 'body', 'data-owner': 'draft',
            }, g);
            this._zoneLabel(g, d, type.name(this.edit.area.slice(4)), type.cls);
            this._handles(g, d, (x, y) => this.s2p(x, y), 'draft');
        }
        if (this.arranging && this.layout.room) {
            const [sx, sy] = this.w2p(this.layout.x, this.layout.y);
            this._handles(g, this.layout.room, (x, y) => this.w2p(x, y), 'room', [sx, sy, sensorHit()]);
        }
    }

    _renderSensor() {
        const g = this.layers.sensor;
        g.replaceChildren();
        const [px, py] = this.w2p(this.layout.x, this.layout.y);
        const rot = this.layout.rot || 0;
        // Facing direction on screen (world y points up, screen y points down)
        const fx = -Math.sin(rot * DEG), fy = -Math.cos(rot * DEG);
        const body = el('g', { class: 'sensor', transform: `translate(${r1(px)} ${r1(py)}) rotate(${r1(-rot)})` }, g);
        el('rect', { class: 'sensor-body', x: -13, y: -5, width: 26, height: 10, rx: 3 }, body);
        el('path', { class: 'sensor-nose', d: 'M-5 -5L0 -10L5 -5' }, body);
        el('text', { class: 'sensor-label', x: r1(px - fx * 20), y: r1(py - fy * 20), 'text-anchor': 'middle', 'dominant-baseline': 'middle' }, g).textContent = 'Switch';
        if (!this.arranging) return;
        const hx = px + fx * 58, hy = py + fy * 58;
        el('line', { class: 'rot-line', x1: r1(px), y1: r1(py), x2: r1(hx), y2: r1(hy) }, g);
        el('circle', { class: 'handle rot', cx: r1(hx), cy: r1(hy), r: 7 }, g);
        el('circle', { class: 'hit', cx: r1(hx), cy: r1(hy), r: coarse.matches ? 22 : 13, 'data-drag': 'rotate' }, g);
        el('circle', { class: 'hit sensor-hit', cx: r1(px), cy: r1(py), r: sensorHit(), 'data-drag': 'sensor' }, g);
    }

    // --- Pointer interaction ----------------------------------------------

    _local(e) {
        const rect = this.rect || this.svg.getBoundingClientRect();
        return [e.clientX - rect.left, e.clientY - rect.top];
    }

    _down(e) {
        if (e.pointerType === 'mouse' && e.button !== 0 && e.button !== 1) return;
        if (e.isPrimary) {
            // A new gesture: forget pointers whose up/cancel never arrived, so a lone
            // finger isn't mistaken for the second half of a pinch
            this.pointers.clear();
            this.pinch = null;
            // (no release: a mouse reuses its pointerId, and the late lostpointercapture would cancel the new drag)
            if (this.drag) this._finishDrag(this._dropDrag(false));
        }
        this.rect = this.svg.getBoundingClientRect();
        this._computeTransform();
        const p = this._local(e);
        this.pointers.set(e.pointerId, p);

        if (this.pointers.size === 2) {
            // Second finger: zoom and pan with both. Whatever the first one was dragging stays where it got to.
            const [a, b] = [...this.pointers.values()];
            const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
            if (this.drag) this._finishDrag(this._dropDrag(false));
            this.rect = this.svg.getBoundingClientRect();
            this.pinch = { dist: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, k: this.k, world: this.p2w(mid[0], mid[1]) };
            for (const id of this.pointers.keys()) this._capture(id);
            return;
        }
        if (this.pointers.size > 2) return;

        const t = e.target.closest ? e.target.closest('[data-drag],[data-zone]') : null;
        const kind = t && t.dataset.drag;
        if (kind && e.button === 0) {
            this.drag = {
                kind, id: e.pointerId, start: p, moved: false,
                owner: t.dataset.owner, edges: t.dataset.edges ? t.dataset.edges.split(',') : [],
                draft: this.edit && this.edit.draft ? { ...this.edit.draft } : null,
                layout: { x: this.layout.x, y: this.layout.y },
            };
            this._capture(e.pointerId);
            e.preventDefault();
            return;
        }
        const zone = t && t.dataset.zone ? t.dataset.zone : null;
        const canPan = e.pointerType === 'mouse' || this.svg.classList.contains('capture');
        this.drag = { kind: canPan ? 'pan' : 'tap', id: e.pointerId, start: p, last: p, moved: false, zone };
        if (canPan) {
            this._capture(e.pointerId);
            if (e.pointerType === 'mouse') e.preventDefault();
        }
    }

    _move(e) {
        const p = this._local(e);
        if (this.pointers.has(e.pointerId)) this.pointers.set(e.pointerId, p);

        if (this.pinch) {
            if (this.pointers.size < 2) return;
            const [a, b] = [...this.pointers.values()];
            const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
            const k = this._clampK(this.pinch.k * Math.hypot(a[0] - b[0], a[1] - b[1]) / this.pinch.dist);
            this._setView(this.pinch.world[0] - (mid[0] - this.W / 2) / k, this.pinch.world[1] + (mid[1] - this.H / 2) / k, k);
            e.preventDefault();
            return;
        }

        const d = this.drag;
        if (!d || d.id !== e.pointerId) {
            if (e.pointerType === 'mouse' && !this.drag) this._hover(p);
            return;
        }
        const dist = Math.hypot(p[0] - d.start[0], p[1] - d.start[1]);
        if (!d.moved && dist < (e.pointerType === 'mouse' ? 3 : 8)) return;
        d.moved = true;
        const shift = e.shiftKey;

        switch (d.kind) {
            case 'tap':
                this.drag = null;        // the browser is scrolling the page
                return;
            case 'pan': {
                this.svg.classList.add('panning');
                this._setView(this.cx - (p[0] - d.last[0]) / this.k, this.cy + (p[1] - d.last[1]) / this.k, this.k);
                d.last = p;
                this.cb.onView(this.visibleRange(), false);
                return;
            }
            case 'handle':
                if (d.owner === 'draft') {
                    if (!this.edit) { this._dropDrag(); return; }
                    const s = this.p2s(p[0], p[1]);
                    for (const edge of d.edges) this.edit.draft[edge] = Math.round(edge[0] === 'x' ? s[0] : s[1]);
                    this.invalidate('edit');
                    this.cb.onDraft(false);
                } else {
                    if (!this.layout.room) { this._dropDrag(); return; }
                    const w = this.p2w(p[0], p[1]);
                    for (const edge of d.edges) this.layout.room[edge] = Math.round(edge[0] === 'x' ? w[0] : w[1]);
                    this.invalidate('room', 'edit');
                    this.cb.onLayout(this.layout, false);
                }
                return;
            case 'body': {
                if (!this.edit) { this._dropDrag(); return; }
                const a = this.p2s(d.start[0], d.start[1]), b = this.p2s(p[0], p[1]);
                const dx = Math.round(b[0] - a[0]), dy = Math.round(b[1] - a[1]);
                Object.assign(this.edit.draft, {
                    x_min: d.draft.x_min + dx, x_max: d.draft.x_max + dx,
                    y_min: d.draft.y_min + dy, y_max: d.draft.y_max + dy,
                });
                this.invalidate('edit');
                this.cb.onDraft(false);
                return;
            }
            case 'sensor': {
                const a = this.p2w(d.start[0], d.start[1]), b = this.p2w(p[0], p[1]);
                let x = d.layout.x + b[0] - a[0], y = d.layout.y + b[1] - a[1];
                const room = this.layout.room;
                if (room && !shift) {
                    // Switches live on walls: snap onto one when close
                    for (const wx of [room.x_min, room.x_max]) if (Math.abs(x - wx) * this.k < WALL_SNAP_PX) x = wx;
                    for (const wy of [room.y_min, room.y_max]) if (Math.abs(y - wy) * this.k < WALL_SNAP_PX) y = wy;
                }
                this.layout.x = Math.round(x);
                this.layout.y = Math.round(y);
                this.invalidate('all');
                this.cb.onLayout(this.layout, false);
                return;
            }
            case 'rotate': {
                const w = this.p2w(p[0], p[1]);
                const angle = Math.atan2(-(w[0] - this.layout.x), w[1] - this.layout.y) / DEG;
                const snap = shift ? 1 : 15;
                this.layout.rot = ((Math.round(angle / snap) * snap) % 360 + 360) % 360;
                this.invalidate('all');
                this.cb.onLayout(this.layout, false);
                return;
            }
        }
    }

    _up(e, cancelled) {
        this.pointers.delete(e.pointerId);
        if (this.pinch) {
            if (this.pointers.size < 2) {
                this.pinch = null;
                this._viewSettled();
            }
            return;
        }
        const d = this.drag;
        if (!d || d.id !== e.pointerId) return;
        this._dropDrag(false);
        if (!d.moved) {
            if (!cancelled && d.zone && (d.kind === 'pan' || d.kind === 'tap')) {
                const [category, area] = d.zone.split(':');
                this.cb.onZoneClick(category, area);
            }
            return;
        }
        this._finishDrag(d);
    }

    _capture(id) {
        try { this.svg.setPointerCapture(id); } catch (err) { /* the pointer already went up */ }
    }

    // Stop tracking the current drag without committing it. Returns it.
    _dropDrag(release = true) {
        const d = this.drag;
        this.drag = null;
        this.rect = null;
        this.svg.classList.remove('panning');
        if (d && release) { try { this.svg.releasePointerCapture(d.id); } catch (err) { /* not captured */ } }
        return d;
    }

    // Commit what a drag changed: the view, the draft zone or the layout
    _finishDrag(d) {
        if (!d || !d.moved) return;
        switch (d.kind) {
            case 'pan':
                this.cb.onView(this.visibleRange(), true);
                break;
            case 'handle':
            case 'body':
                if (d.owner === 'draft') {
                    if (!this.edit) break;
                    normalizeRect(this.edit.draft);
                    this.invalidate('edit');
                    this.cb.onDraft(true);
                } else {
                    const room = this.layout.room;
                    if (!room) break;
                    normalizeRect(room);
                    if (room.x_max - room.x_min < 20) room.x_max = room.x_min + 20;
                    if (room.y_max - room.y_min < 20) room.y_max = room.y_min + 20;
                    this.invalidate('room', 'edit');
                    this.cb.onLayout(this.layout, true);
                }
                break;
            case 'sensor':
            case 'rotate':
                this.cb.onLayout(this.layout, true);
                break;
        }
    }

    _hover(p) {
        this.hoverAt = p;
        if (this.hoverFrame) return;
        this.hoverFrame = requestAnimationFrame(() => {
            this.hoverFrame = 0;
            this._computeTransform();
            this.cb.onPointer(this.p2s(this.hoverAt[0], this.hoverAt[1]));
        });
    }

    _wheel(e) {
        // On phones and narrow windows the page scrolls; zoom only with ctrl (trackpad pinch sends ctrl)
        if (!wide.matches && !e.ctrlKey && !e.metaKey) return;
        e.preventDefault();
        if (!this._measure()) return;
        this._computeTransform();
        const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
        const p = this._local(e);
        this._zoomAt(p[0], p[1], Math.exp(-e.deltaY * unit * 0.0015));
        clearTimeout(this.viewTimer);
        this.viewTimer = setTimeout(() => this._viewSettled(), 250);
    }

    _zoomAt(px, py, factor) {
        const w = this.p2w(px, py);
        const k = this._clampK(this.k * factor);   // clamp first, so the point under the cursor stays put
        this._setView(w[0] - (px - this.W / 2) / k, w[1] + (py - this.H / 2) / k, k);
        this.cb.onView(this.visibleRange(), false);
    }

    _viewSettled() {
        this.cb.onView(this.visibleRange(), true);
    }

    _clampK(k) {
        const span = Math.max(this.W - 2 * PAD, 1);
        return clamp(k, span / MAX_SPAN, span / MIN_SPAN);
    }

    _setView(cx, cy, k) {
        if (!this._measure()) return;
        const hw = (this.W / 2 - PAD) / k, hh = (this.H / 2 - PAD) / k;
        this.range = { xMin: cx - hw, xMax: cx + hw, yMin: cy - hh, yMax: cy + hh };
        this.k = k;
        this.cx = cx;
        this.cy = cy;
        this.invalidate('all');
    }

    // --- Image export -----------------------------------------------------

    // Copy the map with its computed colours inlined, so the image looks the
    // same outside the page's stylesheet.
    async toPNG(background) {
        const PROPS = ['fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-opacity', 'stroke-dasharray',
            'stroke-linecap', 'stroke-linejoin', 'opacity', 'font-family', 'font-size', 'font-weight',
            'paint-order', 'display', 'visibility', 'vector-effect'];
        const clone = this.svg.cloneNode(true);
        const src = [this.svg, ...this.svg.querySelectorAll('*')];
        const dst = [clone, ...clone.querySelectorAll('*')];
        const drop = [];
        src.forEach((node, i) => {
            if (node.classList.contains('hit')) drop.push(dst[i]);   // invisible grab areas
            const cs = getComputedStyle(node);
            dst[i].setAttribute('style', PROPS.map(p => `${p}:${cs.getPropertyValue(p)}`).join(';'));
            dst[i].removeAttribute('class');
        });
        drop.forEach(n => n.remove());
        clone.setAttribute('xmlns', SVG_NS);
        clone.setAttribute('width', this.W);
        clone.setAttribute('height', this.H);
        clone.setAttribute('viewBox', `0 0 ${this.W} ${this.H}`);
        clone.insertBefore(el('rect', { width: '100%', height: '100%', fill: background }), clone.firstChild);

        const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml' }));
        try {
            const img = new Image();
            await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = reject; img.src = url; });
            const scale = 2;
            const canvas = document.createElement('canvas');
            canvas.width = Math.round(this.W * scale);
            canvas.height = Math.round(this.H * scale);
            const ctx = canvas.getContext('2d');
            ctx.scale(scale, scale);
            ctx.drawImage(img, 0, 0);
            return await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
        } finally {
            URL.revokeObjectURL(url);
        }
    }
}
