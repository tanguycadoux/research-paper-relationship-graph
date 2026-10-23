// On selection, the view zooms on the publication and its neighbours, in the part of the
// frame the information card leaves free (#142); on deselection, it goes back to the
// view from before the selection. The bounds of the view (#141) widen for the time of
// the selection: in the view of the whole graph, a neighbour under the card could not be
// shown otherwise.

// Room kept around the nodes, in pixels: the largest node's radius and a margin.
const PADDING = 28;
// Between the card and the free area, in pixels.
const CARD_GAP = 12;
// A publication with a single close neighbour would otherwise fill the frame.
const MAX_ZOOM_RATIO = 4;
const DURATION = 300;

// The rectangles of the frame left free by the card, in pixels from the top left of the
// graph: on its right, and above it (the card is in the bottom left corner).
function freeAreas(cy, card) {
    const frame = cy.container().getBoundingClientRect();
    const box = card.getBoundingClientRect();
    const width = cy.width();
    const height = cy.height();
    return [
        { x1: box.right - frame.left + CARD_GAP, y1: 0, x2: width, y2: height },
        { x1: 0, y1: 0, x2: width, y2: box.top - frame.top - CARD_GAP },
    ];
}

// Graph coordinates of the node centres: their size depends on the zoom (#185).
function centres(nodes) {
    const xs = nodes.map((n) => n.position("x"));
    const ys = nodes.map((n) => n.position("y"));
    return { x1: Math.min(...xs), x2: Math.max(...xs), y1: Math.min(...ys), y2: Math.max(...ys) };
}

// The largest zoom, up to maxZoom, that fits the box in the area; not positive when the
// area is too small. Nodes on a line have a box without width or height: one unit
// avoids dividing by zero.
function fittingZoom(box, area, maxZoom) {
    const zoomX = (area.x2 - area.x1 - 2 * PADDING) / Math.max(box.x2 - box.x1, 1);
    const zoomY = (area.y2 - area.y1 - 2 * PADDING) / Math.max(box.y2 - box.y1, 1);
    return Math.min(maxZoom, zoomX, zoomY);
}

function animateTo(cy, view, complete) {
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    cy.stop();
    cy.animate(view, { duration: still ? 0 : DURATION, easing: "ease-in-out-cubic", complete });
}

// viewport: what bindViewport returns.
export function bindFocus(cy, card, viewport) {
    // The view from before the selection, kept until the view is back to it.
    let before = null;
    const show = (nodes) => {
        const box = centres(nodes);
        const maxZoom = viewport.wholeZoom() * MAX_ZOOM_RATIO;
        // The area where the nodes appear largest, the right one when equal.
        const area = freeAreas(cy, card).reduce((best, other) =>
            fittingZoom(box, other, maxZoom) > fittingZoom(box, best, maxZoom) ? other : best,
        );
        const zoom = fittingZoom(box, area, maxZoom);
        if (zoom <= 0) {
            return;
        }
        before ??= { zoom: cy.zoom(), pan: { ...cy.pan() } };
        // The centre of the nodes on the centre of the area.
        const pan = {
            x: (area.x1 + area.x2) / 2 - ((box.x1 + box.x2) / 2) * zoom,
            y: (area.y1 + area.y2) / 2 - ((box.y1 + box.y2) / 2) * zoom,
        };
        viewport.allowView(zoom, pan);
        animateTo(cy, { zoom, pan });
    };
    // A new selection during the way back stops it: the view to go back to stays the same.
    const release = () => {
        if (before) {
            animateTo(cy, before, () => {
                before = null;
                viewport.restoreBounds();
            });
        }
    };
    return { show, release };
}
