// Hovering a publication shows its title in an HTML tooltip over the frame, on every graph:
// easier to read than a label drawn in the canvas, which other nodes may cover; under the
// title, its distance (#477): to the selected node, or without a selection its level, its
// distance to the author of the graph… (card.js). Only text: nothing is drawn again. On a small
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

// The lines of the tooltip: the title, or the longer text the graph gives (the variants of
// gathered authors, #419; the references to identify, #452, its last line), its distance
// under the title. Each line is [text, icon]: the distance and the references to identify
// begin with their icon (the [data-tooltip-icon] templates of _graph_frame.html).
function tooltipLines(node, describe) {
    const lines = (node.data("tooltip") ?? node.data("label")).split("\n").map((text) => [text, null]);
    if (node.data("toIdentify") && lines.length > 1) {
        lines[lines.length - 1][1] = "to-identify";
    }
    const distance = describe(node);
    if (distance) {
        lines.splice(1, 0, [distance, "distance"]);
    }
    return lines;
}

function fillTooltip(tooltip, lines, icons) {
    tooltip.replaceChildren(
        ...lines.map(([text, icon]) => {
            const line = document.createElement("div");
            const template = icon && icons.get(icon);
            if (template) {
                line.append(template.content.firstElementChild.cloneNode(true));
            }
            line.append(text);
            return line;
        }),
    );
}

function bindTooltip(cy, tooltip, describe) {
    const container = cy.container();
    const icons = new Map(
        Array.from(container.parentElement.querySelectorAll("[data-tooltip-icon]"), (template) => [
            template.dataset.tooltipIcon,
            template,
        ]),
    );
    const hide = () => {
        tooltip.hidden = true;
    };
    cy.on("mouseover", "node[url]", (event) => {
        // Not while the view is dragged, nor while a button is held down.
        if (event.originalEvent?.buttons) {
            return;
        }
        fillTooltip(tooltip, tooltipLines(event.target, describe), icons);
        tooltip.hidden = false;
        place(tooltip, event.target, container);
    });
    cy.on("mouseout", "node[url]", hide);
    container.addEventListener("mouseleave", hide);
    // A gesture or a selection moves the view: the tooltip would be left behind.
    cy.on("viewport tapstart tap", hide);
}

// The tooltip is the [data-graph-tooltip] element beside the container of the graph.
// describe(node): the distance of the node, or null.
export function bindHover(cy, describe = () => null) {
    const tooltip = cy.container().parentElement.querySelector("[data-graph-tooltip]");
    if (tooltip) {
        bindTooltip(cy, tooltip, describe);
    }
    if (cy.elements().length <= LIVE_SIZES_MAX_ELEMENTS) {
        bindEdgeHover(cy);
    }
}
