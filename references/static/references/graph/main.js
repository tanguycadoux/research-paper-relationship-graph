// Citation graph: publications placed on a timeline (x = publication date).
// Entry point, loaded as an ES module after cytoscape.min.js (global `cytoscape`).

import { drawYearAxis } from "./axis.js";
import { bindUndatedBand } from "./band.js";
import { bindExport } from "./export.js";
import { bindFocus } from "./focus.js";
import { placeNodes } from "./layout.js";
import { makeScale, yearRange } from "./scale.js";
import { bindInteractions } from "./selection.js";
import { makeStretch } from "./stretch.js";
import { graphStyle } from "./style.js";
import { bindViewport } from "./viewport.js";

function render() {
    const container = document.getElementById("citation-graph");
    const graph = JSON.parse(document.getElementById("citation-graph-data").textContent);
    const years = yearRange(graph.nodes);
    const scale = makeScale(years, graph.nodes.length, container);
    // bandY: the height of the band of the publications without a date, null without any.
    const { elements, bandY } = placeNodes(graph.nodes, graph.edges, scale);
    const cy = cytoscape({
        container,
        elements: [...elements, ...graph.edges],
        style: graphStyle(),
        // Axes are already scaled to the container; bindViewport fits the graph.
        layout: { name: "preset", fit: false },
        autoungrabify: true,
        autounselectify: true,
    });
    const stretch = makeStretch(cy);
    const showAllButton = document.querySelector("[data-graph-show-all] button");
    const viewport = bindViewport(cy, container, showAllButton, stretch);
    const card = document.getElementById("citation-graph-card");
    bindInteractions(cy, card, bindFocus(cy, viewport, stretch));
    const axis = document.getElementById("citation-graph-axis");
    const drawAxis = () => drawYearAxis(axis, cy, years, scale, stretch);
    cy.on("viewport stretch", drawAxis);
    drawAxis();
    const band = document.getElementById("citation-graph-band");
    bindUndatedBand(cy, band, bandY, stretch);
    const legend = document.getElementById("citation-graph-legend");
    bindExport(cy, { axis, band, legend }, document.querySelector("[data-graph-export]"), viewport);
}

render();
