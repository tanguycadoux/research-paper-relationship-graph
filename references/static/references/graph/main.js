// Citation graph: publications placed on a timeline (x = publication date), or in a
// network without any time axis (#195), as chosen in the URL (graph_variants.py).
// Entry point, loaded as an ES module after cytoscape.min.js (global `cytoscape`).

import { drawYearAxis } from "./axis.js";
import { bindUndatedBand } from "./band.js";
import { bindExport } from "./export.js";
import { bindFocus } from "./focus.js";
import { placeNodes } from "./layout.js";
import { layOutAside, layOutNetwork, networkNodes } from "./network.js";
import { makeScale, yearRange } from "./scale.js";
import { bindInteractions } from "./selection.js";
import { makeStretch } from "./stretch.js";
import { graphStyle } from "./style.js";
import { bindViewport, rendererOptions } from "./viewport.js";

// The time of the layout is measured under this name (performance.measure), for the
// benchmark (docs/banc-graphe.md).
const LAYOUT_MEASURE = "citation-graph-layout";
// Once the graph is created and bound (performance.mark): the time to show it.
const SHOWN_MARK = "citation-graph-shown";

function createGraph(container, nodes, edges) {
    return cytoscape({
        container,
        elements: [...nodes, ...edges],
        style: graphStyle(),
        // Positions are given; bindViewport fits the graph.
        layout: { name: "preset", fit: false },
        autoungrabify: true,
        autounselectify: true,
        ...rendererOptions(nodes.length + edges.length),
    });
}

// The timeline: positions computed before the graph is created; the year axis and the
// band of the publications without a date follow the view.
function timeline(container, graph) {
    performance.mark(LAYOUT_MEASURE);
    const years = yearRange(graph.nodes);
    const scale = makeScale(years, graph.nodes.length, container);
    // bandY: the height of the band of the publications without a date, null without any.
    const { elements, bandY } = placeNodes(graph.nodes, graph.edges, scale);
    performance.measure(LAYOUT_MEASURE, LAYOUT_MEASURE);
    const cy = createGraph(container, elements, graph.edges);
    const bindAxes = (stretch) => {
        const axis = document.getElementById("citation-graph-axis");
        const drawAxis = () => drawYearAxis(axis, cy, years, scale, stretch);
        cy.on("viewport stretch", drawAxis);
        drawAxis();
        const band = document.getElementById("citation-graph-band");
        bindUndatedBand(cy, band, bandY, stretch);
        return { axis, band };
    };
    return { cy, bindAxes };
}

// The network (#195): no axis, no band. cose places the nodes: a large graph in a Web
// Worker before it is created, the page responding meanwhile (#202); a small one, or if the
// worker fails, in the page once it is created.
async function network(container, graph) {
    const nodes = networkNodes(graph.nodes);
    const waiting = container.parentElement.querySelector("[data-graph-waiting]");
    const withoutAxes = (cy) => ({ cy, bindAxes: () => ({ axis: null, band: null }) });
    performance.mark(LAYOUT_MEASURE);
    const placed = await layOutAside(nodes, graph.edges, container, waiting);
    if (placed) {
        performance.measure(LAYOUT_MEASURE, LAYOUT_MEASURE);
        return withoutAxes(createGraph(container, placed, graph.edges));
    }
    const cy = createGraph(container, nodes, graph.edges);
    performance.mark(LAYOUT_MEASURE);
    layOutNetwork(cy);
    performance.measure(LAYOUT_MEASURE, LAYOUT_MEASURE);
    return withoutAxes(cy);
}

async function render() {
    const container = document.getElementById("citation-graph");
    const graph = JSON.parse(document.getElementById("citation-graph-data").textContent);
    const layout = JSON.parse(document.getElementById("citation-graph-layout").textContent);
    const isNetwork = layout.vue === "reseau";
    // While the network waits for its Web Worker, the commands have nothing to act on:
    // disabled until bound (bindViewport sets the state of « Vue d'ensemble »).
    const exportButton = document.querySelector("[data-graph-export] button");
    const showAllButton = document.querySelector("[data-graph-show-all] button");
    showAllButton.disabled = true;
    exportButton.disabled = true;
    // The timeline is created at once; the network may wait for its Web Worker.
    const { cy, bindAxes } = isNetwork ? await network(container, graph) : timeline(container, graph);
    // Positions of the layout, kept for the stretch of a selection on the timeline.
    const stretch = makeStretch(cy);
    const viewport = bindViewport(cy, container, showAllButton, stretch);
    const card = document.getElementById("citation-graph-card");
    // In the network, distances mean something in both directions: a uniform zoom (#195).
    bindInteractions(cy, card, bindFocus(cy, viewport, stretch, { uniform: isNetwork }));
    const { axis, band } = bindAxes(stretch);
    const legend = document.getElementById("citation-graph-legend");
    bindExport(cy, { axis, band, legend }, document.querySelector("[data-graph-export]"), viewport);
    exportButton.disabled = false;
    performance.mark(SHOWN_MARK);
}

render();
