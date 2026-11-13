// Positions of the nodes (#138). x is the publication date. The vertical position no
// longer follows the dates: publications that cite each other are brought together,
// in two steps, without any dependency.
//   1. Order: the barycentre method of layered graph drawing.
//   2. Positions: a small vertical simulation from that order.

import { fractionalYear } from "./scale.js";
import { nodeSizes } from "./style.js";

// Passes of the barycentre method; the order is stable well before.
const ORDER_PASSES = 20;
const ITERATIONS = 300;
// Pull between two publications that cite each other (share of their gap per step).
const SPRING = 0.02;
// Starting rows are ROW_SPACING apart (pixels), whatever the size of the frame, so that
// the layout does not depend on the window: only the final stretch does.
const ROW_SPACING = 36;
// Two publications closer than CLOSE_X in x keep NODE_SPACING between their edges in y,
// so that they do not overlap (their sizes follow their citations).
const CLOSE_X = 40;
const NODE_SPACING = 12;
// A publication keeps EDGE_SPACING between its edge and the edges it is not part of, so
// that no edge runs hidden behind a node. The distance is measured across the edge: a
// steep edge needs a larger vertical gap, up to MAX_EDGE_GAP.
const EDGE_SPACING = 6;
const MAX_EDGE_GAP = 64;
// Between the lowest dated publication and the band of the undated ones (#288).
export const BAND_GAP = 56;

function linkPairs(nodes, edges) {
    const index = new Map(nodes.map((n, i) => [n.data.id, i]));
    return edges
        .map(({ data }) => [index.get(data.source), index.get(data.target)])
        .filter(([source, target]) => source !== undefined && target !== undefined);
}

// Each publication moves towards the average row of the publications it cites or is
// cited by, then the rows are numbered again. Ties keep the previous order, so the
// result does not depend on chance. Returns the row of each index.
export function barycentreOrder(count, links) {
    const around = Array.from({ length: count }, () => []);
    for (const [a, b] of links) {
        around[a].push(b);
        around[b].push(a);
    }
    let row = Array.from({ length: count }, (_, i) => i);
    for (let pass = 0; pass < ORDER_PASSES; pass++) {
        const target = around.map((others, i) =>
            others.length ? others.reduce((sum, other) => sum + row[other], 0) / others.length : row[i],
        );
        const sorted = row
            .map((_, i) => i)
            .sort((a, b) => target[a] - target[b] || row[a] - row[b]);
        row = new Array(count);
        sorted.forEach((i, position) => {
            row[i] = position;
        });
    }
    return row;
}

// Pairs of publications close in date, found once: x never moves.
function closePairs(xs) {
    const order = xs.map((_, i) => i).sort((a, b) => xs[a] - xs[b]);
    const pairs = [];
    for (let i = 0; i < order.length; i++) {
        for (let j = i + 1; j < order.length && xs[order[j]] - xs[order[i]] < CLOSE_X; j++) {
            pairs.push([order[i], order[j]]);
        }
    }
    return pairs;
}

// Each publication with the edges that pass over its date without touching it, along
// with where it stands between their ends (0 at the source, 1 at the target).
function crossedEdges(xs, links) {
    const crossed = [];
    xs.forEach((x, node) => {
        for (const [a, b] of links) {
            const t = (x - xs[a]) / (xs[b] - xs[a]);
            if (node !== a && node !== b && t > 0 && t < 1) {
                crossed.push([node, a, b, t]);
            }
        }
    });
    return crossed;
}

function pullLinked(ys, links) {
    for (const [a, b] of links) {
        const pull = (ys[b] - ys[a]) * SPRING;
        ys[a] += pull;
        ys[b] -= pull;
    }
}

function clearEdges(xs, ys, crossed, sizes) {
    for (const [node, a, b, t] of crossed) {
        const edgeY = ys[a] + t * (ys[b] - ys[a]);
        const slope = (ys[b] - ys[a]) / (xs[b] - xs[a]);
        const clearance = sizes[node] / 2 + EDGE_SPACING;
        const needed = Math.min(clearance * Math.hypot(1, slope), MAX_EDGE_GAP);
        const gap = ys[node] - edgeY;
        if (Math.abs(gap) < needed) {
            ys[node] = edgeY + (gap !== 0 ? Math.sign(gap) : 1) * needed;
        }
    }
}

function separateClose(ys, close, startYs, sizes) {
    for (const [a, b] of close) {
        const gap = ys[b] - ys[a];
        const missing = (sizes[a] + sizes[b]) / 2 + NODE_SPACING - Math.abs(gap);
        if (missing > 0) {
            // Ties are broken by the starting order, so the result is reproducible.
            const direction = gap !== 0 ? Math.sign(gap) : Math.sign(startYs[b] - startYs[a]) || 1;
            ys[a] -= (direction * missing) / 2;
            ys[b] += (direction * missing) / 2;
        }
    }
}

