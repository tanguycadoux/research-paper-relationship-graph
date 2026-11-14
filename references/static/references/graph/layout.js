// Positions of the nodes (#138). x is the publication date. The vertical position no
// longer follows the dates: publications that cite each other are brought together,
// without any dependency. Each group of publications linked by citations (a connected
// component, #230) is laid out on its own, in two steps:
//   1. Order: the barycentre method of layered graph drawing.
//   2. Positions: a small vertical simulation from that order.
// The groups are then stacked, the largest on top, so that groups without any link
// between them never mix. Publications without any link go on rows under them, and
// those without a date on a band under everything (#288, #318).

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
// The simulation only goes through the publication / edge pairs and the close pairs that
// are near enough to act (#202). Those further than their reach plus REACH_MARGIN are set
// aside until they might come within reach (see stillApart).
const REACH_MARGIN = MAX_EDGE_GAP;
// A large group never quite stops moving: the pairs are looked for again at most every
// REFRESH_EVERY steps, a pair coming within reach in between waits for the next search.
const REFRESH_EVERY = 10;
// Between two stacked groups (#230), in pixels of the frame: not squeezed with the
// groups, but all the gaps together take at most MAX_GAPS_SHARE of the height.
const GROUP_GAP = 32;
const MAX_GAPS_SHARE = 0.25;
// Between the groups and the rows of the publications without any link.
const ROWS_GAP = 40;
// Between the lowest dated publication and the band of the undated ones (#288).
export const BAND_GAP = 56;
// The band of the undated publications has at most MAX_BAND_ROWS rows (#318); beyond,
// the publications are pushed along the rows.
const MAX_BAND_ROWS = 4;

function linkPairs(nodes, edges) {
    const index = new Map(nodes.map((n, i) => [n.data.id, i]));
    return edges
        .map(({ data }) => [index.get(data.source), index.get(data.target)])
        .filter(([source, target]) => source !== undefined && target !== undefined);
}

// Time spent in each step, added to timings[name] when timings is given (the benchmark
// of #202, tools/graph_bench/); otherwise f is just called.
function timed(timings, name, f) {
    if (!timings) {
        return f();
    }
    const start = performance.now();
    const result = f();
    timings[name] = (timings[name] || 0) + performance.now() - start;
    return result;
}

