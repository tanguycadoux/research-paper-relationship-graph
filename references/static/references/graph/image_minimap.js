// The minimap of the image of a large graph (#453): the nodes drawn as dots in a canvas,
// once, from the list of the nodes (a second copy of the SVG would weigh as much as the
// image), and a rectangle over it for the part shown. A click or a drag in it moves the
// view there.

// The longest side of the minimap, in pixels: at most a third of the width of the frame.
const SIDE = 180;
// A node of level 1, --color-graph-cited (assets/css/source.css, #470) in sRGB.
const DOT_COLOR = "#59b47d";

export function createMinimap(box, nodes, view) {
    const canvas = box.querySelector("canvas");
    const rectangle = box.querySelector("[data-image-minimap-view]");
    const { width, height } = view.size;
    const scale = Math.min(SIDE, view.frame().width / 3) / Math.max(width, height);
    drawDots(canvas, nodes, scale, width, height);
    box.hidden = false;

    function update(current) {
        const frame = view.frame();
        const left = Math.max(0, current.x * scale);
        const top = Math.max(0, current.y * scale);
        const right = Math.min(width, current.x + frame.width * current.unit) * scale;
        const bottom = Math.min(height, current.y + frame.height * current.unit) * scale;
        rectangle.style.left = `${left}px`;
        rectangle.style.top = `${top}px`;
        rectangle.style.width = `${Math.max(2, right - left)}px`;
        rectangle.style.height = `${Math.max(2, bottom - top)}px`;
    }

    listenPointer(canvas, (x, y) => view.centreOn(x / scale, y / scale, { settle: true }));
    view.onChange(update);
    update(view.current());
}

function drawDots(canvas, nodes, scale, width, height) {
    const ratio = window.devicePixelRatio || 1;
    canvas.style.width = `${width * scale}px`;
    canvas.style.height = `${height * scale}px`;
    canvas.width = Math.round(width * scale * ratio);
    canvas.height = Math.round(height * scale * ratio);
    const context = canvas.getContext("2d");
    context.scale(ratio * scale, ratio * scale);
    context.fillStyle = DOT_COLOR;
    // At least half a pixel of the minimap: the smallest nodes stay visible.
    const least = 0.5 / scale;
    for (const node of nodes) {
        const radius = Math.max(least, node.r);
        context.fillRect(node.x - radius, node.y - radius, 2 * radius, 2 * radius);
    }
}

// A press, then each move while pressed: the point of the canvas, in its pixels.
function listenPointer(canvas, moveTo) {
    const at = (event) => {
        const box = canvas.getBoundingClientRect();
        moveTo(event.clientX - box.left, event.clientY - box.top);
    };
    canvas.addEventListener("pointerdown", (event) => {
        canvas.setPointerCapture(event.pointerId);
        at(event);
    });
    canvas.addEventListener("pointermove", (event) => {
        if (canvas.hasPointerCapture(event.pointerId)) {
            at(event);
        }
    });
}
