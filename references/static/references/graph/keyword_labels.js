// The names of the terms on the map of the keywords (#418), as on VOSviewer: drawn in the
// canvas under their node, the most carried first, each only where it covers no name
// already placed. Zooming in spreads the nodes, whose size stays on the screen (#185):
// more names fit. They are placed again once the view or the selection stops changing,
// never during a motion: the animations keep their pace. The exported image has them too
// (it is the canvas), and nothing more: the nodes have no shortLabel (export_labels.js).

// Size of a name on the screen, in pixels, and the room around it.
const FONT_SIZE = 11;
const LINE_HEIGHT = 1.25;
const PADDING = 2;
// Between the node and its name.
const GAP = 2;
// Placed again once the view has not changed for this long, in milliseconds.
const SETTLE_DELAY = 120;

const onScreen = (pixels) => (element) => pixels / element.cy().zoom();

// The rules of the names, after those of the graph: only the nodes of class `labelled`.
export function labelRules(fontFamily) {
    return [
        {
            selector: "node.labelled",
            style: {
                label: "data(label)",
                "font-family": fontFamily,
                "font-size": onScreen(FONT_SIZE),
                color: "#1f2937",
                "text-valign": "bottom",
                "text-margin-y": onScreen(GAP + PADDING),
                "text-background-color": "white",
                "text-background-opacity": 0.75,
                "text-background-padding": onScreen(PADDING),
                "text-background-shape": "roundrectangle",
                "text-events": "no",
            },
        },
    ];
}

function overlaps(a, b) {
    return a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2;
}

// The selected term first, then the most carried, then by name: they keep their name when
// two would overlap. Faded terms (outside a selection) have none.
function candidates(cy) {
    return cy
        .nodes()
        .not(".faded")
        .sort(
            (a, b) =>
                Number(b.hasClass("selected")) - Number(a.hasClass("selected")) ||
                b.data("publications") - a.data("publications") ||
                a.data("label").localeCompare(b.data("label")),
        );
}

const inside = (box, frame) =>
    box.x1 >= 0 && box.x2 <= frame.width && box.y1 >= 0 && box.y2 <= frame.height;

// The box of the name of a node on the screen, under it; null when the name would be cut
// by the edge of the frame.
function labelBox(node, width, frame) {
    const { x, y } = node.renderedPosition();
    const top = y + node.renderedOuterHeight() / 2 + GAP;
    const height = FONT_SIZE * LINE_HEIGHT + 2 * PADDING;
    const half = width / 2 + PADDING;
    const box = { x1: x - half, x2: x + half, y1: top, y2: top + height };
    return inside(box, frame) ? box : null;
}

// The nodes whose name fits, in the order of candidates. width(node): the width of its
// name in pixels, constant on the screen.
function fitting(cy, width) {
    const frame = { width: cy.width(), height: cy.height() };
    const placed = [];
    const named = [];
    for (const node of candidates(cy)) {
        const box = labelBox(node, width(node), frame);
        if (box && !placed.some((other) => overlaps(box, other))) {
            placed.push(box);
            named.push(node);
        }
    }
    return named;
}

// Measures each name once: its font does not change with the zoom.
function nameWidths(fontFamily) {
    const context = document.createElement("canvas").getContext("2d");
    context.font = `${FONT_SIZE}px ${fontFamily}`;
    const widths = new Map();
    return (node) => {
        if (!widths.has(node.id())) {
            widths.set(node.id(), context.measureText(node.data("label")).width);
        }
        return widths.get(node.id());
    };
}

// Places the names now, then again whenever the view or the classes of the nodes (a
// selection) have settled.
export function bindKeywordLabels(cy, fontFamily) {
    const width = nameWidths(fontFamily);
    let placing = false;
    let settle = null;
    const place = () => {
        const named = cy.collection(fitting(cy, width));
        placing = true;
        cy.batch(() => {
            cy.nodes(".labelled").not(named).removeClass("labelled");
            named.addClass("labelled");
        });
        placing = false;
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
