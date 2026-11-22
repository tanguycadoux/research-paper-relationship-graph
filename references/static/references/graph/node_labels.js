// The names of the nodes of a network drawn in the canvas (#418, #468), as on VOSviewer:
// on the map of the keywords, every term whose name fits; on the graphs of the authors,
// the most published only (as the image of the large graphs). The selected node first,
// then the node of the graph (role "source"), then the largest, each only where its name
// covers neither a name already placed nor another node: under the node, else above it,
// on its right or on its left. In the dense centre of a graph of authors, the largest
// would then have no name: there, a name may cover nodes that have none. The map of the
// keywords says how many names are hidden. Zooming in spreads the nodes, whose size stays
// on the screen (#185): more names fit. They are placed again once the view or the
// selection stops changing, never during a motion: the animations keep their pace. The
// exported image has them (it is the canvas); export_labels.js adds its own around them.

// Size of a name on the screen, in pixels, and the room around it.
const FONT_SIZE = 11;
const LINE_HEIGHT = 1.25;
const PADDING = 2;
// Between the node and its name.
const GAP = 2;
// Placed again once the view has not changed for this long, in milliseconds.
const SETTLE_DELAY = 120;
// Where a name may go, in this order: a class of the node (label-below…).
const PLACES = ["below", "above", "right", "left"];

const onScreen = (pixels) => (element) => pixels / element.cy().zoom();
// The margin of a name from its node, away from it (below, right) or back (above, left).
const away = onScreen(GAP + PADDING);
const back = onScreen(-(GAP + PADDING));

// The rules of the names, after those of the graph: only the nodes of class `labelled`,
// placed by their class label-below, label-above, label-right or label-left. field: the
// data written ("label", or "shortLabel": the family name of an author).
export function labelRules(fontFamily, field = "label") {
    return [
        {
            selector: "node.labelled",
            style: {
                label: `data(${field})`,
                "font-family": fontFamily,
                "font-size": onScreen(FONT_SIZE),
                color: "#1f2937",
                "text-background-color": "white",
                "text-background-opacity": 0.75,
                "text-background-padding": onScreen(PADDING),
                "text-background-shape": "roundrectangle",
                "text-events": "no",
                // Above the nodes without a name, which a name may cover (overNodes), and
                // the largest above the others: a name covers no larger node (fitting).
                "z-index": (node) => 10 + node.data("publications"),
            },
        },
        {
            selector: "node.labelled.label-below",
            style: { "text-valign": "bottom", "text-halign": "center", "text-margin-y": away },
        },
        {
            selector: "node.labelled.label-above",
            style: { "text-valign": "top", "text-halign": "center", "text-margin-y": back },
        },
        {
            selector: "node.labelled.label-right",
            style: { "text-valign": "center", "text-halign": "right", "text-margin-x": away },
        },
        {
            selector: "node.labelled.label-left",
            style: { "text-valign": "center", "text-halign": "left", "text-margin-x": back },
        },
    ];
}

function overlaps(a, b) {
    return a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2;
}

// The selected node first, then the node of the graph, then the largest, then by name:
// they keep their name when two would overlap. Faded nodes (outside a selection) have none.
function candidates(cy) {
    return cy
        .nodes()
        .not(".faded")
        .sort(
            (a, b) =>
                Number(b.hasClass("selected")) - Number(a.hasClass("selected")) ||
                Number(b.data("role") === "source") - Number(a.data("role") === "source") ||
                b.data("publications") - a.data("publications") ||
                a.data("label").localeCompare(b.data("label")),
        );
}

const inside = (box, frame) =>
    box.x1 >= 0 && box.x2 <= frame.width && box.y1 >= 0 && box.y2 <= frame.height;

// The box of the name of a node on the screen, at a place around its disc.
function labelBox(disc, width, place) {
    const height = FONT_SIZE * LINE_HEIGHT + 2 * PADDING;
    const outer = width + 2 * PADDING;
    const { x, y, r } = disc;
    if (place === "below" || place === "above") {
        const top = place === "below" ? y + r + GAP : y - r - GAP - height;
        return { x1: x - outer / 2, x2: x + outer / 2, y1: top, y2: top + height };
    }
    const left = place === "right" ? x + r + GAP : x - r - GAP - outer;
    return { x1: left, x2: left + outer, y1: y - height / 2, y2: y + height / 2 };
}

