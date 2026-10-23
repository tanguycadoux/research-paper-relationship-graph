// Look of the graph (#139, #140). The colours are defined once, as Tailwind theme
// variables in assets/css/source.css (--color-graph-*), shared with the HTML legend.
// The role of a node (source, citing, cited) gives its colour; its number of citations
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
        // Straight edges, without arrows: a publication cites older ones, on its left.
        {
            selector: "edge",
            style: {
                width: onScreen(1.25),
                "line-color": color("edge"),
                opacity: 0.85,
                "curve-style": "straight",
            },
        },
        {
            selector: "edge.hovered",
            style: { width: onScreen(2), "line-color": color("edge-strong"), opacity: 1, "z-index": 5 },
        },
        // Selection (#61): the publication, its references and the publications citing it,
        // each with the colour of its relation; edges in a lighter shade of their nodes.
        { selector: ".faded", style: { opacity: 0.15 } },
        { selector: "node.selected", style: { "border-width": onScreen(3), "border-color": "#0b0b0b" } },
        { selector: "node.reference-node", style: { "background-color": color("cited") } },
        { selector: "node.citing-node", style: { "background-color": color("citing") } },
        {
            selector: "edge.reference",
            style: { width: onScreen(3), "line-color": color("cited-light"), opacity: 1, "z-index": 5 },
        },
        {
            selector: "edge.citing",
            style: { width: onScreen(3), "line-color": color("citing-light"), opacity: 1, "z-index": 5 },
        },
    ];
}
