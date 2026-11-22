// The groups of distance to the selected node, in the panel (#477), on every graph: once a
// node is selected, « Distance 1 : 13 »… up to DISTANCE_LIMIT, then « Au-delà : n », each
// with the dots of its colours. The lightnesses of distances 1 to 3 are too close to tell a
// distance by eye: hovering a group lights its nodes and its links, the rest fades further;
// a click keeps it lit, a second click takes it off. Read from the classes distance.js put
// (`distance-<d>`, `faded`): nothing is computed again. On a large graph, any change of
// class draws the whole canvas again (#202, hover.js): there, only a click lights a group.

import { DISTANCE_LIMIT, distanceOf, hueOf } from "./distance.js";
import { groupColor, nodeGroup } from "./palette.js";

// Up to this many elements, hovering a group lights it. Measured (Chrome headless,
// 1 400 px): the longest frame after lighting a group is 17 ms up to 300 elements, 33 ms
// at 1 384 (the authors of the corpus), 50 ms at 2 406 (the base), 150 ms at 5 287 (the
// graph of P. Ferracin): beyond, sliding along the list would stutter.
const PREVIEW_MAX_ELEMENTS = 2500;

// The classes put here, for clearSelection (card.js).
export const GROUP_CLASSES = "group-lit group-dim";

// The opacity of what a lit group leaves out: below that of a selection (0.12 to 0.15).
const DIMMED = 0.05;
// The order of the dots of a group: the past, the future, the centre, the base.
const HUE_ORDER = ["cited", "citing", "source", "base"];
// The key of the group beyond the limit.
const BEYOND = "beyond";

// After the rules of every graph (coauthors.js and keywords.js add theirs after
// graphStyle): these win.
function addRules(cy) {
    cy.style()
        .selector(".group-dim")
        .style({ opacity: DIMMED })
        .selector(".group-lit")
        .style({ opacity: 1, "z-index": 8 })
        .update();
}

// The nodes at each distance, by colour, and those beyond: [{key, distance, count, hues}].
function groupsOf(cy) {
    const groups = Array.from({ length: DISTANCE_LIMIT }, (_, d) => ({
        key: String(d + 1),
        distance: d + 1,
        count: 0,
        hues: new Set(),
    }));
    const beyond = { key: BEYOND, distance: null, count: 0, hues: new Set() };
    cy.nodes().forEach((node) => {
        const distance = distanceOf(node);
        if (distance) {
            groups[distance - 1].count += 1;
            groups[distance - 1].hues.add(hueOf(node) ?? nodeGroup(node));
        } else if (node.hasClass("faded")) {
            beyond.count += 1;
        }
    });
    return [...groups, beyond];
}

// The elements of a group: its nodes and the links that reach them (distance.js gives a
// link the distance after that of its nearest end); at the limit, the links between two
// of its nodes too. Beyond: what the selection faded.
function membersOf(cy, key) {
    if (key === BEYOND) {
        return cy.elements(".faded");
    }
    const distance = Number(key);
    const members = cy.elements(`.distance-${distance}`);
    return distance === DISTANCE_LIMIT ? members.union(cy.edges(`.distance-${distance + 1}`)) : members;
}

function dot(color) {
    const span = document.createElement("span");
    span.className = "inline-block size-2.5 shrink-0 rounded-full";
    // A colour computed by palette.js: that of the nodes of the graph.
    span.style.backgroundColor = color;
    return span;
}

function dotsOf(group) {
    const box = document.createElement("span");
    box.className = "flex w-8 shrink-0 gap-0.5";
    box.setAttribute("aria-hidden", "true");
    if (group.key === BEYOND) {
        const faded = document.createElement("span");
        faded.className = "inline-block size-2.5 shrink-0 rounded-full border border-gray-300 bg-gray-100";
        box.append(faded);
        return box;
    }
    for (const hue of HUE_ORDER.filter((name) => group.hues.has(name))) {
        box.append(dot(groupColor(hue, group.distance)));
    }
    return box;
}

function groupButton(group) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.distanceGroup = group.key;
    button.setAttribute("aria-pressed", "false");
    button.disabled = group.count === 0;
    button.className =
        "flex w-full cursor-pointer items-center gap-2 rounded px-1.5 py-0.5 text-left text-gray-700 " +
        "hover:bg-gray-100 aria-pressed:bg-gray-200 aria-pressed:font-medium aria-pressed:text-gray-900 " +
        "disabled:cursor-default disabled:text-gray-400 disabled:hover:bg-transparent";
    const name = group.key === BEYOND ? "Au-delà" : `Distance ${group.distance}`;
    const text = document.createElement("span");
    text.textContent = `${name} : ${group.count}`;
    button.append(dotsOf(group), text);
    const item = document.createElement("li");
    item.append(button);
    return item;
}

// box: the [data-distance-groups] element of the card (_graph_frame.html). Returns how to
// show the groups of a selection (once distance.js has marked it) and how to forget them.
export function bindDistanceGroups(cy, box) {
    if (!box) {
        return { show() {}, reset() {} };
    }
    addRules(cy);
    const list = box.querySelector("[data-distance-list]");
    const live = cy.elements().length <= PREVIEW_MAX_ELEMENTS;
    box.querySelector("[data-distance-hint]").textContent = live
        ? "Survolez un groupe pour le voir, cliquez pour le garder."
        : "Cliquez sur un groupe pour le voir, à nouveau pour l'enlever.";
    let root = null;
    let pinned = null;
    let lit = null;

    const light = (key) => {
        if (key === lit) {
            return;
        }
        lit = key;
        cy.batch(() => {
            cy.elements().removeClass(GROUP_CLASSES);
            if (key) {
                const shown = membersOf(cy, key).union(root);
                shown.addClass("group-lit");
                cy.elements().not(shown).addClass("group-dim");
            }
        });
    };
    const press = () => {
        for (const button of list.querySelectorAll("button")) {
            button.setAttribute("aria-pressed", String(button.dataset.distanceGroup === pinned));
        }
    };

    list.addEventListener("click", (event) => {
        const button = event.target.closest("[data-distance-group]");
        if (!button) {
            return;
        }
        const key = button.dataset.distanceGroup;
        pinned = pinned === key ? null : key;
        press();
        light(pinned);
    });
    if (live) {
        const preview = (event) => {
            const button = event.target.closest("[data-distance-group]");
            light(button && !button.disabled ? button.dataset.distanceGroup : pinned);
        };
        list.addEventListener("pointerover", preview);
        list.addEventListener("focusin", preview);
        list.addEventListener("pointerleave", () => light(pinned));
        list.addEventListener("focusout", () => light(pinned));
    }

    return {
        // node: the selected node, which stays lit with every group.
        show(node) {
            root = node;
            pinned = null;
            lit = null;
            list.replaceChildren(...groupsOf(cy).map(groupButton));
        },
        // The classes are taken off with those of the selection (card.js).
        reset() {
            root = null;
            pinned = null;
            lit = null;
            list.replaceChildren();
        },
    };
}
