// Look of the graph (#139, #140). The colours are defined once, as Tailwind theme
// variables in assets/css/source.css (--color-graph-*), shared with the HTML legend.
// The role of a node (source, citing, cited, or other on the graph of the base, #131)
// gives the hue of its colour and its level the lightness (#470, palette.js); its
// number of citations in the base gives its size. Sizes are given on the screen (#185): zooming spreads the
// nodes out instead of enlarging them, which separates publications close in date.

import { cssColor, groupColor, nodeGroup, nodeLevel } from "./palette.js";

const MIN_SIZE = 14;
const MAX_SIZE = 32;

// A colour of the theme, shared with the HTML legend, as Cytoscape reads it (#470).
export function color(name) {
    return cssColor(getComputedStyle(document.documentElement).getPropertyValue(`--color-graph-${name}`).trim());
}

// A length in pixels on the screen, whatever the zoom. Cytoscape evaluates it again when
// the style is updated (keepScreenSize in screen_size.js).
function onScreen(pixels) {
    return (element) => pixels / element.cy().zoom();
}

// The mark of the references to identify (#452): the SVG of the page
// (_graph_warning_icon.html) as an image, or null on a graph without it.
function warningImage() {
    const svg = document.querySelector("[data-graph-warning-icon]");
    if (!svg) {
        return null;
    }
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(svg))}`;
}

// Its size on the screen; its centre on the circle of the node, at 45° top right (#470).
const WARNING_SIZE = 11;

// From the centre of a node to the point of its circle at 45°, on each axis; ring: the
// width of a ring drawn over the mark, which moves it out of it.
function onCircle(ring = 0) {
    return (node) => ((node.data("size") / 2 + ring) * Math.SQRT1_2) / node.cy().zoom();
}
const negative = (length) => (node) => -length(node);

function warningRules() {
    const image = warningImage();
    if (!image) {
        return [];
    }
    return [
        {
            selector: "node[toIdentify > 0]",
            style: {
                "background-image": image,
                "background-image-containment": "over",
                "background-clip": "none",
                "background-fit": "none",
                "background-width": onScreen(WARNING_SIZE),
                "background-height": onScreen(WARNING_SIZE),
                "background-position-x": "50%",
                "background-position-y": "50%",
                "background-offset-x": onCircle(),
                "background-offset-y": negative(onCircle()),
                // Room for the mark, the selection moving it further out: it would be cut.
                "bounds-expansion": onScreen(WARNING_SIZE),
                // Above its neighbours, which would hide the mark.
                "z-index": 1,
            },
        },
        // The dark ring of the selection is drawn over the mark: the mark moves out of it.
        {
            selector: "node.selected[toIdentify > 0]",
            style: {
                "background-offset-x": onCircle(2),
                "background-offset-y": negative(onCircle(2)),
            },
        },
    ];
}

function nodeSize(node) {
    return node.data("size") / node.cy().zoom();
}

// Area proportional to the number of citations: the diameter follows its square root.
export function nodeSizes(nodes) {
    const most = Math.max(1, ...nodes.map((n) => n.data.citedBy));
    return nodes.map((n) => MIN_SIZE + (MAX_SIZE - MIN_SIZE) * Math.sqrt(n.data.citedBy / most));
}

// The edges of the citation graphs: all alike, on the screen whatever the zoom (#185).
// faded: the opacity of what a selection leaves out, nodes and edges.
const CITATION_EDGES = { width: onScreen(1.25), hoveredWidth: onScreen(2), opacity: 0.85, faded: 0.15 };

// The fill and the contour of a node: the hue of its group (its role, or its relation to
// the selected node), the lightness of its level (#470).
const fill = (group) => (node) => groupColor(group ?? nodeGroup(node), nodeLevel(node));
const contour = (group) => (node) => groupColor(group ?? nodeGroup(node), nodeLevel(node), true);

// The nodes: their size, their colour by role and level, and their label when hovered.
function nodeRules() {
    return [
        {
            selector: "node",
            style: {
                width: nodeSize,
                height: nodeSize,
                "background-color": fill(),
                // A contour of the same hue, darker, separates overlapping nodes.
                "border-width": onScreen(2),
                "border-color": contour(),
                // No square halo when a node is clicked: Cytoscape draws one by default.
                "overlay-opacity": 0,
            },
        },
        ...warningRules(),
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
    ];
}

function edgeRules(edges) {
    return [
        // Straight edges: a publication cites older ones, on its left. An edge cannot be
        // clicked or hovered (events: no) nor outlined: the selection goes through the nodes.
        {
            selector: "edge",
            style: {
                events: "no",
                "overlay-opacity": 0,
                width: edges.width,
                "line-color": color("edge"),
                opacity: edges.opacity,
                "curve-style": "straight",
            },
        },
        {
            selector: "edge.hovered",
            style: { width: edges.hoveredWidth, "line-color": color("edge-strong"), opacity: 1, "z-index": 5 },
        },
    ];
}

// A link of the selection (#470): the colour of the group it leads to, at the lightness of
// the level after that of the node at its other end.
export function linkColor(group) {
    return (edge) => {
        const other = edge.source().hasClass("selected") ? edge.target() : edge.source();
        return groupColor(group, nodeLevel(other) + 1);
    };
}

function selectionRules(edges) {
    return [
        // Selection (#61): the publication, its references and the publications citing it,
        // each with the colour of its relation; edges in a lighter shade of their nodes.
        { selector: ".faded", style: { opacity: edges.faded } },
        // The selected publication keeps a dark ring. The soft round halo only shows while
        // the node is pressed (:active), like Cytoscape's own, which is turned off above.
        { selector: "node.selected", style: { "border-width": onScreen(3), "border-color": "#0b0b0b" } },
        {
            selector: "node:active",
            style: {
                "underlay-color": "#0b0b0b",
                "underlay-opacity": 0.12,
                "underlay-padding": onScreen(6),
                "underlay-shape": "ellipse",
            },
        },
        {
            selector: "node.reference-node",
            style: { "background-color": fill("cited"), "border-color": contour("cited") },
        },
        {
            selector: "node.citing-node",
            style: { "background-color": fill("citing"), "border-color": contour("citing") },
        },
        {
            selector: "edge.reference",
            style: { width: onScreen(3), "line-color": linkColor("cited"), opacity: 1, "z-index": 5 },
        },
        {
            selector: "edge.citing",
            style: { width: onScreen(3), "line-color": linkColor("citing"), opacity: 1, "z-index": 5 },
        },
    ];
}

// edges: their width, at rest and hovered, their opacity, and that of the faded elements;
// another graph gives its own (coauthors.js), and adds the rules of its selection after.
export function graphStyle(edges = CITATION_EDGES) {
    return [...nodeRules(), ...edgeRules(edges), ...selectionRules(edges)];
}
