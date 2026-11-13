// On selection, the view zooms on the publication and its neighbours, in the whole frame:
// the information card is beside the graph, it hides nothing (#142, #291). On
// deselection, it goes back to the view from before the selection. The view stays within
// the bounds of #141: the view aimed at is brought within them before moving.

// Room kept around the nodes, in pixels: the largest node's radius and a margin.
const PADDING = 28;
// A publication with a single close neighbour would otherwise fill the frame.
const MAX_ZOOM_RATIO = 4;
const DURATION = 300;

// Graph coordinates of the node centres: their size depends on the zoom (#185).
function centres(nodes) {
    const xs = nodes.map((n) => n.position("x"));
    const ys = nodes.map((n) => n.position("y"));
    return { x1: Math.min(...xs), x2: Math.max(...xs), y1: Math.min(...ys), y2: Math.max(...ys) };
}

// The largest zoom, up to maxZoom, that fits the box in the frame. Nodes on a line have a
// box without width or height: one unit avoids dividing by zero.
function fittingZoom(cy, box, maxZoom) {
    const zoomX = (cy.width() - 2 * PADDING) / Math.max(box.x2 - box.x1, 1);
    const zoomY = (cy.height() - 2 * PADDING) / Math.max(box.y2 - box.y1, 1);
    return Math.min(maxZoom, zoomX, zoomY);
}

function animateTo(cy, view, complete) {
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    cy.stop();
    cy.animate(view, { duration: still ? 0 : DURATION, easing: "ease-in-out-cubic", complete });
}

// viewport: what bindViewport returns.
export function bindFocus(cy, viewport) {
    // The view from before the selection, kept until the view is back to it.
    let before = null;
    const show = (nodes) => {
        const box = centres(nodes);
        const zoom = fittingZoom(cy, box, viewport.wholeZoom() * MAX_ZOOM_RATIO);
        // The centre of the nodes on the centre of the frame.
        const pan = {
            x: cy.width() / 2 - ((box.x1 + box.x2) / 2) * zoom,
            y: cy.height() / 2 - ((box.y1 + box.y2) / 2) * zoom,
        };
        before ??= { zoom: cy.zoom(), pan: { ...cy.pan() } };
        animateTo(cy, viewport.within(zoom, pan));
    };
    // A new selection during the way back stops it: the view to go back to stays the same.
    const release = () => {
        if (before) {
            animateTo(cy, before, () => {
                before = null;
            });
        }
    };
    return { show, release };
}
