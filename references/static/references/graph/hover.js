// Hovering a publication shows its title. On a small graph, Cytoscape draws it as a label
// and darkens the edges of the publication (classes `hovered`, style.js). On a large one
// (#202), any change of class draws the whole canvas again (40 ms at 1 000 publications,
// 140 ms at 2 000): the title goes in an HTML tooltip over the frame instead, and the
// canvas is left as it is.

import { LIVE_SIZES_MAX_ELEMENTS } from "./viewport.js";

// Between the node and the tooltip, and between the tooltip and the edge of the frame, in
// pixels.
const GAP = 6;

function bindClassHover(cy) {
    cy.on("mouseover", "node[url]", (event) => {
        event.target.addClass("hovered");
        event.target.connectedEdges().addClass("hovered");
    });
    cy.on("mouseout", "node[url]", (event) => {
        event.target.removeClass("hovered");
        event.target.connectedEdges().removeClass("hovered");
    });
}

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

function bindTooltipHover(cy, tooltip) {
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
    // Cytoscape sends no mouseout when the pointer leaves the frame from the node.
    container.addEventListener("mouseleave", hide);
    // A gesture or a selection moves the view: the tooltip would be left behind.
    cy.on("viewport tapstart tap", hide);
}

// The tooltip is the [data-graph-tooltip] element beside the container of the graph.
export function bindHover(cy) {
    const tooltip = cy.container().parentElement.querySelector("[data-graph-tooltip]");
    if (tooltip && cy.elements().length > LIVE_SIZES_MAX_ELEMENTS) {
        bindTooltipHover(cy, tooltip);
    } else {
        bindClassHover(cy);
    }
}
