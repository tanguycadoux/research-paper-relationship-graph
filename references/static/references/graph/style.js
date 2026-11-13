// Look of the graph (#139, #140). The colours are defined once, as Tailwind theme
// variables in assets/css/source.css (--color-graph-*), shared with the HTML legend.
// The role of a node (source, citing, cited, or other on the graph of the base, #131)
// gives its colour, the colour of cited by default; its number of citations
// in the base gives its size. Sizes are given on the screen (#185): zooming spreads the
// nodes out instead of enlarging them, which separates publications close in date.

const MIN_SIZE = 14;
const MAX_SIZE = 32;

function color(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(`--color-graph-${name}`).trim();
}

// A length in pixels on the screen, whatever the zoom. Cytoscape evaluates it again when
// the style is updated (keepScreenSize in main.js).
function onScreen(pixels) {
    return (element) => pixels / element.cy().zoom();
}

// Width (and length) of an arrowhead on the screen, in pixels (#288).
const ARROW_SIZE = 8;
// Cytoscape sizes an arrowhead from max((13.37 × width)^0.9, 29) × arrow-scale, in graph
// units, and draws its triangle 0.3 times that size wide and long.
const TRIANGLE_RATIO = 0.3;

// The arrow-scale that gives ARROW_SIZE pixels on the screen for an edge of the given
// width on the screen, whatever the zoom (#185).
function arrowScale(edgeWidth) {
    return (element) => {
        const zoom = element.cy().zoom();
        const base = Math.max(((13.37 * edgeWidth) / zoom) ** 0.9, 29);
        return ARROW_SIZE / (TRIANGLE_RATIO * base * zoom);
    };
}

// An edge of the given width and colour on the screen, with an arrowhead of its colour
// on the cited publication: the edge goes from the citing one to the cited one.
function edgeLook(edgeWidth, lineColor) {
    return {
        width: onScreen(edgeWidth),
        "line-color": lineColor,
        "target-arrow-color": lineColor,
        "arrow-scale": arrowScale(edgeWidth),
    };
}

function nodeSize(node) {
    return node.data("size") / node.cy().zoom();
}

// Area proportional to the number of citations: the diameter follows its square root.
export function nodeSizes(nodes) {
    const most = Math.max(1, ...nodes.map((n) => n.data.citedBy));
    return nodes.map((n) => MIN_SIZE + (MAX_SIZE - MIN_SIZE) * Math.sqrt(n.data.citedBy / most));
}

export function graphStyle() {
    return [
        {
            selector: "node",
            style: {
                width: nodeSize,
                height: nodeSize,
                "background-color": color("cited"),
                // A ring of the surface colour separates overlapping nodes.
                "border-width": onScreen(2),
                "border-color": "white",
            },
        },
        { selector: 'node[role = "source"]', style: { "background-color": color("source") } },
        { selector: 'node[role = "citing"]', style: { "background-color": color("citing") } },
        {
            selector: "node.hovered",
            style: {
                label: "data(label)",
                "font-size": onScreen(12),
                color: "#0b0b0b",
                "text-wrap": "wrap",
                "text-max-width": onScreen(300),
                "text-background-color": "white",
                "text-background-opacity": 0.9,
                "z-index": 10,
            },
        },
        // Straight edges, with a small arrowhead on the cited publication (#288): the time
        // axis gives the direction, except for the publications without a date.
        {
            selector: "edge",
            style: {
                ...edgeLook(1.25, color("edge")),
                opacity: 0.85,
                "curve-style": "straight",
                "target-arrow-shape": "triangle",
            },
        },
        {
            selector: "edge.hovered",
            style: { ...edgeLook(2, color("edge-strong")), opacity: 1, "z-index": 5 },
        },
        // Selection (#61): the publication, its references and the publications citing it,
        // each with the colour of its relation; edges in a lighter shade of their nodes.
        { selector: ".faded", style: { opacity: 0.15 } },
        { selector: "node.selected", style: { "border-width": onScreen(3), "border-color": "#0b0b0b" } },
        { selector: "node.reference-node", style: { "background-color": color("cited") } },
        { selector: "node.citing-node", style: { "background-color": color("citing") } },
        {
            selector: "edge.reference",
            style: { ...edgeLook(3, color("cited-light")), opacity: 1, "z-index": 5 },
        },
        {
            selector: "edge.citing",
            style: { ...edgeLook(3, color("citing-light")), opacity: 1, "z-index": 5 },
        },
    ];
}
