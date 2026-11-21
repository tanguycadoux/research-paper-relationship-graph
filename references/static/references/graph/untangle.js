// Fewer crossings on the timeline (#323): after the vertical simulation of a group
// (layout.js), two publications close in the vertical order exchange their heights when
// fewer edges cross that way, as in the drawing of a layered graph. x never moves.

// Each publication is compared with the next WINDOW ones from the top.
const WINDOW_ = () => globalThis.LAYOUT_EXP?.window ?? 8;
// At most this many passes over the group: the result is stable well before.
const PASSES_ = () => globalThis.LAYOUT_EXP?.passes ?? 6;

// Whether the links e and f (indices in tangle.from and tangle.to) cross at the heights
// ys: the ends of each strictly on either side of the other (sharing an end is not
// crossing).
function crossAt(tangle, e, f, ys) {
    const { from, to, xs } = tangle;
    globalThis.UNT_CROSS = (globalThis.UNT_CROSS || 0) + 1;
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

// Exchanges the heights of i and j if fewer links cross then; whether they were. Skipped
// when none of their links crosses any other.
function trySwap(i, j, tangle, ys) {
    const touched = [...tangle.around[i], ...tangle.around[j].filter((e) => !tangle.around[i].includes(e))];
    globalThis.UNT_TRY = (globalThis.UNT_TRY || 0) + 1;
    if (!touched.some((e) => tangle.crossings[e] > 0)) {
        return false;
    }
    globalThis.UNT_EVAL = (globalThis.UNT_EVAL || 0) + 1;
    const carried = tangle.carry ? tangle.leaves : null;
    if (carried && (carried[i].includes(j) || carried[j].includes(i))) {
        return false;
    }
    const before = crossingPairs(touched, tangle, ys);
    const dy = ys[j] - ys[i];
    const shift = (sign) => {
        ys[i] += sign * dy;
        ys[j] -= sign * dy;
        if (carried) {
            for (const leaf of carried[i]) ys[leaf] += sign * dy;
            for (const leaf of carried[j]) ys[leaf] -= sign * dy;
        }
    };
    shift(1);
    const after = crossingPairs(touched, tangle, ys, before.length - 1);
    if (after.length < before.length) {
        count(tangle, before, -1);
        count(tangle, after, 1);
        return true;
    }
    shift(-1);
    return false;
}

// One pass from the top: each publication against the next WINDOW ones. Whether any pair
// was exchanged. order: the publications from the top, kept so.
function untanglePass(order, tangle, ys) {
    let changed = false;
    for (let k = 0; k < order.length; k++) {
        for (let d = 1; d <= WINDOW_() && k + d < order.length; d++) {
            if (trySwap(order[k], order[k + d], tangle, ys)) {
                [order[k], order[k + d]] = [order[k + d], order[k]];
                changed = true;
            }
        }
    }
    return changed;
}

// Exchanges heights (ys, changed) until no exchange removes a crossing, at most PASSES
// times. links: pairs of indices of the publications.
export function untangle(xs, ys, links) {
    const around = xs.map(() => []);
    links.forEach(([a, b], e) => {
        around[a].push(e);
        around[b].push(e);
    });
    const tangle = {
        xs,
        from: links.map(([a]) => a),
        to: links.map(([, b]) => b),
        around,
        overlaps: overlapping(links, xs),
        crossings: links.map(() => 0),
        carry: globalThis.LAYOUT_EXP?.carry,
        leaves: xs.map((_, i) => around[i].map((e) => (links[e][0] === i ? links[e][1] : links[e][0])).filter((o) => around[o].length === 1)),
    };
    count(tangle, crossingPairs([...links.keys()], tangle, ys), 1);
    const movable = (globalThis.LAYOUT_EXP?.leavesOnly ?? true) ? (i) => around[i].length === 1 : () => true;
    const order = ys.map((_, i) => i).filter(movable).sort((p, q) => ys[p] - ys[q]);
    for (let pass = 0; pass < PASSES_() && untanglePass(order, tangle, ys); pass++) {
        globalThis.UNT_PASS = (globalThis.UNT_PASS || 0) + 1;
    }
}
