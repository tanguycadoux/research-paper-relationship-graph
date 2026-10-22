// Selection of a publication (#61): its references and the publications citing it
// stand out, and the information card describes it.

// French plural: 0 and 1 take the singular.
function publications(count) {
    return `${count} publication${count > 1 ? "s" : ""}`;
}

function fillCard(card, data, referenceCount, citingCount) {
    const field = (name) => card.querySelector(`[data-card="${name}"]`);
    const showRow = (name, visible) => {
        card.querySelector(`[data-card-row="${name}"]`).hidden = !visible;
    };
    field("title").textContent = data.label;
    const etAl = data.authorCount > 1 ? " et al." : "";
    field("authors").textContent = data.firstAuthor + etAl;
    showRow("authors", data.authorCount > 0);
    field("year").textContent = data.date ? data.date.slice(0, 4) : "";
    showRow("year", Boolean(data.date));
    const doiLink = field("doi").querySelector("a");
    doiLink.href = `https://doi.org/${data.doi}`;
    doiLink.firstChild.nodeValue = data.doi;
    showRow("doi", Boolean(data.doi));
    field("isbn").textContent = data.isbn;
    showRow("isbn", Boolean(data.isbn));
    field("references").textContent = `cite ${publications(referenceCount)}`;
    field("citing").textContent = `citée par ${publications(citingCount)}`;
    field("cited-by").textContent = `citée par ${publications(data.citedBy)}`;
    card.querySelector("[data-card-link] a").href = data.url;
    card.hidden = false;
}

function clearSelection(cy, card) {
    cy.elements().removeClass("faded selected reference citing");
    card.hidden = true;
}

// An edge goes from the citing publication to the cited one.
function selectNode(cy, node, card) {
    clearSelection(cy, card);
    const references = node.outgoers("edge");
    const citing = node.incomers("edge");
    const kept = node.union(references).union(references.targets());
    cy.elements().not(kept.union(citing).union(citing.sources())).addClass("faded");
    node.addClass("selected");
    references.addClass("reference");
    citing.addClass("citing");
    fillCard(card, node.data(), references.length, citing.length);
}

export function bindInteractions(cy, card) {
    // Hovering a publication shows its title and darkens its edges.
    cy.on("mouseover", "node[url]", (event) => {
        event.target.addClass("hovered");
        event.target.connectedEdges().addClass("hovered");
    });
    cy.on("mouseout", "node[url]", (event) => {
        event.target.removeClass("hovered");
        event.target.connectedEdges().removeClass("hovered");
    });
    cy.on("tap", "node[url]", (event) => selectNode(cy, event.target, card));
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
