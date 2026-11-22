// The view of the image of a large graph (#453): the part of the SVG shown in the frame,
// as its viewBox, always of the frame's proportions. Zoom with the wheel, centred on the
// pointer; move by dragging; « + », « − » and « Tout voir ».
//
// During a gesture, the SVG already drawn is only moved and scaled by a CSS transform,
// which the browser does without drawing it again; the viewBox follows once the gesture
// has stopped (SETTLE ms), and the image is drawn sharp at its new scale. Setting the
// viewBox at each step would draw the 9 500 circles and 56 000 edges of the graph of the
// authors again at each frame. The layer of the lit nodes (image_highlight.js) is a second
// SVG over the first, moved with it: lighting a node never draws the image again.

const SETTLE = 150;
// Zoom of a wheel notch (deltaY of 100) and of a button.
const WHEEL_ZOOM = 1.25;
const BUTTON_ZOOM = 1.6;
// At most this many screen pixels per unit of the image; at least the whole image.
const MAX_SCALE = 8;
// A press that moves less than this is a click (on a node, its link), not a drag.
const DRAG_THRESHOLD = 4;

// frame: the element over the image that takes the wheel and the pointer (image_pointer.js).
export function createView(frame, svgs) {
    const size = imageSize(svgs[0]);
    const listeners = { change: [], draw: [] };
    const state = { view: null, drawn: null, timer: null, frame: frame.getBoundingClientRect() };
    for (const svg of svgs) {
        svg.setAttribute("width", "100%");
        svg.setAttribute("height", "100%");
        svg.style.transformOrigin = "0 0";
        svg.style.willChange = "transform";
    }

    function fitted() {
        const { width, height } = state.frame;
        const unit = Math.max(size.width / width, size.height / height);
        return {
            x: (size.width - width * unit) / 2,
            y: (size.height - height * unit) / 2,
            unit,
        };
    }

    // The view kept within the image: never smaller than the whole image, never further
    // in than MAX_SCALE, and its centre on the image.
    function bounded(view) {
        const { width, height } = state.frame;
        const unit = Math.min(fitted().unit, Math.max(1 / MAX_SCALE, view.unit));
        const centreX = clamp(view.x + (width * view.unit) / 2, 0, size.width);
        const centreY = clamp(view.y + (height * view.unit) / 2, 0, size.height);
        return { x: centreX - (width * unit) / 2, y: centreY - (height * unit) / 2, unit };
    }

    function show(view, { settle = true } = {}) {
        state.view = bounded(view);
        if (!settle || !state.drawn) {
            draw();
        } else {
            moveDrawn();
            clearTimeout(state.timer);
            state.timer = setTimeout(draw, SETTLE);
        }
        listeners.change.forEach((listener) => listener(state.view));
    }

    function draw() {
        clearTimeout(state.timer);
        const { x, y, unit } = state.view;
        const { width, height } = state.frame;
        for (const svg of svgs) {
            svg.setAttribute("viewBox", `${x} ${y} ${width * unit} ${height * unit}`);
            svg.style.transform = "";
        }
        state.drawn = state.view;
        listeners.draw.forEach((listener) => listener(state.view));
    }

    // The SVG drawn for state.drawn, moved and scaled to show state.view.
    function moveDrawn() {
        const { drawn, view } = state;
        const scale = drawn.unit / view.unit;
        const dx = (drawn.x - view.x) / view.unit;
        const dy = (drawn.y - view.y) / view.unit;
        for (const svg of svgs) {
            svg.style.transform = `translate(${dx}px, ${dy}px) scale(${scale})`;
        }
    }

    // Zoomed by factor around a point of the frame, in pixels.
    function zoomAt(factor, px, py, options) {
        const { x, y, unit } = state.view;
        const next = unit / factor;
        show({ x: x + px * (unit - next), y: y + py * (unit - next), unit: next }, options);
    }

    function zoomCentre(factor) {
        zoomAt(factor, state.frame.width / 2, state.frame.height / 2, { settle: false });
    }

    // A point of the image in the middle of the frame, zoomed in to at least `unit`;
    // settle: drawn once a series of moves has stopped (a drag in the minimap).
    function centreOn(px, py, { unit = state.view.unit, settle = false } = {}) {
        const { width, height } = state.frame;
        const next = Math.min(state.view.unit, unit);
        show({ x: px - (width * next) / 2, y: py - (height * next) / 2, unit: next }, { settle });
    }

    function resize() {
        state.frame = frame.getBoundingClientRect();
        show(state.view ?? fitted(), { settle: false });
    }

    listenWheel(frame, (factor, px, py) => zoomAt(factor, px, py));
    listenDrag(frame, (dx, dy) => {
        const { x, y, unit } = state.view;
        show({ x: x - dx * unit, y: y - dy * unit, unit });
    });
    new ResizeObserver(resize).observe(frame);
    resize();

    return {
        size,
        frame: () => state.frame,
        current: () => state.view,
        showAll: () => show(fitted(), { settle: false }),
        zoomIn: () => zoomCentre(BUTTON_ZOOM),
        zoomOut: () => zoomCentre(1 / BUTTON_ZOOM),
        centreOn,
        // At each step of a gesture, and once the image is drawn at the new view.
        onChange: (listener) => listeners.change.push(listener),
        onDraw: (listener) => listeners.draw.push(listener),
    };
}

function imageSize(svg) {
    const [, , width, height] = svg.getAttribute("viewBox").split(/[\s,]+/).map(Number);
    return { width, height };
}

function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
}

function listenWheel(frame, zoomAt) {
    frame.addEventListener(
        "wheel",
        (event) => {
            event.preventDefault();
            const box = frame.getBoundingClientRect();
            // Lines or pages of a wheel, pixels of a touchpad: about 100 per notch.
            const delta = event.deltaY * (event.deltaMode ? 33 : 1);
            const factor = WHEEL_ZOOM ** (-delta / 100);
            zoomAt(factor, event.clientX - box.left, event.clientY - box.top);
        },
        { passive: false },
    );
}

// Drag to move the view; the click that ends a drag does not follow the link of the node
// under the pointer.
function listenDrag(frame, move) {
    let press = null;
    frame.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) {
            return;
        }
        press = { x: event.clientX, y: event.clientY, dragging: false, id: event.pointerId };
    });
    frame.addEventListener("pointermove", (event) => {
        if (!press || event.pointerId !== press.id) {
            return;
        }
        const dx = event.clientX - press.x;
        const dy = event.clientY - press.y;
        if (!press.dragging && Math.hypot(dx, dy) < DRAG_THRESHOLD) {
            return;
        }
        if (!press.dragging) {
            press.dragging = true;
            frame.setPointerCapture(event.pointerId);
        }
        press.x = event.clientX;
        press.y = event.clientY;
        move(dx, dy);
    });
    const release = () => {
        if (press?.dragging) {
            // The click, if any, comes before the next task.
            frame.dataset.dragged = "";
            setTimeout(() => delete frame.dataset.dragged, 0);
        }
        press = null;
    };
    frame.addEventListener("pointerup", release);
    frame.addEventListener("pointercancel", release);
    frame.addEventListener(
        "click",
        (event) => {
            if ("dragged" in frame.dataset) {
                event.preventDefault();
                event.stopImmediatePropagation();
            }
        },
        true,
    );
}
