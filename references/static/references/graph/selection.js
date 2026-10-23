// Selection of a publication (#61): its references and the publications citing it
// stand out, each with the colour of its relation (nodes and edges), and the compact
// information card describes it (#187); the view moves to show them beside the card (#142).

import { showInFreeArea } from "./focus.js";

function fillCard(card, data, referenceCount, citingCount) {
    const field = (name) => card.querySelector(`[data-card="${name}"]`);
    const showRow = (name, visible) => {
        card.querySelector(`[data-card-row="${name}"]`).hidden = !visible;
    };
    // The title is the link to the page of the publication.
    field("title").textContent = data.label;
    field("title").href = data.url;
    field("venue").textContent = data.venue;
    field("venue").hidden = !data.venue;
    const etAl = data.authorCount > 1 ? " et al." : "";
    field("authors").textContent = data.firstAuthor + etAl;
    showRow("authors", data.authorCount > 0);
    field("year").textContent = data.date ? data.date.slice(0, 4) : "";
    showRow("year", Boolean(data.date));
    field("references").textContent = `cite ${referenceCount}`;
    field("citing").textContent = `citée par ${citingCount}`;
    const citations = data.citedBy;
    field("cited-by").textContent = `${citations} citation${citations > 1 ? "s" : ""} dans la base`;
    card.hidden = false;
}

const SELECTION_CLASSES = "faded selected reference citing reference-node citing-node";

function clearSelection(cy, card) {
    cy.elements().removeClass(SELECTION_CLASSES);
    card.hidden = true;
}

// An edge goes from the citing publication to the cited one.
function selectNode(cy, node, card, allowView) {
    clearSelection(cy, card);
    const references = node.outgoers("edge");
    const citing = node.incomers("edge");
    const kept = node.union(references).union(references.targets());
    cy.elements().not(kept.union(citing).union(citing.sources())).addClass("faded");
    node.addClass("selected");
    references.addClass("reference");
    references.targets().not(node).addClass("reference-node");
    citing.addClass("citing");
    citing.sources().not(node).addClass("citing-node");
    fillCard(card, node.data(), references.length, citing.length);
    showInFreeArea(cy, kept.union(citing.sources()).nodes(), card, allowView);
}

export function bindInteractions(cy, card, allowView) {
    // Hovering a publication shows its title and darkens its edges.
    cy.on("mouseover", "node[url]", (event) => {
        event.target.addClass("hovered");
        event.target.connectedEdges().addClass("hovered");
    });
    cy.on("mouseout", "node[url]", (event) => {
        event.target.removeClass("hovered");
        event.target.connectedEdges().removeClass("hovered");
    });
    cy.on("tap", "node[url]", (event) => selectNode(cy, event.target, card, allowView));
    cy.on("tap", (event) => {
        if (event.target === cy) {
            clearSelection(cy, card);
        }
    });
    cy.on("dbltap", "node[url]", (event) => {
        window.location.href = event.target.data("url");
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            clearSelection(cy, card);
        }
    });
    card.querySelector("[data-card-close] button").addEventListener("click", () =>
        clearSelection(cy, card),
    );
}
