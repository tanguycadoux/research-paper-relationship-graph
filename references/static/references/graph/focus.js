// On selection, the view shows the publication and its neighbours over the whole frame,
// in width and in height (#142, #291): the zoom fills one axis, and the graph is
// stretched along the other (stretch.js) until it fills it too. On deselection, the view
// and the positions go back to what they were before the selection. The view stays
// within the bounds of #141, stretched with the graph.

import { IDENTITY, isIdentity } from "./stretch.js";

// Room kept around the nodes, in pixels: the largest node's radius and a margin.
const PADDING = 28;
// The zoom stays under this many times the zoom of the whole graph: nodes and edges are
// drawn at a constant size on the screen (#185), the zoom only spreads them.
const MAX_ZOOM_RATIO = 4;
// An axis is stretched at most this many times: the graph stays recognisable.
const MAX_STRETCH = 4;
// Below this span (in pixels of the layout), an axis is not stretched: neighbours of the
// same year have nothing to spread.
const MIN_SPAN = 1;
// A publication and a single neighbour would end in opposite corners of the frame: they
// are stretched to this part of it only.
const PAIR_FILL = 0.6;
const DURATION = 300;

// Layout coordinates of the node centres: their size depends on the zoom (#185), and the
// stretch of a previous selection does not count.
function centres(nodes, stretch) {
    const points = nodes.map((node) => stretch.layoutPosition(node));
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    return { x1: Math.min(...xs), x2: Math.max(...xs), y1: Math.min(...ys), y2: Math.max(...ys) };
}

// The scale, along each axis, that fits the box in the given part of the frame. A box
// without width or height (nodes on a line) counts as one unit wide: no division by zero.
function fittingScales(cy, box, fill) {
    return {
        x: (fill * (cy.width() - 2 * PADDING)) / Math.max(box.x2 - box.x1, 1),
        y: (fill * (cy.height() - 2 * PADDING)) / Math.max(box.y2 - box.y1, 1),
    };
}

// The zoom and the stretch that show the box over the frame: the zoom fits the tighter
// axis, up to limit; then each axis is stretched to fill the frame too, up to
// MAX_STRETCH. A pair of nodes fills part of the frame only.
function aimFor(cy, box, limit, nodeCount) {
    const whole = fittingScales(cy, box, 1);
    const zoom = Math.min(limit, whole.x, whole.y);
    const aimed = fittingScales(cy, box, nodeCount > 2 ? 1 : PAIR_FILL);
    const spread = (scale, span) =>
        span >= MIN_SPAN ? Math.min(MAX_STRETCH, Math.max(1, scale / zoom)) : 1;
    const centre = { x: (box.x1 + box.x2) / 2, y: (box.y1 + box.y2) / 2 };
    return {
        zoom,
        stretch: {
            sx: spread(aimed.x, box.x2 - box.x1),
            sy: spread(aimed.y, box.y2 - box.y1),
            cx: centre.x,
            cy: centre.y,
        },
        // The centre of the box does not move with the stretch: on the centre of the frame.
        pan: { x: cy.width() / 2 - centre.x * zoom, y: cy.height() / 2 - centre.y * zoom },
    };
}

const lerp = (a, b, t) => a + (b - a) * t;
// Sizes change by the same factor at each moment: a zoom looks even, not faster at first.
const geometric = (a, b, t) => a * (b / a) ** t;
const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

// The part of the layout (unstretched coordinates: x is still a date) that a view shows
// over the frame: {x1, x2, y1, y2}.
function windowOf(cy, state) {
    const { zoom, pan, stretch } = state;
    const layoutX = (u) => stretch.cx + ((u - pan.x) / zoom - stretch.cx) / stretch.sx;
    const layoutY = (v) => stretch.cy + ((v - pan.y) / zoom - stretch.cy) / stretch.sy;
    return { x1: layoutX(0), x2: layoutX(cy.width()), y1: layoutY(0), y2: layoutY(cy.height()) };
}

// Where a window of the layout appears on the screen in a view: {x1, x2, y1, y2} in pixels.
function onScreen(cy, state, area) {
    const { zoom, pan, stretch } = state;
    const screenX = (x) => (stretch.cx + (x - stretch.cx) * stretch.sx) * zoom + pan.x;
    const screenY = (y) => (stretch.cy + (y - stretch.cy) * stretch.sy) * zoom + pan.y;
    return { x1: screenX(area.x1), x2: screenX(area.x2), y1: screenY(area.y1), y2: screenY(area.y2) };
}

// One axis of a rectangle between two others: its centre linearly, its size
// geometrically. A geometric mean stays under the linear one, so each edge stays between
// where it starts and where it ends: nothing overshoots.
function between(a1, a2, b1, b2, e) {
    const centre = lerp((a1 + a2) / 2, (b1 + b2) / 2, e);
    const size = geometric(a2 - a1, b2 - b1, e);
    return [centre - size / 2, centre + size / 2];
}

