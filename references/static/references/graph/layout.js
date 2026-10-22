// Positions of the nodes (#138). x is the publication date. The vertical position no
// longer follows the dates: publications that cite each other are brought together,
// in two steps, without any dependency.
//   1. Order: the barycentre method of layered graph drawing.
//   2. Positions: a small vertical simulation from that order.

import { fractionalYear } from "./scale.js";
import { citedByRange, nodeColor } from "./style.js";

// Passes of the barycentre method; the order is stable well before.
const ORDER_PASSES = 20;
const ITERATIONS = 300;
// Pull between two publications that cite each other (share of their gap per step).
const SPRING = 0.02;
// Two publications closer than CLOSE_X in x must be CLOSE_GAP apart in y (pixels), so
// that they do not overlap.
const CLOSE_X = 40;
const CLOSE_GAP = 32;
// A publication keeps EDGE_GAP away from the edges it is not part of, so that no edge
// runs hidden behind a node. The distance is measured across the edge: a steep edge
// needs a larger vertical gap, up to MAX_EDGE_GAP.
const EDGE_GAP = 16;
const MAX_EDGE_GAP = 64;

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

function clearEdges(xs, ys, crossed) {
    for (const [node, a, b, t] of crossed) {
        const edgeY = ys[a] + t * (ys[b] - ys[a]);
        const slope = (ys[b] - ys[a]) / (xs[b] - xs[a]);
        const needed = Math.min(EDGE_GAP * Math.hypot(1, slope), MAX_EDGE_GAP);
        const gap = ys[node] - edgeY;
        if (Math.abs(gap) < needed) {
            ys[node] = edgeY + (gap !== 0 ? Math.sign(gap) : 1) * needed;
        }
    }
}

function separateClose(ys, close, startYs) {
    for (const [a, b] of close) {
        const gap = ys[b] - ys[a];
        const missing = CLOSE_GAP - Math.abs(gap);
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
// never overlap. The result is stretched to the available height, never squeezed: a
// taller graph is shown whole by zooming out.
export function verticalPositions(xs, startYs, links, top, bottom) {
    const ys = [...startYs];
    const close = closePairs(xs);
    const crossed = crossedEdges(xs, links);
    for (let step = 0; step < ITERATIONS; step++) {
        pullLinked(ys, links);
        clearEdges(xs, ys, crossed);
        separateClose(ys, close, startYs);
    }
    const min = Math.min(...ys);
    const span = Math.max(...ys) - min;
    const stretch = span > 0 ? Math.max(1, (bottom - top) / span) : 1;
    const offset = span > 0 ? top : (top + bottom) / 2;
    return ys.map((y) => offset + (y - min) * stretch);
}

export function placeNodes(nodes, edges, scale) {
    const yearOf = (n) => (n.data.date ? fractionalYear(n.data.date) : scale.undatedYear);
    // From the order by date, as before, so that the result is reproducible.
    const byDate = [...nodes].sort((a, b) => yearOf(a) - yearOf(b));
    const links = linkPairs(byDate, edges);
    const rows = barycentreOrder(byDate.length, links);
    const xs = byDate.map((n) => scale.x(yearOf(n)));
    const ys = verticalPositions(
        xs,
        rows.map((row) => scale.y(row)),
        links,
        scale.y(0),
        scale.y(byDate.length - 1),
    );
    const citedRange = citedByRange(nodes);
    return byDate.map((n, i) => ({
        data: { ...n.data, color: nodeColor(n.data, citedRange) },
        position: { x: xs[i], y: ys[i] },
    }));
}
