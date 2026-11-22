// The distance of each element to the selected node (#472), on every graph: its
// neighbours are at distance 1, theirs at distance 2, and so on up to DISTANCE_LIMIT;
// beyond, the elements fade as before. The lightness of a node says its distance, on the
// curve of the levels (#470, palette.js), its hue its group; a link has the lightness of
// the distance after that of its nearest end. Classes put here, read by style.js:
// `near` and `distance-<d>` on what is shown (nodes and links), `past` or `future` for
// the hue of a citation graph (the relation of the node to the selected one).

// The farthest distance shown: beyond, the elements fade.
export const DISTANCE_LIMIT = 3;

// The classes put here, for clearSelection (card.js): a link can be one step farther than
// the farthest node.
const distanceClasses = Array.from({ length: DISTANCE_LIMIT + 1 }, (_, d) => `distance-${d + 1}`);
export const DISTANCE_CLASSES = ["near", "past", "future", ...distanceClasses].join(" ");

// The distance of an element marked here (node or link), or null.
export function distanceOf(element) {
    for (let d = 1; d <= DISTANCE_LIMIT + 1; d++) {
        if (element.hasClass(`distance-${d}`)) {
            return d;
        }
    }
    return null;
}

// Its hue on a citation graph: past (cited), future (citing), or null (its own group).
export function hueOf(element) {
    if (element.hasClass("past")) {
        return "cited";
    }
    return element.hasClass("future") ? "citing" : null;
}

// Breadth first from root, up to DISTANCE_LIMIT. steps(node, hue): the [edge, node, hue]
// one step away from a node reached with this hue (null on a graph without hue). Returns
// {id: {node, distance, hue}}, the root at distance 0.
export function reach(root, steps) {
    const reached = new Map([[root.id(), { node: root, distance: 0, hue: null }]]);
    let frontier = [root];
    for (let distance = 1; distance <= DISTANCE_LIMIT && frontier.length; distance++) {
        const next = [];
        for (const from of frontier) {
            for (const [, node, hue] of steps(from, reached.get(from.id()).hue)) {
                if (!reached.has(node.id())) {
                    reached.set(node.id(), { node, distance, hue });
                    next.push(node);
                }
            }
        }
        frontier = next;
    }
    return reached;
}

// Any link, either way; no hue: each node keeps that of its group.
export function undirectedSteps(node) {
    return node.connectedEdges().map((edge) => {
        const other = edge.source().same(node) ? edge.target() : edge.source();
        return [edge, other, null];
    });
}

const HUE_CLASS = { cited: "past", citing: "future" };

// A link between two reached nodes: the distance after that of its nearest end, and the
// hue of its farthest end (of its cited end, the target, when both are as far).
function linkMark(edge, reached) {
    const source = reached.get(edge.source().id());
    const target = reached.get(edge.target().id());
    const far = source.distance > target.distance ? source : target;
    return { distance: Math.min(source.distance, target.distance) + 1, hue: far.hue };
}

// Marks what reach() reached and the links between them, fades the rest. edgeClass(hue):
// the class of a link of the selected node on this graph (its width), nearClass(hue):
// that of a node at distance 1 (export_labels.js names them). Returns the nodes at
// distance 1.
export function markDistances(root, reached, { edgeClass, nearClass }) {
    const cy = root.cy();
    const kept = [];
    const neighbours = [];
    cy.batch(() => {
        for (const { node, distance, hue } of reached.values()) {
            kept.push(node);
            if (distance === 0) {
                continue;
            }
            node.addClass(`near distance-${distance}`);
            if (hue) {
                node.addClass(HUE_CLASS[hue]);
            }
            if (distance === 1) {
                node.addClass(nearClass(hue));
                neighbours.push(node);
            }
        }
        for (const { node } of reached.values()) {
            for (const edge of node.connectedEdges()) {
                const ends = [edge.source().id(), edge.target().id()];
                if (edge.hasClass("near") || !ends.every((id) => reached.has(id))) {
                    continue;
                }
                const { distance, hue } = linkMark(edge, reached);
                edge.addClass(`near distance-${distance}`);
                // Only the links of the selected node are widened: the others keep their
                // width and their opacity, the direct links stand out.
                if (distance === 1) {
                    edge.addClass(edgeClass(hue));
                }
                if (hue) {
                    edge.addClass(HUE_CLASS[hue]);
                }
                kept.push(edge);
            }
        }
        cy.elements().not(cy.collection(kept)).addClass("faded");
    });
    return cy.collection(neighbours);
}
