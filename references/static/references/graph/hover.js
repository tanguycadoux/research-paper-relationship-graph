// Hovering a publication shows its title in an HTML tooltip over the frame, on every graph:
// easier to read than a label drawn in the canvas, which other nodes may cover. On a small
// graph, the edges of the publication are darkened too (class `hovered`, style.js). On a
// large one (#202), any change of class draws the whole canvas again (40 ms at 1 000
// publications, 140 ms at 2 000): the canvas is left as it is.

import { LIVE_SIZES_MAX_ELEMENTS } from "./viewport.js";

// Between the node and the tooltip, and between the tooltip and the edge of the frame, in
// pixels.
const GAP = 6;

// Above the node, or below it when there is no room above; centred on it, within the
// frame of the graph (the Cytoscape container, not the axis above it).
function place(tooltip, node, container) {
    const position = node.renderedPosition();
    const radius = node.renderedOuterHeight() / 2;
    const width = tooltip.offsetWidth;
    const height = tooltip.offsetHeight;
    let top = position.y - radius - GAP - height;
    if (top < GAP) {
        top = position.y + radius + GAP;
    }
    top = Math.min(top, container.clientHeight - height - GAP);
    const left = Math.max(GAP, Math.min(position.x - width / 2, container.clientWidth - width - GAP));
    tooltip.style.left = `${container.offsetLeft + left}px`;
    tooltip.style.top = `${container.offsetTop + top}px`;
}

// The edges of the hovered publication, darkened while the pointer is on it.
function bindEdgeHover(cy) {
    let hovered = cy.collection();
    const clear = () => {
        hovered.removeClass("hovered");
        hovered = cy.collection();
    };
    cy.on("mouseover", "node[url]", (event) => {
        clear();
        hovered = event.target.connectedEdges().addClass("hovered");
    });
    cy.on("mouseout", "node[url]", clear);
    // Cytoscape sends no mouseout when the pointer leaves the frame from the node.
    cy.container().addEventListener("mouseleave", clear);
}

function bindTooltip(cy, tooltip) {
    const container = cy.container();
    const hide = () => {
        tooltip.hidden = true;
    };
    cy.on("mouseover", "node[url]", (event) => {
        // Not while the view is dragged, nor while a button is held down.
        if (event.originalEvent?.buttons) {
            return;
        }
        tooltip.textContent = event.target.data("label");
        tooltip.hidden = false;
        place(tooltip, event.target, container);
    });
    cy.on("mouseout", "node[url]", hide);
    container.addEventListener("mouseleave", hide);
    // A gesture or a selection moves the view: the tooltip would be left behind.
    cy.on("viewport tapstart tap", hide);
}

// The tooltip is the [data-graph-tooltip] element beside the container of the graph.
export function bindHover(cy) {
    const tooltip = cy.container().parentElement.querySelector("[data-graph-tooltip]");
    if (tooltip) {
        bindTooltip(cy, tooltip);
    }
    if (cy.elements().length <= LIVE_SIZES_MAX_ELEMENTS) {
        bindEdgeHover(cy);
    }
}
