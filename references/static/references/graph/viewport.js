// The view of the graph: the whole graph fitted to the frame is the furthest one can
// zoom out, and the view never moves beyond it (#141); sizes stay constant on the
// screen (#185).

import { MARGIN } from "./scale.js";

// Cytoscape's own lower limit, so that a smaller frame can fit the graph again.
const NO_MIN_ZOOM = 1e-50;

// How far to move a view, along one axis, to bring it within the bounds: a view larger
// than the bounds is centred on them.
function shiftInto(viewStart, viewEnd, boundStart, boundEnd) {
    if (viewEnd - viewStart >= boundEnd - boundStart) {
        return (boundStart + boundEnd - viewStart - viewEnd) / 2;
    }
    return Math.max(boundStart - viewStart, 0) + Math.min(boundEnd - viewEnd, 0);
}

// Moving the view by dx in the graph moves the rendered graph by -dx * zoom.
function keepWithin(cy, bounds) {
    const view = cy.extent();
    const dx = shiftInto(view.x1, view.x2, bounds.x1, bounds.x2);
    const dy = shiftInto(view.y1, view.y2, bounds.y1, bounds.y2);
    const zoom = cy.zoom();
    // Under half a pixel the view is within: no endless corrections from rounding.
    if (Math.abs(dx * zoom) >= 0.5 || Math.abs(dy * zoom) >= 0.5) {
        cy.panBy({ x: -dx * zoom, y: -dy * zoom });
    }
}

// Sizes in the style are divided by the zoom (#185): they are evaluated again when the
// zoom changes, at most once per frame, so that zooming stays smooth on large graphs.
function keepScreenSize(cy) {
    let zoom = cy.zoom();
    let pending = false;
    cy.style().update();
    cy.on("viewport", () => {
        if (pending || cy.zoom() === zoom) {
            return;
        }
        pending = true;
        requestAnimationFrame(() => {
            pending = false;
            zoom = cy.zoom();
            cy.style().update();
        });
    });
}

// Returns the function that shows the whole graph again.
export function bindViewport(cy, container) {
    // The visible area, in graph coordinates, once the whole graph is fitted.
    let bounds = null;
    const showAll = () => {
        bounds = null;
        cy.minZoom(NO_MIN_ZOOM);
        // fit measures the nodes at their size for the current zoom (#185): once more
        // with their size for the new zoom, so that the result is the same from any view.
        cy.fit(undefined, MARGIN / 2);
        cy.style().update();
        cy.fit(undefined, MARGIN / 2);
        cy.minZoom(cy.zoom());
        bounds = cy.extent();
    };
    showAll();
    cy.on("viewport", () => {
        if (bounds) {
            keepWithin(cy, bounds);
        }
    });
    // The container may change size after initialization (page layout, window resize).
    new ResizeObserver(() => {
        cy.resize();
        showAll();
    }).observe(container);
    keepScreenSize(cy);
    return showAll;
}
