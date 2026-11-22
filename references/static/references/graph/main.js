// Citation graph: publications placed on a timeline (x = publication date), or in a
// network without any time axis (#195), as chosen in the URL (graph_variants.py).
// Entry point, loaded as an ES module after cytoscape.min.js (global `cytoscape`). The
// frame, the view, the selection and the export are those of every graph (graph.js).
// The layout takes the time of the field « Temps de calcul » (layout_time.js, #323): a
// large graph, or a long time, in a Web Worker (layout_aside.js).

import { drawYearAxis } from "./axis.js";
import { bindUndatedBand } from "./band.js";
import { bindGraph, createGraph, graphFrame, LAYOUT_MEASURE } from "./graph.js";
import { CANCELLED, layOutAside } from "./layout_aside.js";
import { bindLayoutTime, layoutTimeField } from "./layout_time.js";
import { placeNodes } from "./layout.js";
import { networkNodes, networkPositions, placedAt } from "./network.js";
import { makeScale, yearRange } from "./scale.js";
import { bindCitationSelection } from "./selection.js";

const frameSize = (container) => ({ width: container.clientWidth, height: container.clientHeight });
const byId = (elements) => new Map(elements.map((element) => [element.data.id, element.position]));

// The timeline: positions computed before the graph is created; the year axis and the
// band of the publications without a date follow the view. relayout(budget, waiting): the
// new positions by id, or CANCELLED.
async function timeline(container, graph, budget, waiting) {
    performance.mark(LAYOUT_MEASURE);
    const years = yearRange(graph.nodes);
    const scale = makeScale(years, graph.nodes.length, container);
    const layOut = async (time, show, always = false) => {
        const message = { view: "frise", nodes: graph.nodes, edges: graph.edges, years, frame: frameSize(container) };
        const reply = await layOutAside({ ...message, budget: time }, show, always);
        if (reply === CANCELLED) {
            return reply;
        }
        return reply?.timeline ?? placeNodes(graph.nodes, graph.edges, scale, null, time);
    };
    // bandY: the height of the band of the publications without a date, null without any.
    const { elements, bandY } = await layOut(budget, waiting);
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
    const relayout = async (time, show) => {
        const result = await layOut(time, show, true);
        return result === CANCELLED ? result : byId(result.elements);
    };
    return { cy, bindAxes, relayout };
}

// The network (#195): no axis, no band. Laid out before it is created: a large graph in a
// Web Worker, the page responding meanwhile (#202); a small one, or if the worker fails, in
// the page.
async function network(container, graph, budget, waiting) {
    const nodes = networkNodes(graph.nodes);
    const layOut = async (time, show, always = false) => {
        const message = { view: "reseau", nodes, edges: graph.edges, frame: frameSize(container), budget: time };
        const reply = await layOutAside(message, show, always);
        if (reply === CANCELLED) {
            return reply;
        }
        return reply
            ? new Map(Object.entries(reply.positions))
            : networkPositions(nodes, graph.edges, message.frame, time);
    };
    performance.mark(LAYOUT_MEASURE);
    const positions = await layOut(budget, waiting);
    performance.measure(LAYOUT_MEASURE, LAYOUT_MEASURE);
    const cy = createGraph(container, placedAt(nodes, positions), graph.edges);
    return { cy, relayout: (time, show) => layOut(time, show, true) };
}

async function render() {
    const frame = graphFrame();
    const { container, data: graph } = frame;
    const layout = JSON.parse(document.getElementById("citation-graph-layout").textContent);
    const isNetwork = layout.vue === "reseau";
    // While the graph waits for its Web Worker, the commands have nothing to act on:
    // disabled until bound (bindViewport sets the state of « Vue d'ensemble », bindGraph
    // enables the export).
    frame.showAllButton.disabled = true;
    frame.exportCommand.querySelector("button").disabled = true;
    const field = layoutTimeField();
    const message = container.parentElement.querySelector("[data-graph-waiting]");
    const waiting = (on) => {
        message.hidden = !on;
    };
    const lay = isNetwork ? network : timeline;
    const { cy, bindAxes, relayout } = await lay(container, graph, field.budget, waiting);
    // In the network, distances mean something in both directions: a uniform zoom (#195).
    const bound = bindGraph(cy, frame, { bindSelection: bindCitationSelection, uniform: isNetwork, bindAxes });
    bindLayoutTime(cy, field, { bound, card: frame.card, relayout });
}

render();
