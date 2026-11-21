// The selection and its card, shared by every graph (#340): a tap on a node selects it,
// a double tap opens its page, a tap on the background, Escape or the close button of the
// card deselects. The card beside the graph (_graph_frame.html) keeps its place: it
// describes the selected node, or says what the graph shows when nothing is selected.
// Each graph only says how a node is selected and how the card is filled
// (selection.js for the citations, coauthor_selection.js for the coauthors).

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
    cy.elements().removeClass(classes);
    showCard(card, false);
}

// Binds the selection on the nodes matching `selector`, and the hover (hover.js).
// select(node, card): marks the node and its neighbours with `classes`, fills the card,
// and returns the nodes the view zooms on. focus: what bindFocus returns.
export function bindSelection(cy, card, focus, { selector, classes, select }) {
    const deselect = () => {
        clearSelection(cy, card, classes);
        focus.release();
    };
    bindHover(cy);
    cy.on("tap", selector, (event) => {
        clearSelection(cy, card, classes);
        const shown = select(event.target, card);
        showCard(card, true);
        focus.show(shown);
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
}
