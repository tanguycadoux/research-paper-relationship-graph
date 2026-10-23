// Citation graph: publications placed on a timeline (x = publication date).
// Entry point, loaded as an ES module after cytoscape.min.js (global `cytoscape`).

import { drawYearAxis } from "./axis.js";
import { bindExport } from "./export.js";
import { bindFocus } from "./focus.js";
import { placeNodes } from "./layout.js";
import { makeScale, yearRange } from "./scale.js";
import { bindInteractions } from "./selection.js";
import { graphStyle } from "./style.js";
import { bindViewport } from "./viewport.js";

function render() {
    const container = document.getElementById("citation-graph");
    const graph = JSON.parse(document.getElementById("citation-graph-data").textContent);
    const years = yearRange(graph.nodes);
    const scale = makeScale(years, graph.nodes.length, container);
    const cy = cytoscape({
        container,
        elements: [...placeNodes(graph.nodes, graph.edges, scale), ...graph.edges],
        style: graphStyle(),
        // Axes are already scaled to the container; bindViewport fits the graph.
        layout: { name: "preset", fit: false },
        autoungrabify: true,
        autounselectify: true,
    });
    const showAllButton = document.querySelector("[data-graph-show-all] button");
    const viewport = bindViewport(cy, container, showAllButton);
    const card = document.getElementById("citation-graph-card");
    bindInteractions(cy, card, bindFocus(cy, card, viewport));
    const axis = document.getElementById("citation-graph-axis");
    const hasUndated = graph.nodes.some((n) => !n.data.date);
    const drawAxis = () => drawYearAxis(axis, cy, years, scale, hasUndated);
    cy.on("viewport", drawAxis);
    drawAxis();
    const legend = document.getElementById("citation-graph-legend");
    bindExport(cy, { axis, legend }, document.querySelector("[data-graph-export]"), viewport);
}

render();
