// The nodes lit on the image of a large graph (#453): the one hovered, in the image or in
// the list, and those checked in the list, with their links. Drawn in an SVG of their own
// over the image (layer), with the same viewBox: the thousands of circles and edges of the
// image are never touched, and lighting a node costs only its ring.

const SVG = "http://www.w3.org/2000/svg";
const HOVER_COLOR = "#1d4ed8";
// --color-graph-citing (assets/css/source.css).
const CHECKED_COLOR = "#eb6834";
// The ring around a node: this many pixels of the screen beyond it, whatever the zoom,
// so that a node of a few pixels shows in the view of the whole image.
const RING_GAP = 6;
const RING_WIDTH = 3;

export function createHighlight(layer, nodes, edges) {
    const links = element("g", {});
    const rings = element("g", {});
    layer.append(links, rings);
    const checked = new Map();
    const state = { hovered: null, unit: 1, neighbours: null };

    function ring(index, color) {
        const node = nodes[index];
        return element("circle", {
            cx: node.x,
            cy: node.y,
            r: node.r + RING_GAP * state.unit,
            fill: "none",
            stroke: color,
            "stroke-width": RING_WIDTH,
            "vector-effect": "non-scaling-stroke",
        });
    }

    function redraw() {
        rings.replaceChildren(...[...checked.keys()].map((index) => ring(index, CHECKED_COLOR)));
        if (state.hovered !== null) {
            rings.append(ring(state.hovered, HOVER_COLOR));
        }
    }

    function hover(index) {
        if (index !== state.hovered) {
            state.hovered = index;
            redraw();
        }
    }

    function check(index, on) {
        if (on && !checked.has(index)) {
            state.neighbours ??= adjacency(nodes.length, edges);
            checked.set(index, linkPath(nodes, index, state.neighbours[index]));
        } else if (!on) {
            checked.get(index)?.remove();
            checked.delete(index);
        }
        links.replaceChildren(...checked.values());
        redraw();
    }

    // The rings keep their gap on the screen: redrawn at each new scale.
    function rescale(view) {
        if (view.unit !== state.unit) {
            state.unit = view.unit;
            redraw();
        }
    }

    return { hover, check, rescale };
}

function element(name, attributes) {
    const node = document.createElementNS(SVG, name);
    for (const [key, value] of Object.entries(attributes)) {
        node.setAttribute(key, value);
    }
    return node;
}

// The neighbours of each node, from the edges as a flat list of pairs of ranks.
function adjacency(count, edges) {
    const neighbours = Array.from({ length: count }, () => []);
    for (let i = 0; i < edges.length; i += 2) {
        neighbours[edges[i]].push(edges[i + 1]);
        neighbours[edges[i + 1]].push(edges[i]);
    }
    return neighbours;
}

function linkPath(nodes, index, neighbours) {
    const { x, y } = nodes[index];
    const d = neighbours.map((other) => `M${x} ${y}L${nodes[other].x} ${nodes[other].y}`).join("");
    return element("path", {
        d: d || "M0 0",
        stroke: CHECKED_COLOR,
        "stroke-width": 2,
        "stroke-opacity": 0.8,
        fill: "none",
        "vector-effect": "non-scaling-stroke",
    });
}
