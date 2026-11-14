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
const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

// The centre of an identity stretch does not matter: it takes the other one, so that the
// stretch grows from, or shrinks to, the centre of the selection.
function lerpStretch(from, to, t) {
    if (isIdentity(from)) {
        from = { ...from, cx: to.cx, cy: to.cy };
    } else if (isIdentity(to)) {
        to = { ...to, cx: from.cx, cy: from.cy };
    }
    return {
        sx: lerp(from.sx, to.sx, t),
        sy: lerp(from.sy, to.sy, t),
        cx: lerp(from.cx, to.cx, t),
        cy: lerp(from.cy, to.cy, t),
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
    // The stretch and the view move together, frame by frame: the view is interpolated
    // around the graph point at the centre of the frame, which keeps the motion straight.
    const moveTo = (target, complete) => {
        stop();
        cy.stop();
        const from = { stretch: stretch.current(), zoom: cy.zoom(), pan: { ...cy.pan() } };
        const centreOf = (zoom, pan) => ({
            x: (cy.width() / 2 - pan.x) / zoom,
            y: (cy.height() / 2 - pan.y) / zoom,
        });
        const fromCentre = centreOf(from.zoom, from.pan);
        const toCentre = centreOf(target.zoom, target.pan);
        const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const start = performance.now();
        viewport.hold(true);
        const step = (now) => {
            const t = still ? 1 : Math.min(1, (now - start) / DURATION);
            const eased = easeInOutCubic(t);
            const zoom = lerp(from.zoom, target.zoom, eased);
            const centre = {
                x: lerp(fromCentre.x, toCentre.x, eased),
                y: lerp(fromCentre.y, toCentre.y, eased),
            };
            stretch.apply(lerpStretch(from.stretch, target.stretch, eased));
            cy.viewport({
                zoom,
                pan: { x: cy.width() / 2 - centre.x * zoom, y: cy.height() / 2 - centre.y * zoom },
            });
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
    // Showing the whole graph again (button, resized frame) ends the stretch at once.
    viewport.onShowAll(() => {
        stop();
        before = null;
        stretch.apply(IDENTITY);
    });
    return { show, release };
}
