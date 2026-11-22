// The names of some nodes on the exported image (#289), placed where they cover neither
// another label nor, if possible, another node (export.js).

// Labels of the publications, in pixels of the page (twice as many on the image).
const LABEL_FONT_SIZE = 11;
const LABEL_PADDING = 3;
const LABEL_GAP = 4;
// A shortened label keeps at least these first letters.
const MIN_SHORTENED = 4;

// The publications named on the image (#289): with a selection, the selected one and its
// neighbours; otherwise the sources (the publication of the graph, or the corpus). The
// selected publication first, then the most cited: they keep their label when two
// labels would overlap. On a coauthorship graph (#222): the selected author and their
// coauthors, or the author of the graph; the most published first. Those already named
// in the canvas (class `labelled`, node_labels.js, #468) are not named twice.
function labelledNodes(cy) {
    const selected = cy.nodes(".selected");
    const nodes = selected.nonempty()
        ? selected.union(cy.nodes(".reference-node, .citing-node, .coauthor-node"))
        : cy.nodes('[role = "source"]');
    const rank = (node) => node.data("citedBy") ?? node.data("publications");
    return nodes
        .not(".labelled")
        .filter((node) => node.data("shortLabel"))
        .sort(
            (a, b) =>
                Number(b.hasClass("selected")) - Number(a.hasClass("selected")) ||
                rank(b) - rank(a),
        );
}

function overlaps(a, b) {
    return a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2;
}

function box(x1, y1, width, height) {
    return { x1, y1, x2: x1 + width, y2: y1 + height };
}

// Where the label of a node may go, in order: right of the node, left, above, below.
function labelPlaces(x, y, radius, width, height) {
    return [
        box(x + radius + LABEL_GAP, y - height / 2, width, height),
        box(x - radius - LABEL_GAP - width, y - height / 2, width, height),
        box(x - width / 2, y - radius - LABEL_GAP - height, width, height),
        box(x - width / 2, y + radius + LABEL_GAP, width, height),
    ];
}

function inView(nodes, width, height) {
    return nodes.filter((node) => {
        const { x, y } = node.renderedPosition();
        return x >= 0 && x <= width && y >= 0 && y <= height;
    });
}

function discs(nodes) {
    return nodes.map((node) => {
        const { x, y } = node.renderedPosition();
        const radius = node.renderedWidth() / 2;
        return box(x - radius, y - radius, 2 * radius, 2 * radius);
    });
}

// The text cut at a word, or at a letter for a single long word, and ended by « … », so
// that it is at most `room` wide; null if not even its first letters fit.
function shortened(context, text, room) {
    const fits = (candidate) => context.measureText(candidate).width <= room;
    let cut = text;
    while (cut.length > MIN_SHORTENED) {
        const space = cut.lastIndexOf(" ");
        cut = space > MIN_SHORTENED ? cut.slice(0, space) : cut.slice(0, -1);
        cut = cut.replace(/[\s,:;.\-…]+$/u, "");
        if (fits(`${cut}…`)) {
            return `${cut}…`;
        }
    }
    return null;
}

// A label shortened to the room left of the frame beside the node, on its right or else
// on its left (#421): a node near the edge keeps a name rather than none.
function shortenedPlaces(context, text, x, y, radius, frameWidth, height) {
    const right = frameWidth - (x + radius + LABEL_GAP);
    const left = x - radius - LABEL_GAP;
    return [right, left].flatMap((room, side) => {
        const cut = shortened(context, text, room - 2 * LABEL_PADDING);
        if (!cut) {
            return [];
        }
        const width = context.measureText(cut).width + 2 * LABEL_PADDING;
        const x1 = side === 0 ? x + radius + LABEL_GAP : x - radius - LABEL_GAP - width;
        return [{ ...box(x1, y - height / 2, width, height), text: cut }];
    });
}

// The labels placed in the visible graph (width x height, in pixels of the page). Each
// goes in the first place that stays inside and covers no other label nor any node; if
// there is none, in the first that covers no other label nor a labelled node (an
// unlabelled node may then be partly hidden); if there is none either, shortened to the
// room beside the node. A label without such a place is left out: none crosses the edge
// of the image (#421). Nor does any cover a name drawn in the canvas (node_labels.js).
export function placeLabels(context, cy, nodes, width, height) {
    const labelled = inView(nodes, width, height);
    const allDiscs = discs(inView(cy.nodes(), width, height));
    const labelledDiscs = discs(labelled);
    const drawn = cy
        .nodes(".labelled")
        .map((node) => node.renderedBoundingBox({ includeNodes: false, includeOverlays: false }));
    const fits = (candidate, obstacles) =>
        candidate.x1 >= 0 &&
        candidate.x2 <= width &&
        candidate.y1 >= 0 &&
        candidate.y2 <= height &&
        !drawn.some((other) => overlaps(candidate, other)) &&
        !obstacles.some((other) => overlaps(candidate, other));
    const placed = [];
    for (const node of labelled) {
        const text = node.data("shortLabel");
        const { x, y } = node.renderedPosition();
        const radius = node.renderedWidth() / 2;
        const labelWidth = context.measureText(text).width + 2 * LABEL_PADDING;
        const labelHeight = LABEL_FONT_SIZE + 2 * LABEL_PADDING;
        const places = labelPlaces(x, y, radius, labelWidth, labelHeight).map((place) => ({ ...place, text }));
        const place =
            places.find((candidate) => fits(candidate, [...placed, ...allDiscs])) ??
            places.find((candidate) => fits(candidate, [...placed, ...labelledDiscs])) ??
            shortenedPlaces(context, text, x, y, radius, width, labelHeight).find((candidate) =>
                fits(candidate, [...placed, ...labelledDiscs]),
            );
        if (place) {
            placed.push(place);
        }
    }
    return placed;
}

// Each label on a light background, readable over the lines of the graph.
function drawLabels(context, labels, top, color) {
    context.textAlign = "left";
    context.textBaseline = "middle";
    for (const label of labels) {
        context.fillStyle = "rgba(255, 255, 255, 0.85)";
        context.strokeStyle = "rgba(0, 0, 0, 0.15)";
        context.beginPath();
        context.roundRect(label.x1, top + label.y1, label.x2 - label.x1, label.y2 - label.y1, 3);
        context.fill();
        context.stroke();
        context.fillStyle = color;
        // Never wider than its box, whatever the font drawn (#421).
        const room = label.x2 - label.x1 - 2 * LABEL_PADDING;
        context.fillText(label.text, label.x1 + LABEL_PADDING, top + (label.y1 + label.y2) / 2, room);
    }
}

// Draws the labels on the graph drawn at `top` on the image, in the font of the page
// (fontFamily) and the colour of its text.
export function drawNodeLabels(context, cy, { top, fontFamily, color }) {
    context.font = `${LABEL_FONT_SIZE}px ${fontFamily}`;
    const labels = placeLabels(context, cy, labelledNodes(cy), cy.width(), cy.height());
    drawLabels(context, labels, top, color);
}
