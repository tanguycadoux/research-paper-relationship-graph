// Map of the keywords of a corpus (#418), in the manner of VOSviewer: the keywords (or the
// topics) of the OpenAlex answers, linked by the publications that carry both
// (services/display/keyword_graph.py), in the network view only. Entry point, loaded as
// an ES module after cytoscape.min.js (global `cytoscape`). The frame, the view, the
// uniform zoom on a selection and the export are those of every graph (graph.js); the
// names are drawn where they fit (keyword_labels.js).

import { bindGraph, createGraph, graphFrame, LAYOUT_MEASURE } from "./graph.js";
import { bindKeywordLabels, labelRules } from "./keyword_labels.js";
import { bindKeywordSelection } from "./keyword_selection.js";
import { COSE, spiralPosition } from "./network.js";
import { color, graphStyle } from "./style.js";

// Diameter of a node on the screen: its area follows the number of publications.
const MIN_SIZE = 12;
const MAX_SIZE = 36;
// Width of an edge on the screen, from the weakest link to the strongest.
const MIN_WIDTH = 0.75;
const MAX_WIDTH = 5;
// Opacity of an edge: the many links of a single publication stay in the background.
const MIN_OPACITY = 0.25;
const MAX_OPACITY = 0.85;
// The ideal length of an edge and its elasticity in cose, from the weakest link to the
// strongest, as on the graph of the coauthors (coauthors.js), a little longer: the names
// need the room.
const LONGEST_EDGE = 80;
const SHORTEST_EDGE = 40;
const SOFTEST_EDGE = 64;
const STIFFEST_EDGE = 16;

const lerp = (a, b, t) => a + (b - a) * t;

// Starting positions on the spiral of the network view (network.js): the same map is laid
// out the same way at each visit, the most carried term at its centre.
function nodeElements(nodes) {
    const most = Math.max(1, ...nodes.map((n) => n.data.publications));
    return nodes.map((node, i) => {
        const size = lerp(MIN_SIZE, MAX_SIZE, Math.sqrt(node.data.publications / most));
        return { data: { ...node.data, size }, position: spiralPosition(i) };
    });
}

// strength: from 0 to 1, the square root of the shared publications relative to the most
// shared, which keeps the links of a single publication visible.
function edgeElements(edges) {
    const heaviest = Math.max(1, ...edges.map((e) => e.data.shared));
    return edges.map((edge) => {
        const strength = Math.sqrt(edge.data.shared / heaviest);
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
// (#185); the links of a selected term in the light shade of its colour; then the names.
function keywordStyle(fontFamily) {
    const width = (extra) => (edge) => (edge.data("width") + extra) / edge.cy().zoom();
    const edges = { width: width(0), hoveredWidth: width(1), opacity: "data(opacity)", faded: 0.12 };
    return [
        ...graphStyle(edges),
        {
            selector: "edge.linked",
            style: { width: width(1), "line-color": color("cited-light"), opacity: 1, "z-index": 5 },
        },
        ...labelRules(fontFamily),
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
    const fontFamily = getComputedStyle(frame.container).fontFamily;
    const nodes = nodeElements(frame.data.nodes);
    const edges = edgeElements(frame.data.edges);
    const cy = createGraph(frame.container, nodes, edges, keywordStyle(fontFamily));
    layOut(cy);
    // Never stretched: the network keeps its distances (#195).
    const bindSelection = bindKeywordSelection(frame.data.publications);
    bindGraph(cy, frame, { bindSelection, uniform: true });
    bindKeywordLabels(cy, fontFamily);
}

render();
