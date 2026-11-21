// Coauthorship graph (#222): the authors, linked by the publications they signed together
// (services/display/author_graph.py), in the network view only (#195). Entry point,
// loaded as an ES module after cytoscape.min.js (global `cytoscape`). The frame, the
// view, the uniform zoom on a selection and the export are those of every graph (graph.js).

import { bindCoauthorSelection } from "./coauthor_selection.js";
import { bindGraph, createGraph, graphFrame, LAYOUT_MEASURE } from "./graph.js";
import { COSE, spiralPosition } from "./network.js";
import { color, graphStyle } from "./style.js";

// Diameter of a node on the screen: its area follows the number of publications.
const MIN_SIZE = 14;
const MAX_SIZE = 32;
// Width of an edge on the screen, from the weakest link to the strongest.
const MIN_WIDTH = 0.75;
const MAX_WIDTH = 4;
// Opacity of an edge: the many weak links of large publications stay in the background.
const MIN_OPACITY = 0.3;
const MAX_OPACITY = 0.9;
// The ideal length of an edge and its elasticity in cose (the lower, the stiffer: the
// spring pulls with (length - ideal)² / elasticity), from the weakest link to the
// strongest. Cose's defaults are 48 (network.js) and 32: a strong link is half as long
// and four times as stiff as a weak one, the weak ones keep their place in the network.
const LONGEST_EDGE = 64;
const SHORTEST_EDGE = 32;
const SOFTEST_EDGE = 64;
const STIFFEST_EDGE = 16;

const lerp = (a, b, t) => a + (b - a) * t;

// Starting positions on the spiral of the network view (network.js): the same graph is
// laid out the same way at each visit, the author of the graph at its centre.
function nodeElements(nodes) {
    const most = Math.max(1, ...nodes.map((n) => n.data.publications));
    return nodes.map((node, i) => {
        const size = lerp(MIN_SIZE, MAX_SIZE, Math.sqrt(node.data.publications / most));
        return { data: { ...node.data, size }, position: spiralPosition(i) };
    });
}

// strength: 0 for the weakest link of the graph, 1 for the strongest; the square root
// of the weight relative to the strongest keeps the many weak links visible.
function edgeElements(edges) {
    const heaviest = Math.max(...edges.map((e) => e.data.weight));
    return edges.map((edge) => {
        const strength = Math.sqrt(edge.data.weight / heaviest);
        return {
            data: {
                ...edge.data,
                strength,
                width: lerp(MIN_WIDTH, MAX_WIDTH, strength),
                opacity: lerp(MIN_OPACITY, MAX_OPACITY, strength),
            },
        };
    });
}

// Edges as wide and as dark as their link is strong, on the screen whatever the zoom
// (#185), the faded elements a little lighter than on the citation graphs; the links of a
// selected author in the light shade of its colour.
function coauthorStyle() {
    const width = (extra) => (edge) => (edge.data("width") + extra) / edge.cy().zoom();
    const edges = { width: width(0), hoveredWidth: width(1), opacity: "data(opacity)", faded: 0.12 };
    return [
        ...graphStyle(edges),
        {
            selector: "edge.coauthor",
            style: { width: width(1), "line-color": color("cited-light"), opacity: 1, "z-index": 5 },
        },
    ];
}

function layOut(cy) {
    performance.mark(LAYOUT_MEASURE);
    cy.layout({
        ...COSE,
        idealEdgeLength: (edge) => lerp(LONGEST_EDGE, SHORTEST_EDGE, edge.data("strength")),
        edgeElasticity: (edge) => lerp(SOFTEST_EDGE, STIFFEST_EDGE, edge.data("strength")),
    }).run();
    performance.measure(LAYOUT_MEASURE, LAYOUT_MEASURE);
}

function render() {
    const frame = graphFrame();
    const nodes = nodeElements(frame.data.nodes);
    const edges = edgeElements(frame.data.edges);
    const cy = createGraph(frame.container, nodes, edges, coauthorStyle());
    layOut(cy);
    // Never stretched: the network keeps its distances (#195); the view needs it anyway.
    bindGraph(cy, frame, { bindSelection: bindCoauthorSelection, uniform: true });
}

render();
