// On selection, the view moves to show the publication and its neighbours in the part of
// the frame the information card leaves free (#142). It never zooms in, only out when
// they do not fit. The bounds of the view (#141) widen just enough for that view: in the
// view of the whole graph, a neighbour under the card could not be shown otherwise.

// Room kept around the nodes, in pixels: the largest node's radius and a margin.
const PADDING = 28;
// Between the card and the free area, in pixels.
const CARD_GAP = 12;
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

// The largest zoom, at most the current one, that fits the box in the area; not positive
// when the area is too small. Nodes on a line have a box without width or height: one
// unit avoids dividing by zero.
function fittingZoom(cy, box, area) {
    const zoomX = (area.x2 - area.x1 - 2 * PADDING) / Math.max(box.x2 - box.x1, 1);
    const zoomY = (area.y2 - area.y1 - 2 * PADDING) / Math.max(box.y2 - box.y1, 1);
    return Math.min(cy.zoom(), zoomX, zoomY);
}

function isShown(cy, box, area) {
    const zoom = cy.zoom();
    const pan = cy.pan();
    return (
        box.x1 * zoom + pan.x >= area.x1 + PADDING &&
        box.x2 * zoom + pan.x <= area.x2 - PADDING &&
        box.y1 * zoom + pan.y >= area.y1 + PADDING &&
        box.y2 * zoom + pan.y <= area.y2 - PADDING
    );
}

export function showInFreeArea(cy, nodes, card, allowView) {
    const box = centres(nodes);
    const areas = freeAreas(cy, card);
    if (areas.some((area) => isShown(cy, box, area))) {
        return;
    }
    // The area where the nodes appear largest, the right one when equal.
    const area = areas.reduce((best, other) =>
        fittingZoom(cy, box, other) > fittingZoom(cy, box, best) ? other : best,
    );
    const zoom = fittingZoom(cy, box, area);
    if (zoom <= 0) {
        return;
    }
    // The centre of the nodes on the centre of the area.
    const pan = {
        x: (area.x1 + area.x2) / 2 - ((box.x1 + box.x2) / 2) * zoom,
        y: (area.y1 + area.y2) / 2 - ((box.y1 + box.y2) / 2) * zoom,
    };
    allowView(zoom, pan);
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    cy.stop();
    cy.animate({ zoom, pan }, { duration: still ? 0 : DURATION, easing: "ease-in-out-cubic" });
}