// The disc of each node on the screen, as a box, with its centre and radius.
function discOf(node) {
    const { x, y } = node.renderedPosition();
    const r = node.renderedOuterHeight() / 2;
    return { node, x, y, r, x1: x - r, x2: x + r, y1: y - r, y2: y + r };
}

// The first place where the name of the disc stays in the frame and covers none of the
// obstacles (names, other nodes); null if there is none.
function freePlace(disc, width, frame, obstacles) {
    for (const place of PLACES) {
        const box = labelBox(disc, width, place);
        if (
            inside(box, frame) &&
            !obstacles.some((other) => other.node !== disc.node && overlaps(box, other))
        ) {
            return { box, place };
        }
    }
    return null;
}

// The nodes named, with their place, in the order of candidates: at most `most`.
// width(node): the width of its name in pixels, constant on the screen. overNodes: a
// name that has no free place may cover the other nodes, except those already named:
// it is drawn above the nodes without a name and the smaller named ones.
function fitting(cy, width, { most, overNodes }) {
    const frame = { width: cy.width(), height: cy.height() };
    const nodes = candidates(cy);
    const discs = nodes.map(discOf);
    const placed = [];
    const named = [];
    for (const disc of discs) {
        if (named.length >= most) {
            break;
        }
        const free =
            freePlace(disc, width(disc.node), frame, [...placed, ...discs]) ??
            (overNodes ? freePlace(disc, width(disc.node), frame, [...placed, ...named]) : null);
        if (free) {
            placed.push(free.box);
            named.push({ ...disc, place: free.place });
        }
    }
    return { named, candidates: nodes.length };
}

// Measures each name once: its font does not change with the zoom.
function nameWidths(fontFamily, field) {
    const context = document.createElement("canvas").getContext("2d");
    context.font = `${FONT_SIZE}px ${fontFamily}`;
    const widths = new Map();
    return (node) => {
        if (!widths.has(node.id())) {
            widths.set(node.id(), context.measureText(node.data(field)).width);
        }
        return widths.get(node.id());
    };
}

const PLACE_CLASSES = PLACES.map((place) => `label-${place}`).join(" ");

// The [data-graph-hidden-labels] element of the frame, if the graph has one (the map of
// the keywords): how many nodes have no name, and how to read them (#468).
function sayHidden(hint, hidden) {
    if (!hint) {
        return;
    }
    hint.hidden = hidden === 0;
    const text = hidden > 1 ? hint.dataset.plural : hint.dataset.singular;
    hint.textContent = text.replace("{n}", hidden);
}

// The classes of the names as placed: only those that change, so that a name which stays
// is not drawn again.
function setNames(cy, named) {
    const kept = cy.collection(named.map(({ node }) => node));
    cy.nodes(".labelled").not(kept).removeClass(`labelled ${PLACE_CLASSES}`);
    for (const { node, place } of named) {
        if (!node.hasClass("labelled") || !node.hasClass(`label-${place}`)) {
            node.removeClass(PLACE_CLASSES).addClass(`labelled label-${place}`);
        }
    }
}

// Places the names now, then again whenever the view or the classes of the nodes (a
// selection) have settled. Options: field, the data written; most, the number of names at
// most; overNodes, whether a name may cover the nodes without a name (see fitting).
export function bindNodeLabels(cy, fontFamily, { field = "label", most = Infinity, overNodes = false } = {}) {
    const width = nameWidths(fontFamily, field);
    const options = { most, overNodes };
    const hint = cy.container().parentElement.querySelector("[data-graph-hidden-labels]");
    let placing = false;
    let settle = null;
    const place = () => {
        const { named, candidates: count } = fitting(cy, width, options);
        placing = true;
        cy.batch(() => setNames(cy, named));
        placing = false;
        sayHidden(hint, Math.min(count, most) - named.length);
    };
    const schedule = () => {
        if (placing) {
            return;
        }
        clearTimeout(settle);
        settle = setTimeout(place, SETTLE_DELAY);
    };
    place();
    cy.on("viewport", schedule);
    cy.on("class", "node", schedule);
}
