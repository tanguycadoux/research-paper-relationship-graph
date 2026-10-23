// Citation graph: publications placed on a timeline (x = publication date).
// Entry point, loaded as an ES module after cytoscape.min.js (global `cytoscape`).

import { drawYearAxis } from "./axis.js";
import { placeNodes } from "./layout.js";
import { MARGIN, makeScale, yearRange } from "./scale.js";
import { bindInteractions } from "./selection.js";
import { graphStyle } from "./style.js";

function keepFitted(cy, container) {
    // The container may change size after initialization (page layout, window resize).
    new ResizeObserver(() => {
        cy.resize();
        cy.fit(undefined, MARGIN / 2);
    }).observe(container);
}

// Sizes in the style are divided by the zoom (#185): they are evaluated again when the
// zoom changes, at most once per frame, so that zooming stays smooth on large graphs.
function keepScreenSize(cy) {
    let zoom = cy.zoom();
    let pending = false;
    // The layout has already fitted the graph to the frame.
    cy.style().update();
    cy.on("viewport", () => {
        if (pending || cy.zoom() === zoom) {
            return;
        }
        pending = true;
        requestAnimationFrame(() => {
            pending = false;
            zoom = cy.zoom();
            cy.style().update();
        });
    });
}

function render() {
    const container = document.getElementById("citation-graph");
    const graph = JSON.parse(document.getElementById("citation-graph-data").textContent);
    const years = yearRange(graph.nodes);
    const scale = makeScale(years, graph.nodes.length, container);
    const cy = cytoscape({
        container,
        elements: [...placeNodes(graph.nodes, graph.edges, scale), ...graph.edges],
        style: graphStyle(),
        // Axes are already scaled to the container: fitting only corrects small offsets.
        layout: { name: "preset", fit: true, padding: MARGIN / 2 },
        autoungrabify: true,
        autounselectify: true,
    });
    keepScreenSize(cy);
    bindInteractions(cy, document.getElementById("citation-graph-card"));
    const axis = document.getElementById("citation-graph-axis");
    const hasUndated = graph.nodes.some((n) => !n.data.date);
    const drawAxis = () => drawYearAxis(axis, cy, years, scale, hasUndated);
    cy.on("viewport", drawAxis);
    drawAxis();
    keepFitted(cy, container);
}

render();
