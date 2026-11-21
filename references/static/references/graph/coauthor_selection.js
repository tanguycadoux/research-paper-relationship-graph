// Selection of an author in a coauthorship graph (#222): their coauthors and their links
// stand out, the rest fades, and the card of the panel describes them (their name links
// to their page, their publications, their coauthors in this graph and the strongest
// links, and the variants of a node of gathered duplicates, #419). The view zooms on
// them uniformly (focus.js), and goes back on deselection.
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

// A variant of gathered authors (#419): its name, its publications linked to its page,
// and for a logged-in user (the card has the form), a box checked for the merge or the
// distinction (_author_graph_variants.html).
function variantItem(variant, withBox) {
    const item = document.createElement("li");
    item.className = "flex flex-wrap items-center gap-x-2";
    const count = document.createElement("a");
    count.href = variant.url;
    count.textContent = plural(variant.publications, "publication");
    const detail = document.createElement("span");
    detail.className = "text-gray-500";
    detail.append("· ", count);
    if (!withBox) {
        const name = document.createElement("span");
        name.textContent = variant.label;
        item.append(name, detail);
        return item;
    }
    const box = document.createElement("input");
    box.type = "checkbox";
    box.name = "authors";
    box.value = variant.id;
    box.id = `graph-variant-${variant.id}`;
    box.checked = true;
    const label = document.createElement("label");
    label.htmlFor = box.id;
    label.className = "mb-0 font-normal";
    label.textContent = variant.label;
    item.append(box, label, detail);
    return item;
}

function fillVariants(card, variants = []) {
    const withBox = card.querySelector("[data-card-variants-form]") !== null;
    cardField(card, "variants").replaceChildren(
        ...variants.map((variant) => variantItem(variant, withBox)),
    );
    card.querySelector('[data-card-row="variants"]').hidden = variants.length === 0;
}

function fillCard(card, node) {
    const data = node.data();
    fillVariants(card, data.variants);
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
