// Citation graph: publications placed on a timeline (x = publication date), or in a
// network without any time axis (#195), as chosen in the URL (graph_variants.py).
// Entry point, loaded as an ES module after cytoscape.min.js (global `cytoscape`). The
// frame, the view, the selection and the export are those of every graph (graph.js). The
// graph is developed or reduced without reloading the page (#451, expand.js): each layout
// also says how to lay out another graph.

import { drawYearAxis } from "./axis.js";
import { bindUndatedBand } from "./band.js";
import { bindExpansion } from "./expand.js";
import { bindGraph, createGraph, graphFrame, LAYOUT_MEASURE } from "./graph.js";
import { placeNodes } from "./layout.js";
import { layOutAgain, layOutAside, layOutNetwork, networkNodes } from "./network.js";
import { blendScale, makeScale, yearRange } from "./scale.js";
import { bindCitationSelection } from "./selection.js";

// The positions of the timeline for a graph, the band of the publications without a date
// included (bandY: its height, null without any), and the years and scale of its axis.
function placeOnTimeline(container, graph) {
    const years = yearRange(graph.nodes);
    const scale = makeScale(years, graph.nodes.length, container);
    return { ...placeNodes(graph.nodes, graph.edges, scale), years, scale };
}

// The axes between two layouts (#451), at eased progress e: the scale in between, the
// years of both, the band at its height in between (where it is when only one has a band).
function blendAxes(from, to, e) {
    if (e >= 1) {
        return to;
    }
    const bands = [from.bandY, to.bandY].filter((y) => y !== null);
    return {
        scale: blendScale(from.scale, to.scale, e),
        years: { min: Math.min(from.years.min, to.years.min), max: Math.max(from.years.max, to.years.max) },
        bandY: bands.length === 2 ? from.bandY + (to.bandY - from.bandY) * e : (bands[0] ?? null),
    };
}

// The timeline: positions computed before the graph is created; the year axis and the
// band of the publications without a date follow the view, and the axes of a new layout.
function timeline(container, graph) {
    performance.mark(LAYOUT_MEASURE);
    let axes = placeOnTimeline(container, graph);
    performance.measure(LAYOUT_MEASURE, LAYOUT_MEASURE);
    const cy = createGraph(container, axes.elements, graph.edges);
    const bindAxes = (stretch) => {
        const axis = document.getElementById("citation-graph-axis");
        const drawAxis = () => drawYearAxis(axis, cy, axes.years, axes.scale, stretch);
        cy.on("viewport stretch", drawAxis);
        drawAxis();
        const band = document.getElementById("citation-graph-band");
        bindUndatedBand(cy, band, () => axes.bandY, stretch);
        return { axis, band };
    };
    // Another graph (#451): its nodes placed, and the axes moving with them.
    const layOut = async (next) => {
        const from = axes;
        const to = placeOnTimeline(container, next);
        return {
            elements: to.elements,
            move: (e) => {
                axes = blendAxes(from, to, e);
            },
        };
    };
    return { cy, bindAxes, layOut };
}

// The network (#195): no axis, no band. cose places the nodes: a large graph in a Web
// Worker before it is created, the page responding meanwhile (#202); a small one, or if the
// worker fails, in the page once it is created.
async function network(container, graph) {
    const nodes = networkNodes(graph.nodes);
    const waiting = container.parentElement.querySelector("[data-graph-waiting]");
    performance.mark(LAYOUT_MEASURE);
    const placed = await layOutAside(nodes, graph.edges, container, waiting);
    let cy;
    if (placed) {
        performance.measure(LAYOUT_MEASURE, LAYOUT_MEASURE);
        cy = createGraph(container, placed, graph.edges);
    } else {
        cy = createGraph(container, nodes, graph.edges);
        performance.mark(LAYOUT_MEASURE);
        layOutNetwork(cy);
        performance.measure(LAYOUT_MEASURE, LAYOUT_MEASURE);
    }
    // Another graph (#451): cose from the positions start(id) gives, those of the graph
    // shown for its nodes, so that the network changes as little as it can.
    const layOut = async (next, start) => {
        const nodes = networkNodes(next.nodes).map((node) => ({ ...node, position: start(node.data.id) }));
        return { elements: await layOutAgain(nodes, next.edges, container, waiting), move: () => {} };
    };
    return { cy, layOut };
}

// The publication just developed or reduced (#451, ?noeud= of graph_levels.py) is
// selected again once the page is loaded: its new neighbours stand out.
function selectRequested(cy) {
    const id = new URLSearchParams(window.location.search).get("noeud");
    const node = id ? cy.getElementById(id) : cy.collection();
    if (node.nonempty()) {
        node.emit("tap");
    }
}

async function render() {
    const frame = graphFrame();
    const { container, data: graph } = frame;
    const layout = JSON.parse(document.getElementById("citation-graph-layout").textContent);
    const isNetwork = layout.vue === "reseau";
    // While the network waits for its Web Worker, the commands have nothing to act on:
    // disabled until bound (bindViewport sets the state of « Vue d'ensemble », bindGraph
    // enables the export).
    frame.showAllButton.disabled = true;
    frame.exportCommand.querySelector("button").disabled = true;
    // The timeline is created at once; the network, without axes, may wait for its Web Worker.
    const { cy, bindAxes, layOut } = isNetwork ? await network(container, graph) : timeline(container, graph);
    // In the network, distances mean something in both directions: a uniform zoom (#195).
    const bound = bindGraph(cy, frame, { bindSelection: bindCitationSelection, uniform: isNetwork, bindAxes });
    bindExpansion(cy, frame, bound, layOut);
    selectRequested(cy);
}

render();
