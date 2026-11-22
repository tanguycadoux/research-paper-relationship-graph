// Citation graph: publications placed on a timeline (x = publication date), or in a
// network without any time axis (#195), as chosen in the URL (graph_variants.py).
// Entry point, loaded as an ES module after cytoscape.min.js (global `cytoscape`). The
// frame, the view, the selection and the export are those of every graph (graph.js).
// The layout takes the time of the field « Temps de calcul » (layout_time.js, #323): a
// large graph, or a long time, in a Web Worker (layout_aside.js). The graph is developed
// or reduced without reloading the page (#451, expand.js): each layout also says how to
// lay out another graph, with the same time.

import { drawYearAxis } from "./axis.js";
import { bindUndatedBand } from "./band.js";
import { bindExpansion } from "./expand.js";
import { bindGraph, createGraph, graphFrame, LAYOUT_MEASURE } from "./graph.js";
import { CANCELLED, layOutAside } from "./layout_aside.js";
import { bindLayoutTime, layoutTimeField } from "./layout_time.js";
import { placeNodes } from "./layout.js";
import { networkNodes, networkPositions, placedAt } from "./network.js";
import { blendScale, makeScale, yearRange } from "./scale.js";
import { bindCitationSelection } from "./selection.js";

const frameSize = (container) => ({ width: container.clientWidth, height: container.clientHeight });
const byId = (elements) => new Map(elements.map((element) => [element.data.id, element.position]));

// A layout run again until it is not stopped by a newer one (layout_aside.js): a graph
// developed or reduced needs its positions, even when the time changes meanwhile.
async function untilDone(layOut) {
    let result = CANCELLED;
    while (result === CANCELLED) {
        result = await layOut();
    }
    return result;
}

// The positions of the timeline for a graph, the band of the publications without a date
// included (bandY: its height, null without any), and the years and scale of its axis; or
// CANCELLED. budget: the time given to the layout (milliseconds); waiting(on): shows that it
// runs; always: in the Web Worker whatever the size.
async function placeOnTimeline(container, graph, budget, waiting, always = false) {
    const years = yearRange(graph.nodes);
    const scale = makeScale(years, graph.nodes.length, container);
    const message = { view: "frise", nodes: graph.nodes, edges: graph.edges, years, frame: frameSize(container), budget };
    const reply = await layOutAside(message, waiting, always);
    if (reply === CANCELLED) {
        return reply;
    }
    const placed = reply?.timeline ?? placeNodes(graph.nodes, graph.edges, scale, null, budget);
    return { ...placed, years, scale };
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
// layOut(next): another graph placed (#451); relayout(budget, waiting): the graph shown
// placed in another time, its new positions by id, or CANCELLED.
async function timeline(container, graph, budget, waiting) {
    performance.mark(LAYOUT_MEASURE);
    let axes = await placeOnTimeline(container, graph, budget, waiting);
    performance.measure(LAYOUT_MEASURE, LAYOUT_MEASURE);
    let shown = graph;
    let time = budget;
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
        const to = await untilDone(() => placeOnTimeline(container, next, time, waiting));
        shown = next;
        return {
            elements: to.elements,
            move: (e) => {
                axes = blendAxes(from, to, e);
            },
        };
    };
    const relayout = async (budget, show) => {
        time = budget;
        const result = await placeOnTimeline(container, shown, budget, show, true);
        if (result === CANCELLED) {
            return result;
        }
        axes = result;
        return byId(result.elements);
    };
    return { cy, bindAxes, layOut, relayout };
}

// The network (#195): no axis, no band. Laid out before it is created: a large graph in a
// Web Worker, the page responding meanwhile (#202); a small one, or if the worker fails, in
// the page.
async function network(container, graph, budget, waiting) {
    let shown = graph;
    let time = budget;
    const positionsOf = async (nodes, edges, budget, show, always = false) => {
        const message = { view: "reseau", nodes, edges, frame: frameSize(container), budget };
        const reply = await layOutAside(message, show, always);
        if (reply === CANCELLED) {
            return reply;
        }
        return reply ? new Map(Object.entries(reply.positions)) : networkPositions(nodes, edges, message.frame, budget);
    };
    const nodes = networkNodes(graph.nodes);
    performance.mark(LAYOUT_MEASURE);
    const positions = await positionsOf(nodes, graph.edges, budget, waiting);
    performance.measure(LAYOUT_MEASURE, LAYOUT_MEASURE);
    const cy = createGraph(container, placedAt(nodes, positions), graph.edges);
    // Another graph (#451): cose from the positions start(id) gives, those of the graph
    // shown for its nodes, so that the network changes as little as it can.
    const layOut = async (next, start) => {
        const nodes = networkNodes(next.nodes).map((node) => ({ ...node, position: start(node.data.id) }));
        const positions = await untilDone(() => positionsOf(nodes, next.edges, time, waiting));
        shown = next;
        return { elements: placedAt(nodes, positions), move: () => {} };
    };
    const relayout = (budget, show) => {
        time = budget;
        return positionsOf(networkNodes(shown.nodes), shown.edges, budget, show, true);
    };
    return { cy, layOut, relayout };
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
    const { cy, bindAxes, layOut, relayout } = await lay(container, graph, field.budget, waiting);
    // In the network, distances mean something in both directions: a uniform zoom (#195).
    const bound = bindGraph(cy, frame, { bindSelection: bindCitationSelection, uniform: isNetwork, bindAxes });
    bindExpansion(cy, frame, bound, layOut);
    bindLayoutTime(cy, field, { bound, card: frame.card, relayout });
    selectRequested(cy);
}

render();