// Linked publications attract each other; a publication moves away from the edges that
// pass over it; publications close in date push each other apart, last, so that nodes
// never overlap. The result is scaled to the available height, squeezed if needed: nodes
// keep their size on the screen (#185), so zooming out would not separate them either,
// and would lose width; nodes squeezed together are separated by zooming in.
export function verticalPositions(xs, startYs, sizes, links, top, bottom) {
    const ys = [...startYs];
    const close = closePairs(xs);
    const crossed = crossedEdges(xs, links);
    for (let step = 0; step < ITERATIONS; step++) {
        pullLinked(ys, links);
        clearEdges(xs, ys, crossed, sizes);
        separateClose(ys, close, startYs, sizes);
    }
    const min = Math.min(...ys);
    const span = Math.max(...ys) - min;
    const ratio = span > 0 ? (bottom - top) / span : 1;
    const offset = span > 0 ? top : (top + bottom) / 2;
    return ys.map((y) => offset + (y - min) * ratio);
}

// The publications in the order of their date, placed: x is the date, y the result of
// the barycentre order and of the vertical simulation. Sizes are those of all the nodes
// of the graph, so that a node keeps its size whatever the variant.
function placeOnTimeline(nodes, edges, scale, sizeOf, top, bottom) {
    const yearOf = (n) => (n.data.date ? fractionalYear(n.data.date) : scale.undatedYear);
    // From the order by date, as before, so that the result is reproducible.
    const byDate = [...nodes].sort((a, b) => yearOf(a) - yearOf(b));
    const links = linkPairs(byDate, edges);
    const rows = barycentreOrder(byDate.length, links);
    const xs = byDate.map((n) => scale.x(yearOf(n)));
    const sizes = byDate.map(sizeOf);
    const ys = verticalPositions(
        xs,
        rows.map((row) => row * ROW_SPACING),
        sizes,
        links,
        top,
        bottom,
    );
    return byDate.map((n, i) => ({
        data: { ...n.data, size: sizes[i] },
        position: { x: xs[i], y: ys[i] },
    }));
}

// Positions along the band, left to right, so that neighbours keep NODE_SPACING between
// their edges: pushed right from the left end, then back left from the right end if they
// overflow it, then right again if they are too many for the width (the band then
// extends beyond the timeline, on the right).
export function spreadAlong(wanted, sizes, left, right) {
    const order = wanted.map((_, i) => i).sort((a, b) => wanted[a] - wanted[b] || a - b);
    const xs = [...wanted];
    const gap = (a, b) => (sizes[a] + sizes[b]) / 2 + NODE_SPACING;
    const pushRight = () => {
        order.forEach((node, k) => {
            const floor = k === 0 ? left : xs[order[k - 1]] + gap(order[k - 1], node);
            xs[node] = Math.max(xs[node], floor);
        });
    };
    pushRight();
    for (let k = order.length - 1; k >= 0; k--) {
        const node = order[k];
        const ceiling = k === order.length - 1 ? right : xs[order[k + 1]] - gap(node, order[k + 1]);
        xs[node] = Math.min(xs[node], ceiling);
    }
    pushRight();
    return xs;
}

// The publications without a date on a band under the timeline (#288): each near the
// dated publications it cites or that cite it (the average of their x), the others
// spread over the width, in their order. Returns their elements.
function placeOnBand(undated, placed, edges, sizeOf, left, right, bandY) {
    const xOf = new Map(placed.map((element) => [element.data.id, element.position.x]));
    const around = new Map(undated.map((n) => [n.data.id, []]));
    for (const { data } of edges) {
        for (const [own, other] of [[data.source, data.target], [data.target, data.source]]) {
            if (around.has(own) && xOf.has(other)) {
                around.get(own).push(xOf.get(other));
            }
        }
    }
    const alone = undated.filter((n) => around.get(n.data.id).length === 0);
    const step = (right - left) / (alone.length + 1);
    const wanted = undated.map((n) => {
        const xs = around.get(n.data.id);
        return xs.length
            ? xs.reduce((sum, x) => sum + x, 0) / xs.length
            : left + step * (alone.indexOf(n) + 1);
    });
    const sizes = undated.map(sizeOf);
    const xs = spreadAlong(wanted, sizes, left, right);
    return undated.map((n, i) => ({
        data: { ...n.data, size: sizes[i] },
        position: { x: xs[i], y: bandY },
    }));
}

// The elements of the nodes, placed, and the height of the band of the publications
// without a date (null without a band). undatedBand: the variant of #288; without it, or
// without any undated publication, the undated ones are in the column of the timeline.
export function placeNodes(nodes, edges, scale, undatedBand = false) {
    const all = nodeSizes(nodes);
    const sizes = new Map(nodes.map((n, i) => [n.data.id, all[i]]));
    const sizeOf = (n) => sizes.get(n.data.id);
    const undated = undatedBand ? nodes.filter((n) => !n.data.date) : [];
    if (undated.length === 0) {
        const top = scale.y(0);
        const bottom = scale.y(nodes.length - 1);
        return { elements: placeOnTimeline(nodes, edges, scale, sizeOf, top, bottom), bandY: null };
    }
    const dated = nodes.filter((n) => n.data.date);
    const top = scale.y(0);
    const bottom = dated.length > 1 ? scale.y(nodes.length - 1) : top;
    const placed = placeOnTimeline(dated, edges, scale, sizeOf, top, bottom);
    const bandY = bottom + BAND_GAP;
    const left = scale.x(scale.undatedYear);
    const right = Math.max(...placed.map((element) => element.position.x), left);
    const band = placeOnBand(undated, placed, edges, sizeOf, left, right, bandY);
    return { elements: [...placed, ...band], bandY };
}
