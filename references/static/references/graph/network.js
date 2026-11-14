// The network view (#195): no time axis, the positions come from Cytoscape's own
// force-directed layout (cose), built in: no dependency. Linked publications are drawn
// close together, in both directions: a selection zooms uniformly (focus.js), without
// the stretch of the timeline.

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
    idealEdgeLength: () => 48,
    nodeRepulsion: () => 16000,
    nodeOverlap: 8,
    componentSpacing: 48,
    gravity: 0.5,
};

// The elements of the nodes, with their size (style.js) and a starting position: on a
// spiral (golden angle), in the order of the data. cose would otherwise start from random
// positions, and the same graph would change at each visit.
export function networkNodes(nodes) {
    const sizes = nodeSizes(nodes);
    return nodes.map((node, i) => {
        const radius = START_SPACING * Math.sqrt(i);
        const angle = i * GOLDEN_ANGLE;
        return {
            data: { ...node.data, size: sizes[i] },
            position: { x: radius * Math.cos(angle), y: radius * Math.sin(angle) },
        };
    });
}

// Runs cose on the graph, at once (animate: false): before the view and the selection
// read the positions.
export function layOutNetwork(cy) {
    cy.layout(COSE).run();
}
