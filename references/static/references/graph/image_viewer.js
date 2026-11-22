// Entry point of the page that browses the image of a large graph (#453,
// graph_image_viewer.html). The SVG, drawn by the server (services/display/graph_images.py),
// is fetched and put in the page, so that it can be zoomed and its nodes lit; the list of
// its nodes comes with it (nodes.json): name, size, page, centre and radius, and the edges.

import { createHighlight } from "./image_highlight.js";
import { createMinimap } from "./image_minimap.js";
import { createNodeList } from "./image_nodes.js";
import { createPointer } from "./image_pointer.js";
import { createSelection } from "./image_selection.js";
import { createView } from "./image_view.js";

const SVG = "http://www.w3.org/2000/svg";
// « Centrer » zooms in to at least the real size of the image.
const CENTRE_UNIT = 1;
const NOUNS = {
    authors: { node: ["auteur", "auteurs"], size: ["publication", "publications"] },
    base: { node: ["publication", "publications"], size: ["citation", "citations"] },
};

const root = document.querySelector("[data-image-viewer]");
if (root) {
    start(root).catch(() => {
        root.querySelector("[data-image-loading]").textContent = "L'image n'a pas pu être chargée.";
    });
}

async function start(root) {
    const [text, list] = await Promise.all([
        fetch(root.dataset.svgUrl).then(checked).then((response) => response.text()),
        fetch(root.dataset.nodesUrl).then(checked).then((response) => response.json()),
    ]);
    const stage = root.querySelector("[data-image-stage]");
    const svg = imported(text);
    const layer = document.createElementNS(SVG, "svg");
    layer.setAttribute("viewBox", svg.getAttribute("viewBox"));
    layer.classList.add("pointer-events-none", "absolute", "inset-0");
    // The input layer over them takes the pointer (image_pointer.js).
    svg.classList.add("pointer-events-none", "absolute", "inset-0");
    stage.append(svg, layer);
    root.querySelector("[data-image-loading]").remove();
    wire(root, svg, layer, list);
}

function checked(response) {
    if (!response.ok) {
        throw new Error(response.statusText);
    }
    return response;
}

// The SVG of the server, parsed apart and put in the page. It is drawn by the server, the
// names escaped; whatever happens, nothing in it runs (no script, no on… attribute).
function imported(text) {
    const parsed = new DOMParser().parseFromString(text, "image/svg+xml").documentElement;
    if (parsed.nodeName !== "svg") {
        throw new Error("Pas une image SVG");
    }
    parsed.querySelectorAll("script, foreignObject").forEach((node) => node.remove());
    return document.importNode(parsed, true);
}

function wire(root, svg, layer, list) {
    const nodes = list.nodes.map(([label, size, url, x, y, r]) => ({ label, size, url, x, y, r }));
    const input = root.querySelector("[data-image-input]");
    const view = createView(input, [svg, layer]);
    const highlight = createHighlight(layer, nodes, list.edges);
    view.onDraw(highlight.rescale);
    highlight.rescale(view.current());
    createMinimap(root.querySelector("[data-image-minimap]"), nodes, view, root.dataset.kind);
    const centre = (index) => {
        highlight.hover(index);
        view.centreOn(nodes[index].x, nodes[index].y, { unit: CENTRE_UNIT });
    };
    const selection = createSelection(root.querySelector("[data-image-selection]"), nodes, {
        hover: highlight.hover,
        centre,
    });
    const rows = createNodeList(root, nodes, {
        nouns: NOUNS[root.dataset.kind] ?? NOUNS.base,
        hover: highlight.hover,
        centre,
        selection,
    });
    selection.onChange((index, on) => {
        highlight.check(index, on);
        rows.render();
    });
    createPointer(input, root.querySelector("[data-image-tooltip]"), nodes, view, {
        hover: (index) => {
            highlight.hover(index);
            rows.reveal(index);
        },
        select: selection.toggle,
    });
    listenButtons(root, view);
}

function listenButtons(root, view) {
    const actions = { in: view.zoomIn, out: view.zoomOut, all: view.showAll };
    for (const box of root.querySelectorAll("[data-image-zoom]")) {
        box.querySelector("button").addEventListener("click", actions[box.dataset.imageZoom]);
    }
}