// The view, between two others, at eased progress e (#291). What moves is the smaller of
// the two windows of the layout (the one shown at the end when zooming in, at the start
// when zooming out): its rectangle on the screen goes from where it is to the whole frame,
// or back. Both axes grow by the same factor at each moment, in log, so they close in
// together, and the selection never leaves the frame on the way. The zoom, geometric too,
// sets the size of the nodes on the screen (#185); the stretch makes up the rest on each
// axis, around the centre of the window.
function viewBetween(cy, from, to, e) {
    const a = windowOf(cy, from);
    const b = windowOf(cy, to);
    const zoomingIn = (b.x2 - b.x1) * (b.y2 - b.y1) <= (a.x2 - a.x1) * (a.y2 - a.y1);
    const area = zoomingIn ? b : a;
    const frameRect = { x1: 0, x2: cy.width(), y1: 0, y2: cy.height() };
    const start = zoomingIn ? onScreen(cy, from, area) : frameRect;
    const end = zoomingIn ? frameRect : onScreen(cy, to, area);
    const [left, right] = between(start.x1, start.x2, end.x1, end.x2, e);
    const [top, bottom] = between(start.y1, start.y2, end.y1, end.y2, e);
    // Pixels per unit of the layout on each axis, and the window that it gives.
    const kx = (right - left) / (area.x2 - area.x1);
    const ky = (bottom - top) / (area.y2 - area.y1);
    const x1 = area.x1 - left / kx;
    const y1 = area.y1 - top / ky;
    const centre = { x: x1 + cy.width() / kx / 2, y: y1 + cy.height() / ky / 2 };
    const zoom = geometric(from.zoom, to.zoom, e);
    return {
        zoom,
        stretch: { sx: kx / zoom, sy: ky / zoom, cx: centre.x, cy: centre.y },
        // The centre of the stretch does not move: on the centre of the frame.
        pan: { x: cy.width() / 2 - centre.x * zoom, y: cy.height() / 2 - centre.y * zoom },
    };
}

// viewport: what bindViewport returns; stretch: what makeStretch returns.
export function bindFocus(cy, viewport, stretch) {
    // The view and the stretch from before the selection, kept until back to them.
    let before = null;
    let frame = null;
    const stop = () => {
        if (frame !== null) {
            cancelAnimationFrame(frame);
            frame = null;
            viewport.hold(false);
        }
    };
    // One loop moves the view and the stretch together (viewBetween), frame by frame; it
    // ends on the target exactly. A new move starts from where the view is.
    const moveTo = (target, complete) => {
        stop();
        cy.stop();
        const from = { stretch: stretch.current(), zoom: cy.zoom(), pan: { ...cy.pan() } };
        // On a large graph, sizes do not follow the zoom during a motion (viewport.js): an
        // animation would swell the nodes up to MAX_ZOOM_RATIO times, then shrink them. The
        // view goes there at once, as when motion is reduced.
        const still =
            !viewport.live || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const start = performance.now();
        viewport.hold(true);
        const step = (now) => {
            const t = still ? 1 : Math.min(1, (now - start) / DURATION);
            const view = t < 1 ? viewBetween(cy, from, target, easeInOutCubic(t)) : target;
            stretch.apply(view.stretch);
            cy.viewport({ zoom: view.zoom, pan: view.pan });
            if (t < 1) {
                frame = requestAnimationFrame(step);
                return;
            }
            frame = null;
            viewport.hold(false);
            complete?.();
        };
        if (still) {
            step(start);
        } else {
            frame = requestAnimationFrame(step);
        }
    };
    // Zooming or panning by hand stops a move where it is.
    cy.on("scrollzoom pinchzoom dragpan", stop);
    const show = (nodes) => {
        const box = centres(nodes, stretch);
        const limit = viewport.wholeZoom() * MAX_ZOOM_RATIO;
        const aim = aimFor(cy, box, limit, nodes.length);
        before ??= { zoom: cy.zoom(), pan: { ...cy.pan() }, stretch: stretch.current() };
        moveTo({ ...viewport.within(aim.zoom, aim.pan, aim.stretch), stretch: aim.stretch });
    };
    // A new selection during the way back stops it: the view to go back to stays the same.
    const release = () => {
        if (before) {
            moveTo(before, () => {
                before = null;
            });
        }
    };
    // The button shows the whole graph again with the same motion; a resized frame
    // (or no stretch to undo) shows it at once.
    viewport.onShowAllRequest(() => {
        if (isIdentity(stretch.current()) && frame === null) {
            return false;
        }
        before = null;
        moveTo({ ...viewport.wholeView(), stretch: IDENTITY });
        return true;
    });
    viewport.onShowAll(() => {
        stop();
        before = null;
        stretch.apply(IDENTITY);
    });
    return { show, release };
}
