// Selection of a publication (#61): its references and the publications citing it
// stand out, each with the colour of its relation (nodes and edges), then the references
// of its references and the publications citing those that cite it, lighter at each step
// (#472, distance.js); the compact information card beside the graph describes it (#187,
// #291); the view zooms on its neighbours, and goes back on deselection (#142). Without a
// selection, the card says how to select. The gestures and the card are those of every
// graph (card.js).

import { bindSelection, cardField } from "./card.js";
import { DISTANCE_CLASSES, markDistances, reach } from "./distance.js";

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

// Its references to identify (#452), and the link to identify them in series.
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

// The distance follows the citations in the direction of its group only (#472): the
// references of the references (the past), the publications citing those that cite it
// (the future). BOTH_WAYS: every citation, either way, the hue that of the last step.
const BOTH_WAYS = false;

// An edge goes from the citing publication to the cited one: one step to a target is
// towards the past (cited), to a source towards the future (citing).
function citationSteps(node, hue) {
    const past = node.outgoers("edge").map((edge) => [edge, edge.target(), "cited"]);
    const future = node.incomers("edge").map((edge) => [edge, edge.source(), "citing"]);
    if (BOTH_WAYS || !hue) {
        return [...past, ...future];
    }
    return hue === "cited" ? past : future;
}

// Returns the nodes the view zooms on: the publication, its references and the
// publications citing it (distance 1).
function selectPublication(node, card) {
    node.addClass("selected");
    const neighbours = markDistances(node, reach(node, citationSteps), {
        edgeClass: (hue) => (hue === "citing" ? "citing" : "reference"),
        nearClass: (hue) => (hue === "citing" ? "citing-node" : "reference-node"),
    });
    fillCard(card, node.data(), node.outgoers("edge").length, node.incomers("edge").length);
    return node.union(neighbours);
}

// Without a selection, the tooltip gives the distance to the corpus (#477): the level of
// the publication (#451). Nothing for the centre (level 0), nor on the graph of the base,
// whose publications have no level.
function levelText(node) {
    const level = node.data("level");
    return level ? `Niveau ${level}` : null;
}

// focus: what bindFocus returns. Returns what bindSelection returns.
export function bindCitationSelection(cy, card, focus) {
    return bindSelection(cy, card, focus, {
        selector: "node[url]",
        classes: `faded selected reference citing reference-node citing-node ${DISTANCE_CLASSES}`,
        select: selectPublication,
        atRest: levelText,
    });
}
