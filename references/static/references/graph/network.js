// The network view (#195): no time axis, the positions come from Cytoscape's own
// force-directed layout (cose), built in: no dependency. Linked publications are drawn
// close together, in both directions: a selection zooms uniformly (focus.js), without
// the stretch of the timeline. A large network, or one given more time, is laid out in a
// Web Worker (layout_aside.js, #202): the page keeps responding.

import { findCrowns, hubSize, lineUpShared, placeCrowns, turnToFrame } from "./crown.js";
import { countCrossings } from "./crossings.js";
import { seeded } from "./random.js";
import { nodeSizes } from "./style.js";

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

// The drawing with the fewest crossings among the starts of cose (#323): the spiral in
// the order of the data, then in orders shuffled from the seeds 1, 2, 3…, as long as
// another start fits before the deadline (at the average time of the starts so far). Stops
// at a drawing without any crossing. The crossings are only counted when a second start
// fits: on a large graph, they would take long too.
function fewestCrossings(nodes, edges, frame, deadline) {
    const leavesOf = findCrowns(nodes, edges);
    const start = performance.now();
    const first = arrange(nodes, edges, frame, leavesOf);
    // The time of a start, on average so far.
    const perStart = (starts) => (performance.now() - start) / starts;
    if (performance.now() + perStart(1) > deadline) {
        return first;
    }
    let best = { positions: first, crossings: crossingsAt(first, edges) };
    for (let seed = 1; best.crossings > 0 && performance.now() + perStart(seed) <= deadline; seed++) {
        const positions = arrange(restarted(nodes, seed), edges, frame, leavesOf);
        const crossings = crossingsAt(positions, edges);
        if (crossings < best.crossings) {
            best = { positions, crossings };
        }
    }
    return best.positions;
}

// The positions of the nodes of networkNodes, by id (#323), the drawing turned to fill the
// frame. budget: the time given to the layout, in milliseconds (at least one start of cose).
export function networkPositions(nodes, edges, frame, budget = 0) {
    const positions = fewestCrossings(nodes, edges, frame, performance.now() + budget);
    const sizes = new Map(nodes.map((node) => [node.data.id, node.data.size]));
    return turnToFrame(positions, sizes, frame);
}

// The nodes placed at the given positions (by id).
export function placedAt(nodes, positions) {
    return nodes.map((node) => ({ ...node, position: positions.get(node.data.id) }));
}
