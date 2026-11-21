// Selection of an author in a coauthorship graph (#222): their coauthors and their links
// stand out, the rest fades, and the card of the panel describes them (their name links
// to their page, their publications, their coauthors in this graph and the strongest
// links). The view zooms on them uniformly (focus.js), and goes back on deselection.
// The gestures, the card and the hover are those of every graph (card.js, hover.js).

import { bindSelection, cardField } from "./card.js";

// Coauthors listed on the card, the strongest links first.
const STRONGEST_SHOWN = 3;

const plural = (count, word) => `${count} ${word}${count > 1 ? "s" : ""}`;

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
    cardField(card, "title").textContent = data.label;
    cardField(card, "title").href = data.url;
    cardField(card, "publications").textContent = `${plural(data.publications, "publication")} dans la base`;
    const coauthors = node.degree();
    cardField(card, "coauthors").textContent = plural(coauthors, "coauteur");
    const links = strongest(node);
    cardField(card, "strongest").replaceChildren(...links.map(strongestItem));
    card.querySelector('[data-card-row="strongest"]').hidden = links.length === 0;
}

// Returns the nodes the view zooms on: the author and their coauthors.
function selectAuthor(node, card) {
    const links = node.connectedEdges();
    const coauthors = links.connectedNodes().not(node);
    const kept = node.union(links).union(coauthors);
    node.cy().elements().not(kept).addClass("faded");
    node.addClass("selected");
    links.addClass("coauthor");
    coauthors.addClass("coauthor-node");
    fillCard(card, node);
    return node.union(coauthors);
}

// focus: what bindFocus returns.
export function bindCoauthorSelection(cy, card, focus) {
    bindSelection(cy, card, focus, {
        selector: "node",
        classes: "faded selected coauthor coauthor-node",
        select: selectAuthor,
    });
}
