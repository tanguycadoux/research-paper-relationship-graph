// Coauthorship graph (#222): the authors, linked by the publications they signed together
// (services/display/author_graph.py), in the network view only (#195). Entry point,
// loaded as an ES module after cytoscape.min.js (global `cytoscape`). The view, the
// uniform zoom on a selection and the export are those of the citation graphs.

import { bindCoauthorSelection } from "./coauthor_selection.js";
import { bindExport } from "./export.js";
import { bindFocus } from "./focus.js";
import { COSE } from "./network.js";
import { makeStretch } from "./stretch.js";
import { graphStyle } from "./style.js";
import { bindViewport, rendererOptions } from "./viewport.js";

// The time of the layout, under the name of the citation graphs (docs/banc-graphe.md).
const LAYOUT_MEASURE = "citation-graph-layout";

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

// Starting positions on a spiral (golden angle), as in network.js: the same graph is laid
// out the same way at each visit, the author of the graph at its centre.
const START_SPACING = 30;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

const lerp = (a, b, t) => a + (b - a) * t;

// A colour of the theme, shared with the legend (--color-graph-*, as in style.js).
function color(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(`--color-graph-${name}`).trim();
}

function nodeElements(nodes) {
    const most = Math.max(1, ...nodes.map((n) => n.data.publications));
    return nodes.map((node, i) => {
        const radius = START_SPACING * Math.sqrt(i);
        const angle = i * GOLDEN_ANGLE;
        const size = lerp(MIN_SIZE, MAX_SIZE, Math.sqrt(node.data.publications / most));
        return {
            data: { ...node.data, size },
            position: { x: radius * Math.cos(angle), y: radius * Math.sin(angle) },
        };
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

// Edges as wide and as dark as their link is strong, on the screen whatever the zoom (#185); the
// rules of style.js for the edges are repeated after it, since a later rule wins.
function coauthorStyle() {
    const width = (extra) => (edge) => (edge.data("width") + extra) / edge.cy().zoom();
    return [
        ...graphStyle(),
        { selector: "edge", style: { width: width(0), opacity: "data(opacity)" } },
        { selector: "edge.hovered", style: { width: width(1), opacity: 1 } },
        { selector: ".faded", style: { opacity: 0.12 } },
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
    const container = document.getElementById("citation-graph");
    const graph = JSON.parse(document.getElementById("citation-graph-data").textContent);
    const nodes = nodeElements(graph.nodes);
    const edges = edgeElements(graph.edges);
    const cy = cytoscape({
        container,
        elements: [...nodes, ...edges],
        style: coauthorStyle(),
        layout: { name: "preset", fit: false },
        autoungrabify: true,
        autounselectify: true,
        ...rendererOptions(nodes.length + edges.length),
    });
    layOut(cy);
    // Never stretched: the network keeps its distances (#195); the view needs it anyway.
    const stretch = makeStretch(cy);
    const showAllButton = document.querySelector("[data-graph-show-all] button");
    const viewport = bindViewport(cy, container, showAllButton, stretch);
    const card = document.getElementById("citation-graph-card");
    bindCoauthorSelection(cy, card, bindFocus(cy, viewport, stretch, { uniform: true }));
    const legend = document.getElementById("citation-graph-legend");
    const page = { axis: null, band: null, legend };
    bindExport(cy, page, document.querySelector("[data-graph-export]"), viewport);
}

render();
