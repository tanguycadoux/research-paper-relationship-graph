// The selection and its card, shared by every graph (#340): a tap on a node selects it,
// a double tap opens its page, a tap on the background, Escape or the close button of the
// card deselects. The card beside the graph (_graph_frame.html) keeps its place: it
// describes the selected node, or says what the graph shows when nothing is selected.
// Each graph only says how a node is selected and how the card is filled
// (selection.js for the citations, coauthor_selection.js for the coauthors). Under it,
// the groups of distance to the selected node (#477, distance_groups.js); the tooltip of
// a hovered node gives its distance (hover.js).

import { DISTANCE_LIMIT, distanceOf } from "./distance.js";
import { bindDistanceGroups, GROUP_CLASSES } from "./distance_groups.js";
import { bindHover } from "./hover.js";

// One field of the card: [data-card="name"].
export function cardField(card, name) {
    return card.querySelector(`[data-card="${name}"]`);
}

// The content of the card for a selection, or what the graph shows without one.
export function showCard(card, selected) {
    card.querySelector("[data-card-content]").hidden = !selected;
    card.querySelector("[data-card-empty]").hidden = selected;
}

// classes: the classes a selection puts on the elements, separated by spaces.
export function clearSelection(cy, card, classes) {
    cy.elements().removeClass(`${classes} ${GROUP_CLASSES}`);
    showCard(card, false);
}

// The distance of a hovered node, in its tooltip (#477): to the selected node (the classes
// of distance.js), or without a selection what atRest(node) says (each graph its own).
// Beyond the limit, a node with no path at all to the selection, whatever the direction of
// the links, is said to be in another island: linked(node) tells.
function distanceText(node, selected, atRest, linked) {
    if (!selected) {
        return atRest(node);
    }
    if (node.same(selected)) {
        return null;
    }
    const distance = distanceOf(node);
    if (distance) {
        return `à ${distance} pas de la sélection`;
    }
    if (!linked(node)) {
        return "dans un îlot indépendant, sans lien avec la sélection";
    }
    return `au-delà de ${DISTANCE_LIMIT} pas de la sélection`;
}

// Binds the selection on the nodes matching `selector`, and the hover (hover.js).
// select(node, card): marks the node and its neighbours with `classes`, fills the card,
// and returns the nodes the view zooms on. atRest(node): the distance of a hovered node
// without a selection, or null. focus: what bindFocus returns. Returns the selected node
// (or null), and how to select a node again or clear the selection without moving the
// view: once the graph is developed or reduced (#451, expand.js), which moves it.
export function bindSelection(cy, card, focus, { selector, classes, select, atRest = () => null }) {
    let selected = null;
    // The connected part of the graph holding the selection, found at the first hover that
    // needs it, so that a tap costs no more (a walk of the whole part).
    let island = null;
    const linked = (node) => {
        island ??= selected.component();
        return island.has(node);
    };
    const groups = bindDistanceGroups(cy, card.querySelector("[data-distance-groups]"));
    const clear = () => {
        clearSelection(cy, card, classes);
        groups.reset();
        selected = null;
        island = null;
    };
    const deselect = () => {
        clear();
        focus.release();
    };
    const mark = (node) => {
        clearSelection(cy, card, classes);
        selected = node;
        island = null;
        const shown = select(node, card);
        groups.show(node);
        showCard(card, true);
        return shown;
    };
    bindHover(cy, (node) => distanceText(node, selected, atRest, linked));
    cy.on("tap", selector, (event) => {
        focus.show(mark(event.target));
    });
    cy.on("tap", (event) => {
        if (event.target === cy) {
            deselect();
        }
    });
    cy.on("dbltap", selector, (event) => {
        window.location.href = event.target.data("url");
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            deselect();
        }
    });
    card.querySelector("[data-card-close] button").addEventListener("click", deselect);
    return { selected: () => selected, mark, clear };
}
