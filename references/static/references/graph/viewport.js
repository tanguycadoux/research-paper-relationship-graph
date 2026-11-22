// The view of the graph: the whole graph fitted to the frame is the furthest one can
// zoom out, and the view never moves beyond it (#141), a selection included (#142): the
// bounds are stretched with the graph during a selection (#291); sizes stay constant on
// the screen (#185).

import { MARGIN } from "./scale.js";
import { keepScreenSize } from "./screen_size.js";
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

// Evaluating the style again costs Cytoscape about 0.03 ms per element (#202): 135 ms
// for the 4 300 elements of a graph of 1 800 publications, three times the drawing
// itself. Up to this many elements (about 20 ms), sizes follow the zoom at each frame.
export const LIVE_SIZES_MAX_ELEMENTS = 600;

// Options of Cytoscape for a graph of this many elements. On a large one, the drawing
// itself is slow (45 ms for 4 300 elements, 100 ms for 7 000): while the view is zoomed or
// dragged by hand, the edges are hidden and only the nodes are drawn, at each frame
// (#476), so that what a drag brings into the frame shows at once. Moving a picture of the
// graph instead (textureOnViewport, #320) was as fluid up to 4 300 elements, but showed
// nothing of what was out of the frame when the gesture began, until it ended.
export function rendererOptions(elementCount) {
    return { hideEdgesOnViewport: elementCount > LIVE_SIZES_MAX_ELEMENTS };
}

// The view of this zoom and pan, brought within the bounds of the graph stretched as
// given: not below the zoom of the whole graph, around the same centre, then moved as
// little as needed. whole: the view of the whole graph (makeWholeView).
function viewWithin(cy, whole, zoom, pan, stretchAimed) {
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
}

// The view of the whole graph (#141): measured again by measure(), after forget(); the view
// stays within its visible area, stretched with the graph (#291). stretch: what
// makeStretch returns; sizes: what keepScreenSize returns.
function makeWholeView(cy, stretch, sizes) {
    // The view showing the whole graph, and its visible area in graph coordinates.
    let whole = null;
    const measure = () => {
        cy.minZoom(NO_MIN_ZOOM);
        // fit measures the nodes at their size for the current zoom (#185): once more
        // with their size for the new zoom, so that the result is the same from any view.
        cy.fit(undefined, MARGIN / 2);
        sizes.updateNow();
        cy.fit(undefined, MARGIN / 2);
        // The sizes are those of this zoom, give or take the few pixels of the second fit:
        // a large graph does not evaluate them all again (#326).
        sizes.settled();
        whole = { zoom: cy.zoom(), pan: { ...cy.pan() }, extent: cy.extent() };
        cy.minZoom(whole.zoom);
    };
    const showsAll = () => {
        const pan = cy.pan();
        return (
            isIdentity(stretch.current()) &&
            Math.abs(cy.zoom() / whole.zoom - 1) < SAME_ZOOM &&
            Math.abs(pan.x - whole.pan.x) < SAME_PAN &&
            Math.abs(pan.y - whole.pan.y) < SAME_PAN
        );
    };
    const within = (zoom, pan, stretchAimed) => viewWithin(cy, whole, zoom, pan, stretchAimed);
    return {
        measured: () => whole !== null,
        forget: () => {
            whole = null;
        },
        measure,
        showsAll,
        within,
        keepWithin: () => keepWithin(cy, stretchedBox(stretch.current(), whole.extent)),
        zoom: () => whole.zoom,
        // Unstretched: where the button goes back to.
        view: () => ({ zoom: whole.zoom, pan: { ...whole.pan } }),
    };
}

// The button shows the whole graph again (#196); it is disabled, rather than hidden,
// while the whole graph is shown: it stays in view and in place. A move in progress may
// take over the button (onRequest), to show the whole graph with a motion.
function bindShowAllButton(button, showAll) {
    let request = null;
    button.addEventListener("click", () => {
        if (!request?.()) {
            showAll();
        }
    });
    return {
        update: (showsAll) => {
            button.disabled = showsAll;
        },
        onRequest: (handler) => {
            request = handler;
        },
    };
}

// stretch: what makeStretch returns. Returns whether sizes follow the zoom at each frame
// (live: a small graph), and what a selection needs to move the view (#142): the zoom of
// the whole graph, a view brought within the bounds, a hold on the bounds while it
// animates, and a callback when the whole graph is shown again; and whether the whole
// graph is shown (#175).
export function bindViewport(cy, container, showAllButton, stretch) {
    // A small graph is drawn again with its exact sizes at each frame of a motion.
    const live = cy.elements().length <= LIVE_SIZES_MAX_ELEMENTS;
    const sizes = keepScreenSize(cy, live);
    const whole = makeWholeView(cy, stretch, sizes);
    // While a selection animates the view and the stretch together, the bounds wait.
    let held = false;
    const showAllListeners = [];
    const showAll = () => {
        whole.forget();
        for (const listener of showAllListeners) {
            listener();
        }
        whole.measure();
        button.update(whole.showsAll());
    };
    const button = bindShowAllButton(showAllButton, showAll);
    showAll();
    // Held during an animation that ends within the bounds; checked again at its end. The
    // view of a graph just developed or reduced (#451) may start below its new zoom limit.
    const hold = (on) => {
        held = on;
        if (on) {
            cy.minZoom(NO_MIN_ZOOM);
        } else if (whole.measured()) {
            cy.minZoom(whole.zoom());
            whole.keepWithin();
            button.update(whole.showsAll());
        }
    };
    cy.on("viewport", () => {
        if (whole.measured()) {
            if (!held) {
                whole.keepWithin();
            }
            button.update(whole.showsAll());
        }
    });
    // The container may change size after initialization (page layout, window resize).
    new ResizeObserver(() => {
        cy.resize();
        showAll();
    }).observe(container);
    return {
        live,
        wholeZoom: whole.zoom,
        showsAll: whole.showsAll,
        within: whole.within,
        hold,
        onShowAll: (listener) => showAllListeners.push(listener),
        onShowAllRequest: button.onRequest,
        // The view of the whole graph, unstretched: where the button goes back to.
        wholeView: whole.view,
        // Measures the whole graph again and shows it (after a new layout, layout_time.js).
        showAll,
        // Measures the whole graph again once it is developed or reduced (#451), from the
        // positions of its new layout: the view fits it (expand.js puts it back after).
        remeasure: () => {
            whole.forget();
            whole.measure();
        },
    };
}
