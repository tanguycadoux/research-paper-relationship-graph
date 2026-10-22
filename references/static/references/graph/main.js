// Citation graph: publications placed on a timeline (x = publication date).
// Entry point, loaded as an ES module after cytoscape.min.js (global `cytoscape`).

import { drawYearAxis } from "./axis.js";
import { placeNodes } from "./layout.js";
import { MARGIN, makeScale, yearRange } from "./scale.js";
import { bindInteractions } from "./selection.js";
import { STYLE } from "./style.js";

function keepFitted(cy, container) {
    // The container may change size after initialization (page layout, window resize).
    new ResizeObserver(() => {
        cy.resize();
        cy.fit(undefined, MARGIN / 2);
    }).observe(container);
}

function render() {
    const container = document.getElementById("citation-graph");
    const graph = JSON.parse(document.getElementById("citation-graph-data").textContent);
    const years = yearRange(graph.nodes);
    const scale = makeScale(years, graph.nodes.length, container);
    const cy = cytoscape({
        container,
        elements: [...placeNodes(graph.nodes, graph.edges, scale), ...graph.edges],
        style: STYLE,
        // Axes are already scaled to the container: fitting only corrects small offsets.
        layout: { name: "preset", fit: true, padding: MARGIN / 2 },
        autoungrabify: true,
        autounselectify: true,
    });
    bindInteractions(cy, document.getElementById("citation-graph-card"));
    const axis = document.getElementById("citation-graph-axis");
    const hasUndated = graph.nodes.some((n) => !n.data.date);
    const drawAxis = () => drawYearAxis(axis, cy, years, scale, hasUndated);
    cy.on("viewport", drawAxis);
    drawAxis();
    keepFitted(cy, container);
}

render();
