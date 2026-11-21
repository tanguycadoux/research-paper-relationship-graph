// The network view (#195): no time axis, the positions come from Cytoscape's own
// force-directed layout (cose), built in: no dependency. Linked publications are drawn
// close together, in both directions: a selection zooms uniformly (focus.js), without
// the stretch of the timeline. A large network is laid out in a Web Worker
// (network-worker.js, #202): the page keeps responding, with a message in the frame.

import { nodeSizes } from "./style.js";
import { LIVE_SIZES_MAX_ELEMENTS } from "./viewport.js";

// Distance between two consecutive starting points on the spiral, in pixels.
const START_SPACING = 30;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

// Options of cose. Its iterations stop once the temperature falls under minTemp:
// initialTemp * coolingFactor ** i. Each costs n² for the repulsion: the 690 iterations of
// the default cooling (1 000, 0.99, 1) take 27 s for 1 800 publications; the 66 of 0.9
// take 2.9 s. Fewer iterations leave more nodes overlapping: a stronger repulsion makes
// up for part of it (193 pairs instead of 329, 60 by default; docs/banc-graphe.md).
export const COSE = {
    name: "cose",
    coolingFactor: 0.9,
    animate: false,
    // From the deterministic spiral below: the same graph is laid out the same way.
    randomize: false,
    // bindViewport fits the graph to the frame.
    fit: false,
    // Sizes are on the screen (#185): at the zoom of the layout (1), they are in pixels.
    nodeDimensionsIncludeLabels: false,
    // Numbers rather than functions: the options go to the Web Worker as they are.
    idealEdgeLength: 48,
    nodeRepulsion: 16000,
    nodeOverlap: 8,
    componentSpacing: 48,
    gravity: 0.5,
};

// The starting position of the i-th node of a network: on a spiral (golden angle), the
// first at the centre. cose would otherwise start from random positions, and the same
// graph would change at each visit.
export function spiralPosition(i) {
    const radius = START_SPACING * Math.sqrt(i);
    const angle = i * GOLDEN_ANGLE;
    return { x: radius * Math.cos(angle), y: radius * Math.sin(angle) };
}

// The elements of the nodes, with their size (style.js) and their starting position, in
// the order of the data.
export function networkNodes(nodes) {
    const sizes = nodeSizes(nodes);
    return nodes.map((node, i) => ({ data: { ...node.data, size: sizes[i] }, position: spiralPosition(i) }));
}

// Runs cose on the graph, at once (animate: false): before the view and the selection
// read the positions.
export function layOutNetwork(cy) {
    cy.layout(COSE).run();
}

// cose reads the size of the nodes (with their border) from the style: in the Web Worker,
// Cytoscape has no page and no style.js, so it gets the sizes of style.js at the zoom of
// the layout (1). Checked: the positions are the same as in the page (docs/banc-graphe.md).
export const LAYOUT_STYLE = [
    { selector: "node", style: { width: "data(size)", height: "data(size)", "border-width": 2 } },
];

// Up to this many elements (nodes and edges), cose takes less than about 100 ms: it runs in
// the page, without a message that would only flash. Beyond, in a Web Worker: 2.9 s for a
// graph of 1 800 publications, during which the page would not respond.
const WORKER_MIN_ELEMENTS = LIVE_SIZES_MAX_ELEMENTS;

function startWorker() {
    try {
        return new Worker(new URL("./network-worker.js", import.meta.url), { type: "module" });
    } catch {
        return null;
    }
}

// The nodes of networkNodes with the positions of cose, computed in a Web Worker while
// `waiting` (the message in the frame) shows; container: the frame of the graph, whose size
// cose reads. Resolves to null on a small graph, or if the worker fails: the caller then
// lays the graph out in the page (layOutNetwork).
export function layOutAside(nodes, edges, container, waiting) {
    const worker = nodes.length + edges.length > WORKER_MIN_ELEMENTS ? startWorker() : null;
    if (!worker) {
        return Promise.resolve(null);
    }
    waiting.hidden = false;
    return new Promise((resolve) => {
        const done = (positions) => {
            worker.terminate();
            waiting.hidden = true;
            const placed = (node) => ({ ...node, position: positions[node.data.id] });
            resolve(positions ? nodes.map(placed) : null);
        };
        const failed = (error) => {
            console.error("Network layout failed in the Web Worker, done in the page instead:", error);
            done(null);
        };
        worker.onmessage = ({ data }) => (data.positions ? done(data.positions) : failed(data.error));
        worker.onerror = (event) => failed(event.message);
        // The worker loads the same Cytoscape as the page.
        const library = document.querySelector('script[src$="/cytoscape.min.js"]').src;
        const size = { width: container.clientWidth, height: container.clientHeight };
        worker.postMessage({ library, ...size, elements: [...nodes, ...edges] });
    });
}
