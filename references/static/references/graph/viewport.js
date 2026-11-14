// The view of the graph: the whole graph fitted to the frame is the furthest one can
// zoom out, and the view never moves beyond it (#141), a selection included (#142): the
// bounds are stretched with the graph during a selection (#291); sizes stay constant on
// the screen (#185).

import { MARGIN } from "./scale.js";
import { isIdentity, stretchedBox } from "./stretch.js";

// Cytoscape's own lower limit, so that a smaller frame can fit the graph again.
const NO_MIN_ZOOM = 1e-50;
// Tolerances on the zoom (relative) and the pan (pixels) for rounding.
const SAME_ZOOM = 0.001;
const SAME_PAN = 1;

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

// showAllButton shows the whole graph again (#196); it is disabled, rather than hidden,
// while the whole graph is shown: it stays in view and in place. stretch: what
// makeStretch returns. Returns what a selection needs to move the view (#142): the zoom
// of the whole graph, a view brought within the bounds, a hold on the bounds while it
// animates, and a callback when the whole graph is shown again; and whether the whole
// graph is shown (#175).
export function bindViewport(cy, container, showAllButton, stretch) {
    // The view showing the whole graph, and its visible area in graph coordinates: the
    // area the view stays within.
    let whole = null;
    // While a selection animates the view and the stretch together, the bounds wait.
    let held = false;
    const showAllListeners = [];
    const bounds = () => stretchedBox(stretch.current(), whole.extent);
    const showsAll = () => {
        const pan = cy.pan();
        return (
            isIdentity(stretch.current()) &&
            Math.abs(cy.zoom() / whole.zoom - 1) < SAME_ZOOM &&
            Math.abs(pan.x - whole.pan.x) < SAME_PAN &&
            Math.abs(pan.y - whole.pan.y) < SAME_PAN
        );
    };
    const updateButton = () => {
        showAllButton.disabled = showsAll();
    };
    const showAll = () => {
        whole = null;
        for (const listener of showAllListeners) {
            listener();
        }
        cy.minZoom(NO_MIN_ZOOM);
        // fit measures the nodes at their size for the current zoom (#185): once more
        // with their size for the new zoom, so that the result is the same from any view.
        cy.fit(undefined, MARGIN / 2);
        cy.style().update();
        cy.fit(undefined, MARGIN / 2);
        whole = { zoom: cy.zoom(), pan: { ...cy.pan() }, extent: cy.extent() };
        cy.minZoom(whole.zoom);
        updateButton();
    };
    // The view of this zoom and pan, brought within the bounds of the graph stretched as
    // given: not below the zoom of the whole graph, around the same centre, then moved as
    // little as needed.
    const within = (zoom, pan, stretchAimed) => {
        const kept = Math.max(zoom, whole.zoom);
        const centre = {
            x: (cy.width() / 2 - pan.x) / zoom,
            y: (cy.height() / 2 - pan.y) / zoom,
        };
        const view = {
            x1: centre.x - cy.width() / 2 / kept,
            x2: centre.x + cy.width() / 2 / kept,
            y1: centre.y - cy.height() / 2 / kept,
            y2: centre.y + cy.height() / 2 / kept,
        };
        const aimed = stretchedBox(stretchAimed, whole.extent);
        const dx = shiftInto(view.x1, view.x2, aimed.x1, aimed.x2);
        const dy = shiftInto(view.y1, view.y2, aimed.y1, aimed.y2);
        return { zoom: kept, pan: { x: -(view.x1 + dx) * kept, y: -(view.y1 + dy) * kept } };
    };
    showAll();
    cy.on("viewport", () => {
        if (whole) {
            if (!held) {
                keepWithin(cy, bounds());
            }
            updateButton();
        }
    });
    // Held during an animation that ends within the bounds; checked again at its end.
    const hold = (on) => {
        held = on;
        if (!on && whole) {
            keepWithin(cy, bounds());
            updateButton();
        }
    };
    showAllButton.addEventListener("click", showAll);
    // The container may change size after initialization (page layout, window resize).
    new ResizeObserver(() => {
        cy.resize();
        showAll();
    }).observe(container);
    keepScreenSize(cy);
    return {
        wholeZoom: () => whole.zoom,
        showsAll,
        within,
        hold,
        onShowAll: (listener) => showAllListeners.push(listener),
    };
}
