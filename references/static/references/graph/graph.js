// What every graph does around its own nodes and layout (#340): the elements of its frame
// (_graph_frame.html), the creation of the Cytoscape graph, then the view, the selection
// and the export. The entry points (main.js for the citations, coauthors.js for the
// coauthors) only build their elements, lay them out and choose their selection.

import { bindExport } from "./export.js";
import { bindFocus } from "./focus.js";
import { makeStretch } from "./stretch.js";
import { graphStyle } from "./style.js";
import { bindViewport, rendererOptions } from "./viewport.js";

// The time of the layout is measured under this name (performance.measure), for the
// benchmark (docs/banc-graphe.md).
export const LAYOUT_MEASURE = "citation-graph-layout";
// Once the graph is created and bound (performance.mark): the time to show it.
const SHOWN_MARK = "citation-graph-shown";

// The elements of the frame, by the ids and attributes of _graph_frame.html, which the
// benchmark tools read too; data: the nodes and edges given by the server.
export function graphFrame() {
    return {
        container: document.getElementById("citation-graph"),
        data: JSON.parse(document.getElementById("citation-graph-data").textContent),
        card: document.getElementById("citation-graph-card"),
        legend: document.getElementById("citation-graph-legend"),
        showAllButton: document.querySelector("[data-graph-show-all] button"),
        exportCommand: document.querySelector("[data-graph-export]"),
    };
}

export function createGraph(container, nodes, edges, style = graphStyle()) {
    return cytoscape({
        container,
        elements: [...nodes, ...edges],
        style,
        // Positions are given; bindViewport fits the graph.
        layout: { name: "preset", fit: false },
        autoungrabify: true,
        autounselectify: true,
        ...rendererOptions(nodes.length + edges.length),
    });
}

const withoutAxes = () => ({ axis: null, band: null });

// Binds the view, the selection and the export of a created graph, then enables the
// export. bindSelection(cy, card, focus): that of the graph (selection.js,
// coauthor_selection.js). uniform: a zoom without stretch on a selection, in a network.
// bindAxes(stretch): draws the year axis and the band of the timeline, and returns their
// elements for the export. Returns what a new layout of the graph (layout_time.js) and a
// graph developed or reduced without reloading the page (#451, expand.js) need: the view,
// the stretch, the focus and the selection.
export function bindGraph(cy, frame, { bindSelection, uniform, bindAxes = withoutAxes }) {
    // Positions of the layout, kept for the stretch of a selection on the timeline.
    const stretch = makeStretch(cy);
    const viewport = bindViewport(cy, frame.container, frame.showAllButton, stretch);
    const focus = bindFocus(cy, viewport, stretch, { uniform });
    const selection = bindSelection(cy, frame.card, focus);
    const { axis, band } = bindAxes(stretch);
    bindExport(cy, { axis, band, legend: frame.legend }, frame.exportCommand, viewport);
    frame.exportCommand.querySelector("button").disabled = false;
    performance.mark(SHOWN_MARK);
    return { viewport, stretch, focus, selection };
}
