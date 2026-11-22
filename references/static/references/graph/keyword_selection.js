// Selection of a term on the map of the keywords (#418): the terms it appears with and
// their links stand out, then theirs, lighter at each step (#472, distance.js), the rest
// fades, and the card of the panel lists its publications (each a link to its page), the
// link to « Mon corpus » filtered on them, and the terms it appears with most often (a
// click selects one). The view zooms on them uniformly (focus.js), and goes back on
// deselection. The gestures, the card and the hover are those of every graph (card.js,
// hover.js): a double click opens « Mon corpus » filtered.

import { bindSelection, cardField } from "./card.js";
import { DISTANCE_CLASSES, markDistances, reach, undirectedSteps } from "./distance.js";

// Terms listed on the card, the most shared first.
const STRONGEST_SHOWN = 5;

const plural = (count, word) => `${count} ${word}${count > 1 ? "s" : ""}`;

// The other end of each link of the node, the most shared first, then by name.
function strongest(node) {
    return node
        .connectedEdges()
        .map((edge) => ({ edge, other: edge.source().same(node) ? edge.target() : edge.source() }))
        .sort(
            (a, b) =>
                b.edge.data("shared") - a.edge.data("shared") ||
                a.other.data("label").localeCompare(b.other.data("label")),
        )
        .slice(0, STRONGEST_SHOWN);
}

// A term it appears with: a button that selects it, and the publications they share.
function strongestItem({ edge, other }) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "cursor-pointer text-left text-blue-700 hover:underline";
    button.textContent = other.data("label");
    // As a tap on the node: card.js selects it and moves the view.
    button.addEventListener("click", () => other.emit("tap"));
    const detail = document.createElement("span");
    detail.className = "text-gray-500";
    detail.textContent = ` · ${plural(edge.data("shared"), "publication")}`;
    item.append(button, detail);
    return item;
}

function publicationItem(publication) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = publication.url;
    link.textContent = publication.label;
    item.append(link);
    if (publication.year) {
        const year = document.createElement("span");
        year.className = "text-gray-500";
        year.textContent = ` · ${publication.year}`;
        item.append(year);
    }
    return item;
}

// The publications of the term, the newest first, then by title.
function publicationsOf(node, publications) {
    return node
        .data("publicationIds")
        .map((id) => publications[id])
        .sort((a, b) => (b.year ?? 0) - (a.year ?? 0) || a.label.localeCompare(b.label));
}

function fillCard(card, node, publications) {
    const data = node.data();
    cardField(card, "title").textContent = data.label;
    cardField(card, "title").href = data.url;
    cardField(card, "detail").textContent = data.detail;
    cardField(card, "detail").hidden = !data.detail;
    const which =
        data.publications > 1 ? `ses ${data.publications} publications` : "sa publication";
    cardField(card, "corpus").textContent = `Ouvrir ${which} dans « Mon corpus »`;
    cardField(card, "corpus").href = data.url;
    const listed = publicationsOf(node, publications).map(publicationItem);
    cardField(card, "publications").replaceChildren(...listed);
    const links = strongest(node);
    cardField(card, "strongest").replaceChildren(...links.map(strongestItem));
    card.querySelector('[data-card-row="strongest"]').hidden = links.length === 0;
}

// publications: {id: {label, year, url}}, given by the server. Returns the select
// function of card.js: it returns the nodes the view zooms on, the term and its
// neighbours (distance 1); theirs, and so on, lighter with the distance (#472).
function selectTerm(publications) {
    return (node, card) => {
        node.addClass("selected");
        const neighbours = markDistances(node, reach(node, undirectedSteps), {
            edgeClass: () => "linked",
            nearClass: () => "linked-node",
        });
        fillCard(card, node, publications);
        return node.union(neighbours);
    };
}

// focus: what bindFocus returns.
export function bindKeywordSelection(publications) {
    return (cy, card, focus) =>
        bindSelection(cy, card, focus, {
            selector: "node",
            classes: `faded selected linked linked-node ${DISTANCE_CLASSES}`,
            select: selectTerm(publications),
        });
}
