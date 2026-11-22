// The network view (#195): no time axis, the positions come from Cytoscape's own
// force-directed layout (cose), built in: no dependency. Linked publications are drawn
// close together, in both directions: a selection zooms uniformly (focus.js), without
// the stretch of the timeline. A large network is laid out in a Web Worker
// (network-worker.js, #202): the page keeps responding, with a message in the frame.

import { findCrowns, hubSize, lineUpShared, placeCrowns, turnToFrame } from "./crown.js";
import { countCrossings } from "./crossings.js";
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

// cose reads the size of the nodes (with their border) from the style: on a headless
// Cytoscape, in the page or in the Web Worker, without style.js, it gets the sizes of
// style.js at the zoom of the layout (1).
export const LAYOUT_STYLE = [
    { selector: "node", style: { width: "data(size)", height: "data(size)", "border-width": 2 } },
];

// Up to this many elements (nodes and edges), cose takes less than about 100 ms: it runs in
// the page, without a message that would only flash. Beyond, in a Web Worker: 2.9 s for a
// graph of 1 800 publications, during which the page would not respond.
const WORKER_MIN_ELEMENTS = LIVE_SIZES_MAX_ELEMENTS;
// Up to this many elements, cose runs from STARTS starting points, and the drawing with the
// fewest crossings is kept (#323): 60 ms for 226 elements instead of 30 for one. Beyond,
// the starts would hold the page too long.
const MULTI_START_MAX_ELEMENTS = 300;
const STARTS = 6;

function startWorker() {
    try {
        return new Worker(new URL("./network-worker.js", import.meta.url), { type: "module" });
    } catch {
        return null;
    }
}

// cose on a headless Cytoscape, in the page as in the Web Worker: the positions do not
// depend on where it runs. frame: its width and height, towards whose centre cose pulls the
// nodes (cy.width(), cy.height(), which a headless Cytoscape does not have). Returns the
// positions by id.
function cose(nodes, edges, frame) {
    const cy = cytoscape({
        headless: true,
        // cose reads the sizes of the nodes from the style.
        styleEnabled: true,
        style: LAYOUT_STYLE,
        elements: [...nodes, ...edges],
        // Otherwise the null layout would put every node at (0, 0), and cose would separate
        // them at random.
        layout: { name: "preset", fit: false },
    });
    cy.width = () => frame.width;
    cy.height = () => frame.height;
    cy.layout(COSE).run();
    const positions = new Map(cy.nodes().map((node) => [node.id(), { ...node.position() }]));
    cy.destroy();
    return positions;
}

// cose on the core of the graph, each hub as large as its crown, then the leaves in their
// crowns and the shared references lined up (crown.js). Returns the positions by id.
function arrange(nodes, edges, frame, leavesOf) {
    const leaves = new Set([...leavesOf.values()].flat().map((leaf) => leaf.data.id));
    const core = nodes
        .filter((node) => !leaves.has(node.data.id))
        .map((node) => {
            const crown = leavesOf.get(node.data.id);
            return crown ? { ...node, data: { ...node.data, size: hubSize(node, crown) } } : node;
        });
    const coreEdges = edges.filter(({ data }) => !leaves.has(data.source) && !leaves.has(data.target));
    const positions = cose(core, coreEdges, frame);
    placeCrowns(leavesOf, positions, coreEdges);
    lineUpShared(nodes, edges, leavesOf, positions);
    return positions;
}

// A pseudo-random generator from a seed (mulberry32): the same starts at each visit.
function seeded(seed) {
    let state = seed >>> 0;
    return () => {
        state = (state + 0x6d2b79f5) >>> 0;
        let t = Math.imul(state ^ (state >>> 15), state | 1);
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

// The nodes on the starting spiral in another order than that of the data, shuffled from
// the seed.
function restarted(nodes, seed) {
    const random = seeded(seed);
    const order = nodes.map((_, i) => i);
    for (let i = order.length - 1; i > 0; i--) {
        const j = Math.floor(random() * (i + 1));
        [order[i], order[j]] = [order[j], order[i]];
    }
    return nodes.map((node, i) => ({ ...node, position: spiralPosition(order[i]) }));
}

// The number of crossings between the edges at these positions (by id).
function crossingsAt(positions, edges) {
    const links = edges
        .map(({ data }) => [data.source, data.target])
        .filter(([a, b]) => positions.has(a) && positions.has(b));
    return countCrossings(links, (id) => positions.get(id));
}

// The drawing with the fewest crossings among the starts of cose (#323): several on a
// small graph, one on a large one. Stops at a drawing without any crossing.
function fewestCrossings(nodes, edges, frame) {
    const leavesOf = findCrowns(nodes, edges);
    const first = arrange(nodes, edges, frame, leavesOf);
    if (nodes.length + edges.length > MULTI_START_MAX_ELEMENTS) {
        return first;
    }
    let best = { positions: first, crossings: crossingsAt(first, edges) };
    for (let seed = 1; seed < STARTS && best.crossings > 0; seed++) {
        const positions = arrange(restarted(nodes, seed), edges, frame, leavesOf);
        const crossings = crossingsAt(positions, edges);
        if (crossings < best.crossings) {
            best = { positions, crossings };
        }
    }
    return best.positions;
}

// The positions of the nodes of networkNodes, by id (#323), the drawing turned to fill the
// frame.
export function networkPositions(nodes, edges, frame) {
    const positions = fewestCrossings(nodes, edges, frame);
    const sizes = new Map(nodes.map((node) => [node.data.id, node.data.size]));
    return turnToFrame(positions, sizes, frame);
}

// The nodes placed at the given positions (by id).
function placed(nodes, positions) {
    return nodes.map((node) => ({ ...node, position: positions.get(node.data.id) }));
}

// The nodes of networkNodes placed in the page, at once.
export function layOutHere(nodes, edges, container) {
    const frame = { width: container.clientWidth, height: container.clientHeight };
    return placed(nodes, networkPositions(nodes, edges, frame));
}

// The nodes of networkNodes placed in a Web Worker while `waiting` (the message in the
// frame) shows; container: the frame of the graph, whose size the layout reads. Resolves
// to null on a small graph, or if the worker fails: the caller then lays the graph out in
// the page (layOutHere).
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
            resolve(positions ? placed(nodes, new Map(Object.entries(positions))) : null);
        };
        const failed = (error) => {
            console.error("Network layout failed in the Web Worker, done in the page instead:", error);
            done(null);
        };
        worker.onmessage = ({ data }) => (data.positions ? done(data.positions) : failed(data.error));
        worker.onerror = (event) => failed(event.message);
        // The worker loads the same Cytoscape as the page.
        const library = document.querySelector('script[src$="/cytoscape.min.js"]').src;
        const frame = { width: container.clientWidth, height: container.clientHeight };
        worker.postMessage({ library, frame, nodes, edges });
    });
}
