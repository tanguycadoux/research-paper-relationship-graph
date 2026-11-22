// The node under the pointer on the image of a large graph (#453): its name in a tooltip,
// its ring and its row lit. A click selects it, or takes it out of the selection (a drag
// is no click: image_view.js); with Ctrl, ⌘ or the middle button, its page opens in a new
// tab. Its page is also linked from the selection (image_selection.js).
//
// The SVG takes no pointer event: the input layer over it does, and finds the node itself
// in a grid of the nodes. Under a wheel handler (the zoom), the browser records each of the
// 66 000 elements of the SVG of the authors as a region of the handler, and going through
// them took 90 ms at each frame where anything of the page changed.

// The side of a cell of the grid, in units of the image.
const CELL = 64;
// A node is under the pointer up to this many pixels of the screen beyond its edge (at
// most a cell: the whole image of the authors is about 8 units a pixel).
const TOLERANCE = 3;

// actions: hover(index or null), select(index), which toggles the selection of the node.
export function createPointer(input, tooltip, nodes, view, actions) {
    const grid = cells(nodes);
    let current = null;

    function nodeAt(event) {
        const box = input.getBoundingClientRect();
        const { x, y, unit } = view.current();
        const px = x + (event.clientX - box.left) * unit;
        const py = y + (event.clientY - box.top) * unit;
        return closest(around(grid, px, py), nodes, px, py, TOLERANCE * unit);
    }

    function point(event) {
        const index = event.buttons ? null : nodeAt(event);
        if (index !== current) {
            current = index;
            input.toggleAttribute("data-over", index !== null);
            actions.hover(index);
        }
        showTooltip(tooltip, input, event, index === null ? null : nodes[index].label);
    }

    input.addEventListener("pointermove", point);
    input.addEventListener("wheel", point, { passive: true });
    input.addEventListener("pointerleave", () => {
        current = null;
        actions.hover(null);
        showTooltip(tooltip, input, null, null);
    });
    input.addEventListener("click", (event) => {
        const index = nodeAt(event);
        if (index === null) {
            return;
        }
        if (event.ctrlKey || event.metaKey) {
            openNode(nodes, index, event);
        } else {
            actions.select(index);
        }
    });
    input.addEventListener("auxclick", (event) => {
        const index = nodeAt(event);
        if (event.button === 1 && index !== null) {
            openNode(nodes, index, event);
        }
    });
}

// Each node in the cells its disc covers.
function cells(nodes) {
    const grid = new Map();
    nodes.forEach((node, index) => {
        const [left, top] = cellOf(node.x - node.r, node.y - node.r);
        const [right, bottom] = cellOf(node.x + node.r, node.y + node.r);
        for (let cx = left; cx <= right; cx++) {
            for (let cy = top; cy <= bottom; cy++) {
                const name = `${cx},${cy}`;
                if (!grid.has(name)) {
                    grid.set(name, []);
                }
                grid.get(name).push(index);
            }
        }
    });
    return grid;
}

function cellOf(x, y) {
    return [Math.floor(x / CELL), Math.floor(y / CELL)];
}

// The nodes of the cell of the point and of the eight around it: those within the
// tolerance of the point, even across the edge of its cell.
function around(grid, x, y) {
    const [cx, cy] = cellOf(x, y);
    const found = [];
    for (let dx = -1; dx <= 1; dx++) {
        for (let dy = -1; dy <= 1; dy++) {
            found.push(...(grid.get(`${cx + dx},${cy + dy}`) ?? []));
        }
    }
    return found;
}

// Inside a node, the largest (drawn last, on top); otherwise the nearest edge within the
// tolerance.
function closest(candidates, nodes, x, y, tolerance) {
    let best = null;
    let bestScore = Infinity;
    for (const index of candidates) {
        const node = nodes[index];
        const gap = Math.hypot(node.x - x, node.y - y) - node.r;
        const score = gap <= 0 ? -node.r : gap;
        if (gap <= tolerance && score < bestScore) {
            best = index;
            bestScore = score;
        }
    }
    return best;
}

// In a new tab, like a link.
function openNode(nodes, index, event) {
    event.preventDefault();
    window.open(nodes[index].url, "_blank", "noopener");
}

// The name of the node above the pointer, kept in the frame.
function showTooltip(tooltip, input, event, label) {
    tooltip.hidden = label === null;
    if (label === null) {
        return;
    }
    tooltip.textContent = label;
    const box = input.getBoundingClientRect();
    const left = Math.min(event.clientX - box.left + 12, box.width - tooltip.offsetWidth - 4);
    const top = event.clientY - box.top - tooltip.offsetHeight - 10;
    tooltip.style.left = `${Math.max(4, left)}px`;
    tooltip.style.top = `${top < 4 ? event.clientY - box.top + 18 : top}px`;
}
