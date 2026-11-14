// Selection of an author in a coauthorship graph (#222): their coauthors and their links
// stand out, the rest fades, and the card of the panel describes them (their name links
// to their page, their publications, their coauthors in this graph and the strongest
// links). The view zooms on them uniformly (focus.js), and goes back on deselection.

// Coauthors listed on the card, the strongest links first.
const STRONGEST_SHOWN = 3;

const plural = (count, word) => `${count} ${word}${count > 1 ? "s" : ""}`;

function field(card, name) {
    return card.querySelector(`[data-card="${name}"]`);
}

// The strongest links of the node: its coauthors by weight, then by name.
function strongest(node) {
    return node
        .connectedEdges()
        .map((edge) => ({ edge, other: edge.source().same(node) ? edge.target() : edge.source() }))
        .sort(
            (a, b) =>
                b.edge.data("weight") - a.edge.data("weight") ||
                a.other.data("label").localeCompare(b.other.data("label")),
        )
        .slice(0, STRONGEST_SHOWN);
}

function strongestItem({ edge, other }) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = other.data("url");
    link.textContent = other.data("label");
    const shared = edge.data("shared");
    const detail = document.createElement("span");
    detail.className = "text-gray-500";
    detail.textContent = ` · ${plural(shared, "publication")} en commun`;
    item.append(link, detail);
    return item;
}

function fillCard(card, node) {
    const data = node.data();
    field(card, "title").textContent = data.label;
    field(card, "title").href = data.url;
    field(card, "publications").textContent = `${plural(data.publications, "publication")} dans la base`;
    const coauthors = node.degree();
    field(card, "coauthors").textContent = plural(coauthors, "coauteur");
    const links = strongest(node);
    field(card, "strongest").replaceChildren(...links.map(strongestItem));
    card.querySelector('[data-card-row="strongest"]').hidden = links.length === 0;
    showCard(card, true);
}

// The card keeps its place: its content, or what the graph shows when nothing is selected.
function showCard(card, selected) {
    card.querySelector("[data-card-content]").hidden = !selected;
    card.querySelector("[data-card-empty]").hidden = selected;
}

const SELECTION_CLASSES = "faded selected coauthor coauthor-node";

function clearSelection(cy, card) {
    cy.elements().removeClass(SELECTION_CLASSES);
    showCard(card, false);
}

// focus: what bindFocus returns.
function selectNode(cy, node, card, focus) {
    clearSelection(cy, card);
    const links = node.connectedEdges();
    const coauthors = links.connectedNodes().not(node);
    const kept = node.union(links).union(coauthors);
    cy.elements().not(kept).addClass("faded");
    node.addClass("selected");
    links.addClass("coauthor");
    coauthors.addClass("coauthor-node");
    fillCard(card, node);
    focus.show(node.union(coauthors));
}

function deselect(cy, card, focus) {
    clearSelection(cy, card);
    focus.release();
}

export function bindCoauthorSelection(cy, card, focus) {
    // Hovering an author shows their name and darkens their links.
    cy.on("mouseover", "node", (event) => {
        event.target.addClass("hovered");
        event.target.connectedEdges().addClass("hovered");
    });
    cy.on("mouseout", "node", (event) => {
        event.target.removeClass("hovered");
        event.target.connectedEdges().removeClass("hovered");
    });
    cy.on("tap", "node", (event) => selectNode(cy, event.target, card, focus));
    cy.on("tap", (event) => {
        if (event.target === cy) {
            deselect(cy, card, focus);
        }
    });
    cy.on("dbltap", "node", (event) => {
        window.location.href = event.target.data("url");
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            deselect(cy, card, focus);
        }
    });
    card.querySelector("[data-card-close] button").addEventListener("click", () =>
        deselect(cy, card, focus),
    );
}
