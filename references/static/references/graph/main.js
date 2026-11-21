// Citation graph: publications placed on a timeline (x = publication date), or in a
// network without any time axis (#195), as chosen in the URL (graph_variants.py).
// Entry point, loaded as an ES module after cytoscape.min.js (global `cytoscape`). The
// frame, the view, the selection and the export are those of every graph (graph.js).

import { drawYearAxis } from "./axis.js";
import { bindUndatedBand } from "./band.js";
import { bindGraph, createGraph, graphFrame, LAYOUT_MEASURE } from "./graph.js";
import { placeNodes } from "./layout.js";
import { layOutAside, layOutHere, networkNodes } from "./network.js";
import { makeScale, yearRange } from "./scale.js";
import { bindCitationSelection } from "./selection.js";

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

// The network (#195): no axis, no band. Laid out before it is created: a large graph in a
// Web Worker, the page responding meanwhile (#202); a small one, or if the worker fails, in
// the page.
async function network(container, graph) {
    const nodes = networkNodes(graph.nodes);
    const waiting = container.parentElement.querySelector("[data-graph-waiting]");
    performance.mark(LAYOUT_MEASURE);
    const placed =
        (await layOutAside(nodes, graph.edges, container, waiting)) ?? layOutHere(nodes, graph.edges, container);
    performance.measure(LAYOUT_MEASURE, LAYOUT_MEASURE);
    return createGraph(container, placed, graph.edges);
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
    const { cy, bindAxes } = isNetwork ? { cy: await network(container, graph) } : timeline(container, graph);
    // In the network, distances mean something in both directions: a uniform zoom (#195).
    bindGraph(cy, frame, { bindSelection: bindCitationSelection, uniform: isNetwork, bindAxes });
}

render();
