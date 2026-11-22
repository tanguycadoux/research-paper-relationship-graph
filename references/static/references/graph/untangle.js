// Fewer crossings on the timeline (#323): after the vertical simulation of a group
// (layout.js), two publications close in the vertical order exchange their heights when
// fewer edges cross that way, as in the drawing of a layered graph. Each takes its leaves
// (publications linked to it alone) along, so that its fan stays together. x never moves.

// Each publication is compared with the next WINDOW ones from the top.
const WINDOW = 8;
// At most this many passes over the group: the result is stable well before.
const PASSES = 6;

// Whether the links e and f (indices in tangle.from and tangle.to) cross at the heights
// ys: the ends of each strictly on either side of the other (sharing an end is not
// crossing).
function crossAt(tangle, e, f, ys) {
    const { from, to, xs } = tangle;
    const a = from[e];
    const b = to[e];
    const c = from[f];
    const d = to[f];
    if (a === c || a === d || b === c || b === d) {
        return false;
    }
    // Cheap first: one link entirely above the other.
    if (Math.max(ys[a], ys[b]) < Math.min(ys[c], ys[d]) || Math.max(ys[c], ys[d]) < Math.min(ys[a], ys[b])) {
        return false;
    }
    const dx = xs[b] - xs[a];
    const dy = ys[b] - ys[a];
    const sideC = dx * (ys[c] - ys[a]) - dy * (xs[c] - xs[a]);
    const sideD = dx * (ys[d] - ys[a]) - dy * (xs[d] - xs[a]);
    if (!(sideC * sideD < 0)) {
        return false;
    }
    const ex = xs[d] - xs[c];
    const ey = ys[d] - ys[c];
    return (ex * (ys[a] - ys[c]) - ey * (xs[a] - xs[c])) * (ex * (ys[b] - ys[c]) - ey * (xs[b] - xs[c])) < 0;
}

// For each link, the links that span part of the same dates: the only ones it may cross,
// since x never moves.
function overlapping(links, xs) {
    const left = links.map(([a, b]) => Math.min(xs[a], xs[b]));
    const right = links.map(([a, b]) => Math.max(xs[a], xs[b]));
    return links.map((_, e) =>
        links.map((_, f) => f).filter((f) => f !== e && left[f] < right[e] && left[e] < right[f]),
    );
}

// The crossing pairs of links [e, f], each once, between the links touched and all the
// links; stops past limit pairs.
function crossingPairs(touched, tangle, ys, limit = Infinity) {
    const pairs = [];
    for (const e of touched) {
        for (const f of tangle.overlaps[e]) {
            if (!(f < e && touched.includes(f)) && crossAt(tangle, e, f, ys)) {
                pairs.push([e, f]);
                if (pairs.length > limit) {
                    return pairs;
                }
            }
        }
    }
    return pairs;
}

// Adds step to the number of crossings of each link of the pairs.
function count(tangle, pairs, step) {
    for (const [e, f] of pairs) {
        tangle.crossings[e] += step;
        tangle.crossings[f] += step;
    }
}

// Moves i by sign * dy and j the other way, each with its leaves.
function shift(i, j, sign, dy, tangle, ys) {
    for (const k of [i, ...tangle.leaves[i]]) {
        ys[k] += sign * dy;
    }
    for (const k of [j, ...tangle.leaves[j]]) {
        ys[k] -= sign * dy;
    }
}

// The links of i and j: those an exchange moves (the link of a leaf is one of its hub).
function moved(i, j, tangle) {
    return [...new Set([...tangle.around[i], ...tangle.around[j]])];
}

// Exchanges the heights of i and j, with their leaves, if fewer links cross then; whether
// they were. Skipped when none of their links crosses any other, or when one is a leaf
// of the other.
function trySwap(i, j, tangle, ys) {
    if (tangle.leaves[i].includes(j) || tangle.leaves[j].includes(i)) {
        return false;
    }
    const touched = moved(i, j, tangle);
    if (!touched.some((e) => tangle.crossings[e] > 0)) {
        return false;
    }
    const before = crossingPairs(touched, tangle, ys);
    const dy = ys[j] - ys[i];
    shift(i, j, 1, dy, tangle, ys);
    const after = crossingPairs(touched, tangle, ys, before.length - 1);
    if (after.length < before.length) {
        count(tangle, before, -1);
        count(tangle, after, 1);
        return true;
    }
    shift(i, j, -1, dy, tangle, ys);
    return false;
}

// One pass from the top: each publication against the next WINDOW ones. Whether any pair
// was exchanged. order: the publications from the top, kept so.
function untanglePass(order, tangle, ys) {
    let changed = false;
    for (let k = 0; k < order.length; k++) {
        for (let d = 1; d <= WINDOW && k + d < order.length; d++) {
            if (trySwap(order[k], order[k + d], tangle, ys)) {
                [order[k], order[k + d]] = [order[k + d], order[k]];
                changed = true;
            }
        }
    }
    return changed;
}

// For each publication, the links it is part of, by index.
function linksAround(size, links) {
    const around = Array.from({ length: size }, () => []);
    links.forEach(([a, b], e) => {
        around[a].push(e);
        around[b].push(e);
    });
    return around;
}

// For each publication, its leaves: the publications linked to it alone.
function leavesAround(around, links) {
    const other = (i, e) => (links[e][0] === i ? links[e][1] : links[e][0]);
    return around.map((edges, i) => edges.map((e) => other(i, e)).filter((k) => around[k].length === 1));
}

// Exchanges heights (ys, changed) until no exchange removes a crossing, at most PASSES
// times. links: pairs of indices of the publications.
export function untangle(xs, ys, links) {
    const around = linksAround(xs.length, links);
    const tangle = {
        xs,
        from: links.map(([a]) => a),
        to: links.map(([, b]) => b),
        around,
        leaves: leavesAround(around, links),
        overlaps: overlapping(links, xs),
        crossings: links.map(() => 0),
    };
    count(tangle, crossingPairs([...links.keys()], tangle, ys), 1);
    const order = ys.map((_, i) => i).sort((p, q) => ys[p] - ys[q]);
    let pass = 0;
    while (pass < PASSES && untanglePass(order, tangle, ys)) {
        pass++;
    }
}