// The groups of publications linked by citations (connected components, #230), each a
// list of nodes in the given order; the largest first, ties in order of appearance.
function components(nodes, edges) {
    const index = new Map(nodes.map((n, i) => [n.data.id, i]));
    const parent = nodes.map((_, i) => i);
    const find = (i) => {
        while (parent[i] !== i) {
            parent[i] = parent[parent[i]];
            i = parent[i];
        }
        return i;
    };
    for (const { data } of edges) {
        const a = index.get(data.source);
        const b = index.get(data.target);
        if (a !== undefined && b !== undefined) {
            parent[find(a)] = find(b);
        }
    }
    const groups = new Map();
    nodes.forEach((node, i) => {
        const root = find(i);
        if (!groups.has(root)) {
            groups.set(root, []);
        }
        groups.get(root).push(node);
    });
    return [...groups.values()].sort((a, b) => b.length - a.length);
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

// Publications are grouped by date, BLOCK_SIZE at a time, to find those near an edge
// without going through all the publications its dates span (#202).
const BLOCK_SIZE = 32;

// Blocks of publications consecutive in x (which never moves): their x range, and their
// publications sorted by y, sorted again at each search (y moves).
function makeBlocks(xs, order) {
    const blocks = [];
    for (let start = 0; start < order.length; start += BLOCK_SIZE) {
        const members = order.slice(start, start + BLOCK_SIZE);
        blocks.push({ left: xs[members[0]], right: xs[members.at(-1)], members, ys: null });
    }
    return blocks;
}

// The first position in a sorted array whose value is at least value.
function firstAtLeast(values, value) {
    let low = 0;
    let high = values.length;
    while (low < high) {
        const middle = (low + high) >> 1;
        if (values[middle] < value) {
            low = middle + 1;
        } else {
            high = middle;
        }
    }
    return low;
}

// The publications that an edge passes over (their date is strictly between the dates of
// its ends) and that are within reach of it in y, with where each stands between the ends
// (0 at the source, 1 at the target). In the order of the publications, then of the
// edges: the order in which the simulation always went through them. In each block of
// dates, only the publications in the band of y that the edge crosses there are looked at.
function nearEdges(xs, ys, links, blocks, reach) {
    for (const block of blocks) {
        block.members.sort((p, q) => ys[p] - ys[q]);
        block.ys = block.members.map((i) => ys[i]);
    }
    const near = [];
    links.forEach(([a, b], link) => {
        const left = Math.min(xs[a], xs[b]);
        const right = Math.max(xs[a], xs[b]);
        if (left === right) {
            return;
        }
        const edgeYAt = (x) => ys[a] + ((x - xs[a]) / (xs[b] - xs[a])) * (ys[b] - ys[a]);
        for (const block of blocks) {
            if (block.right <= left || block.left >= right) {
                continue;
            }
            const y1 = edgeYAt(Math.max(block.left, left));
            const y2 = edgeYAt(Math.min(block.right, right));
            const high = Math.max(y1, y2) + reach;
            for (let k = firstAtLeast(block.ys, Math.min(y1, y2) - reach); k < block.ys.length; k++) {
                if (block.ys[k] > high) {
                    break;
                }
                const node = block.members[k];
                if (node === a || node === b || xs[node] <= left || xs[node] >= right) {
                    continue;
                }
                const t = (xs[node] - xs[a]) / (xs[b] - xs[a]);
                if (Math.abs(ys[node] - edgeYAt(xs[node])) < reach) {
                    near.push([node, a, b, t, link]);
                }
            }
        }
    });
    return near.sort((p, q) => p[0] - q[0] || p[4] - q[4]);
}

// Pairs of publications close in date (x never moves) and within reach of each other in
// y, in the order of their dates.
function nearPairs(xs, ys, order, reach) {
    const pairs = [];
    for (let i = 0; i < order.length; i++) {
        for (let j = i + 1; j < order.length && xs[order[j]] - xs[order[i]] < CLOSE_X; j++) {
            if (Math.abs(ys[order[j]] - ys[order[i]]) < reach) {
                pairs.push([order[i], order[j]]);
            }
        }
    }
    return pairs;
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

// Whether the pairs set aside at the reference positions are still out of reach. The
// whole group mostly contracts, which moves every publication far but brings close ones
// together only slowly: the move since the reference is split into the closest affine
// move (y -> scale * y + shift, least squares) and what remains. A gap g at the reference
// is now at least scale * |g| - 2 * remainder (each end moved by at most the remainder
// besides the affine move), so a pair set aside beyond reach + REACH_MARGIN stays beyond
// reach while scale * (reach + REACH_MARGIN) - 2 * remainder >= reach.
function stillApart(ys, reference, reach) {
    const n = ys.length;
    let meanRef = 0;
    let meanNow = 0;
    for (let i = 0; i < n; i++) {
        meanRef += reference[i] / n;
        meanNow += ys[i] / n;
    }
    let covariance = 0;
    let variance = 0;
    for (let i = 0; i < n; i++) {
        covariance += (reference[i] - meanRef) * (ys[i] - meanNow);
        variance += (reference[i] - meanRef) ** 2;
    }
    const scale = variance > 0 ? covariance / variance : 1;
    let remainder = 0;
    for (let i = 0; i < n; i++) {
        const moved = ys[i] - (meanNow + scale * (reference[i] - meanRef));
        remainder = Math.max(remainder, Math.abs(moved));
    }
    return scale * (reach + REACH_MARGIN) - 2 * remainder >= reach;
}

// Linked publications attract each other; a publication moves away from the edges that
// pass over it; publications close in date push each other apart, last, so that nodes
// never overlap. Only the pairs within reach are gone through (#202): the others would
// not move anything. They are looked for again when one might have come within reach
// (stillApart), at most every REFRESH_EVERY steps. Returns the y of each publication,
// before fitting to the frame.
export function verticalPositions(xs, startYs, sizes, links, timings = null) {
    const ys = [...startYs];
    const order = xs.map((_, i) => i).sort((a, b) => xs[a] - xs[b]);
    const blocks = makeBlocks(xs, order);
    // The largest distance at which a pair still acts: an edge pushes a publication up to
    // MAX_EDGE_GAP away, two close publications push each other up to their size.
    const reach = Math.max(MAX_EDGE_GAP, Math.max(0, ...sizes) + NODE_SPACING);
    let reference = null;
    let searched = -REFRESH_EVERY;
    let crossed = [];
    let close = [];
    for (let step = 0; step < ITERATIONS; step++) {
        timed(timings, "pullLinked", () => pullLinked(ys, links));
        const due = step - searched >= REFRESH_EVERY;
        if (reference === null || (due && !stillApart(ys, reference, reach))) {
            searched = step;
            crossed = timed(timings, "nearEdges", () =>
                nearEdges(xs, ys, links, blocks, reach + REACH_MARGIN),
            );
            close = timed(timings, "nearPairs", () => nearPairs(xs, ys, order, reach + REACH_MARGIN));
            reference = [...ys];
            if (timings) {
                timings.refreshes = (timings.refreshes || 0) + 1;
            }
        }
        timed(timings, "clearEdges", () => clearEdges(xs, ys, crossed, sizes));
        timed(timings, "separateClose", () => separateClose(ys, close, startYs, sizes));
    }
    return ys;
}

// One group of linked publications laid out alone, in the order of their dates: x is the
// date, y the result of the barycentre order and of the vertical simulation, not yet
// fitted to the frame.
function layOutGroup(group, edges, scale, sizeOf, timings) {
    const yearOf = (n) => fractionalYear(n.data.date);
    // From the order by date, as before, so that the result is reproducible.
    const byDate = [...group].sort((a, b) => yearOf(a) - yearOf(b));
    const links = linkPairs(byDate, edges);
    const rows = timed(timings, "barycentreOrder", () => barycentreOrder(byDate.length, links));
    const xs = byDate.map((n) => scale.x(yearOf(n)));
    const sizes = byDate.map(sizeOf);
    const ys = verticalPositions(
        xs,
        rows.map((row) => row * ROW_SPACING),
        sizes,
        links,
        timings,
    );
    return byDate.map((node, i) => ({ node, x: xs[i], y: ys[i], size: sizes[i] }));
}

// The groups stacked from the top, the largest first, together filling the height
// between top and bottom (#230). Their heights share it in proportion, squeezed or
// stretched like a single graph was before: nodes keep their size on the screen (#185),
// so zooming out would not separate them either, and would lose width; nodes squeezed
// together are separated by zooming in. The gaps between groups are not squeezed.
function stackGroups(groups, top, bottom) {
    const height = bottom - top;
    const spans = groups.map((group) => {
        const ys = group.map((p) => p.y);
        return Math.max(...ys) - Math.min(...ys);
    });
    const total = spans.reduce((sum, span) => sum + span, 0);
    const gap =
        groups.length > 1 ? Math.min(GROUP_GAP, (height * MAX_GAPS_SHARE) / (groups.length - 1)) : 0;
    const room = height - gap * (groups.length - 1);
    // Without any height (each group on a single row), the groups are spread evenly.
    const ratio = total > 0 ? room / total : 0;
    const step = total > 0 ? 0 : height / Math.max(groups.length - 1, 1);
    let offset = groups.length === 1 && total === 0 ? (top + bottom) / 2 : top;
    groups.forEach((group, k) => {
        const min = Math.min(...group.map((p) => p.y));
        for (const p of group) {
            p.y = offset + (p.y - min) * ratio;
        }
        offset += spans[k] * ratio + gap + step;
    });
}

// Points along x on rows: each at its wanted x on the first row where it fits (keeping
// NODE_SPACING between edges), else on a new row, up to maxRows; beyond, pushed right
// along the row that ends the furthest left. Returns the x and the row of each.
export function packRows(wanted, sizes, maxRows = Infinity) {
    const order = wanted.map((_, i) => i).sort((a, b) => wanted[a] - wanted[b] || a - b);
    const ends = [];
    const xs = new Array(wanted.length);
    const rows = new Array(wanted.length);
    const after = (row, i) => ends[row].x + (ends[row].size + sizes[i]) / 2 + NODE_SPACING;
    for (const i of order) {
        let row = ends.findIndex((_, r) => after(r, i) <= wanted[i]);
        let x = wanted[i];
        if (row === -1 && ends.length < maxRows) {
            row = ends.length;
        } else if (row === -1) {
            row = ends.reduce((best, _, r) => (after(r, i) < after(best, i) ? r : best), 0);
            x = after(row, i);
        }
        ends[row] = { x, size: sizes[i] };
        xs[i] = x;
        rows[i] = row;
    }
    return { xs, rows };
}

// The midpoint of the extreme values, or null without any.
function middle(xs) {
    return xs.length ? (Math.min(...xs) + Math.max(...xs)) / 2 : null;
}

// Where a publication without a date goes on the band (#288), or null without any dated
// link. A reference is about as old as the other references of the article citing it:
// for each dated publication citing it, the middle of that article's other dated
// references (or the article itself, without any), and the oldest of these middles,
// since a reference is older than every article citing it. A publication is more recent
// than its own references: never before the most recent one it cites, which is also
// where it goes when nothing dated cites it.
function bandX(id, xOf, referencesOf, citersOf) {
    const ownReferences = (referencesOf.get(id) || [])
        .filter((r) => xOf.has(r))
        .map((r) => xOf.get(r));
    const floor = ownReferences.length ? Math.max(...ownReferences) : null;
    const middles = (citersOf.get(id) || [])
        .filter((citer) => xOf.has(citer))
        .map((citer) => {
            const siblings = referencesOf.get(citer).filter((r) => r !== id && xOf.has(r));
            return siblings.length ? middle(siblings.map((r) => xOf.get(r))) : xOf.get(citer);
        });
    if (middles.length === 0) {
        return floor;
    }
    const oldest = Math.min(...middles);
    return floor === null ? oldest : Math.max(oldest, floor);
}

function element(node, x, y, size) {
    return { data: { ...node.data, size }, position: { x, y } };
}

// The height between two rows of points of the given sizes.
function rowPitch(sizes) {
    return Math.max(...sizes) + NODE_SPACING;
}

// The publications without any link, on rows under the groups, at their date.
function placeAlone(alone, scale, sizeOf, rowsTop) {
    const xs = alone.map((n) => scale.x(fractionalYear(n.data.date)));
    const sizes = alone.map(sizeOf);
    const { rows } = packRows(xs, sizes);
    const pitch = rowPitch(sizes);
    return alone.map((n, i) => element(n, xs[i], rowsTop + rows[i] * pitch, sizes[i]));
}

// The publications without a date on a band under the timeline (#288), each placed by
// bandX; those without any dated link are spread over the width, in their order. They
// go on as many rows as they need, up to MAX_BAND_ROWS, each as close as possible to
// where it should be (#318). Returns their elements.
function placeOnBand(undated, placed, edges, sizeOf, left, right, bandY) {
    const xOf = new Map(placed.map((element) => [element.data.id, element.position.x]));
    // An edge goes from the citing publication to the cited one.
    const referencesOf = new Map();
    const citersOf = new Map();
    for (const { data } of edges) {
        if (!referencesOf.has(data.source)) referencesOf.set(data.source, []);
        if (!citersOf.has(data.target)) citersOf.set(data.target, []);
        referencesOf.get(data.source).push(data.target);
        citersOf.get(data.target).push(data.source);
    }
    const wantedX = new Map(
        undated.map((n) => [n.data.id, bandX(n.data.id, xOf, referencesOf, citersOf)]),
    );
    const alone = undated.filter((n) => wantedX.get(n.data.id) === null);
    const step = (right - left) / (alone.length + 1);
    const spread = (n) => left + step * (alone.indexOf(n) + 1);
    const wanted = undated.map((n) => wantedX.get(n.data.id) ?? spread(n));
    const sizes = undated.map(sizeOf);
    const { xs, rows } = packRows(wanted, sizes, MAX_BAND_ROWS);
    const pitch = rowPitch(sizes);
    return undated.map((n, i) => element(n, xs[i], bandY + rows[i] * pitch, sizes[i]));
}

// The elements of the nodes, placed, and the height of the band of the publications
// without a date (null without any). timings: see timed.
export function placeNodes(nodes, edges, scale, timings = null) {
    const all = nodeSizes(nodes);
    const sizes = new Map(nodes.map((n, i) => [n.data.id, all[i]]));
    const sizeOf = (n) => sizes.get(n.data.id);
    const dated = nodes.filter((n) => n.data.date);
    const undated = nodes.filter((n) => !n.data.date);
    const groups = components(dated, edges);
    const linked = groups
        .filter((group) => group.length > 1)
        .map((group) => layOutGroup(group, edges, scale, sizeOf, timings));
    const top = scale.y(0);
    const bottom = linked.length ? scale.y(nodes.length - 1) : top;
    stackGroups(linked, top, bottom);
    const placed = linked.flat().map((p) => element(p.node, p.x, p.y, p.size));
    const alone = groups.filter((group) => group.length === 1).map(([node]) => node);
    if (alone.length) {
        const rowsTop = linked.length ? bottom + ROWS_GAP : top;
        placed.push(...placeAlone(alone, scale, sizeOf, rowsTop));
    }
    if (undated.length === 0) {
        return { elements: placed, bandY: null };
    }
    const lowest = placed.length ? Math.max(...placed.map((e) => e.position.y)) : top;
    const bandY = lowest + BAND_GAP;
    const left = scale.x(scale.start);
    const right = Math.max(...placed.map((e) => e.position.x), left);
    const band = placeOnBand(undated, placed, edges, sizeOf, left, right, bandY);
    return { elements: [...placed, ...band], bandY };
}
