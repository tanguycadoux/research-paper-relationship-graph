// Sizes constant on the screen (#185): the style divides them by the zoom (style.js), and
// Cytoscape evaluates it again when told to. On a small graph, at most once per frame. On
// a large one (#202), once the zoom has stopped, and then by parts (#326): evaluating the
// style of every element at once costs Cytoscape about 0.03 ms each, and a frame of 140 to
// 220 ms for 4 300 elements, a jolt at the end of each gesture. The elements in view come
// first, at once, then the others, a few milliseconds of them in each frame. A new zoom
// stops the pass and starts another once it stops.

// On a large graph, sizes are evaluated again once the zoom has not changed for this
// long, in milliseconds: meanwhile they scale with the zoom, like a picture.
const SETTLE_DELAY = 150;
// Around the view, in pixels of the screen: the largest node with its ring and its mark
// (style.js), whose centre is just out of view, still shows.
const VIEW_MARGIN = 48;
// Time given in each frame to the elements out of view, in milliseconds: Cytoscape still
// draws the frame, 10 to 30 ms for 4 300 elements.
const FRAME_BUDGET = 8;
// Elements evaluated together, between two looks at the time.
const PART = 50;

// The view widened by its margin, in graph coordinates.
function widenedView(cy) {
    const extent = cy.extent();
    const margin = VIEW_MARGIN / cy.zoom();
    return { x1: extent.x1 - margin, x2: extent.x2 + margin, y1: extent.y1 - margin, y2: extent.y2 + margin };
}

// The box of an element in graph coordinates, from its centre or the centres of its ends.
function centresBox(element) {
    if (element.isNode()) {
        const { x, y } = element.position();
        return { x1: x, x2: x, y1: y, y2: y };
    }
    const a = element.source().position();
    const b = element.target().position();
    return { x1: Math.min(a.x, b.x), x2: Math.max(a.x, b.x), y1: Math.min(a.y, b.y), y2: Math.max(a.y, b.y) };
}

// The elements in view, and the others: nodes by their centre, edges by the box of their
// ends, which may count in a few long edges beside the view (harmless).
function splitByView(cy) {
    const view = widenedView(cy);
    const crosses = (box) => box.x2 >= view.x1 && box.x1 <= view.x2 && box.y2 >= view.y1 && box.y1 <= view.y2;
    const shown = cy.elements().filter((element) => crosses(centresBox(element)));
    return { shown, others: cy.elements().difference(shown) };
}

// Evaluates the style of a large graph again: the elements in view at once, drawn at the
// next frame; the others then, a few milliseconds of them in each frame. Cytoscape
// evaluates the style of an element when it reads it (pstyle): it is read here, to keep to
// the time of the frame, rather than at the next drawing, which reads every element whose
// style is to be evaluated, in view or not. Returns how to stop the pass.
function refreshByParts(cy) {
    const { shown, others } = splitByView(cy);
    shown.updateStyle();
    let next = 0;
    let frame = null;
    const step = () => {
        const end = performance.now() + FRAME_BUDGET;
        while (next < others.length && performance.now() < end) {
            // Removed meanwhile: a graph developed or reduced (expand.js).
            const part = others.slice(next, next + PART).filter((element) => !element.removed());
            next += PART;
            // Out of view: no frame is asked for them (Cytoscape draws one all the same,
            // their bounds having changed).
            part.updateStyle(false);
            part.forEach((element) => element.pstyle("width"));
        }
        frame = next < others.length ? requestAnimationFrame(step) : null;
    };
    frame = requestAnimationFrame(step);
    return () => {
        if (frame !== null) {
            cancelAnimationFrame(frame);
            frame = null;
        }
    };
}

// Sizes in the style are divided by the zoom (#185): they are evaluated again when the
// zoom changes, at most once per frame on a small graph (live), by parts once the zoom
// stops on a large one. Returns how to evaluate them all now (the view of the whole graph
// measures them, viewport.js), and to say that they are right for the zoom of the moment:
// the pass is then not needed.
export function keepScreenSize(cy, live) {
    let zoom = cy.zoom();
    let pending = false;
    let settle = null;
    let stopPass = () => {};
    const update = () => {
        pending = false;
        zoom = cy.zoom();
        cy.style().update();
    };
    const settled = () => {
        clearTimeout(settle);
        stopPass();
        zoom = cy.zoom();
    };
    cy.style().update();
    cy.on("viewport", () => {
        if (cy.zoom() === zoom) {
            return;
        }
        if (!live) {
            stopPass();
            clearTimeout(settle);
            settle = setTimeout(() => {
                zoom = cy.zoom();
                stopPass = refreshByParts(cy);
            }, SETTLE_DELAY);
            return;
        }
        if (!pending) {
            pending = true;
            requestAnimationFrame(update);
        }
    });
    return {
        updateNow: () => {
            settled();
            cy.style().update();
        },
        // On a small graph, the update of the next frame stays: it costs little.
        settled: () => {
            if (!live) {
                settled();
            }
        },
    };
}
