// Selection of a publication (#61): its references and the publications citing it
// stand out, each with the colour of its relation (nodes and edges), and the compact
// information card beside the graph describes it (#187, #291); the view zooms on them,
// and goes back on deselection (#142). Without a selection, the card says how to select.
// The gestures and the card are those of every graph (card.js).

import { bindSelection, cardField } from "./card.js";

// The level of the publication (#451), and for one of level 1, the link that develops its
// neighbours or reduces them (the query string given by the server, graph.py). Only on
// the graphs with levels (_citation_graph.html).
function fillLevel(card, data) {
    const row = card.querySelector('[data-card-row="level"]');
    if (!row) {
        return;
    }
    row.hidden = !data.level;
    cardField(card, "level").textContent = `Niveau ${data.level}`;
    const toggle = data.toggle !== undefined;
    card.querySelector('[data-card-row="toggle"]').hidden = !toggle;
    for (const [name, shown] of [["develop", !data.expanded], ["reduce", Boolean(data.expanded)]]) {
        const wrapper = cardField(card, name);
        wrapper.hidden = !toggle || !shown;
        wrapper.querySelector("a").href = toggle ? `?${data.toggle}` : "#";
    }
}

// Its references to identify, in the corpus of the user (#452), and the link to identify
// them in series.
function fillToIdentify(card, data) {
    const row = card.querySelector('[data-card-row="identify"]');
    if (!row) {
        return;
    }
    const count = data.toIdentify ?? 0;
    row.hidden = !count;
    cardField(card, "to-identify").textContent = `${count} référence${count > 1 ? "s" : ""} à identifier`;
    cardField(card, "identify").querySelector("a").href = data.identifyUrl ?? "#";
}

function fillCard(card, data, referenceCount, citingCount) {
    const field = (name) => cardField(card, name);
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
    fillLevel(card, data);
    fillToIdentify(card, data);
}

// An edge goes from the citing publication to the cited one. Returns the nodes the view
// zooms on: the publication, its references and the publications citing it.
function selectPublication(node, card) {
    const cy = node.cy();
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
    return kept.union(citing.sources()).nodes();
}

// focus: what bindFocus returns.
export function bindCitationSelection(cy, card, focus) {
    bindSelection(cy, card, focus, {
        selector: "node[url]",
        classes: "faded selected reference citing reference-node citing-node",
        select: selectPublication,
    });
}
