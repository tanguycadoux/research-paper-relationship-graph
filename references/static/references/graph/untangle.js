// Fewer crossings on the timeline (#323): after the vertical simulation of a group
// (layout.js), publications close in the vertical order exchange their heights when fewer
// edges cross that way, as in the drawing of a layered graph. Each takes its leaves
// (publications linked to it alone) along, so that its fan stays together. x never moves.
// An exchange that would bring nodes closer than the simulation keeps them, or take one
// out of the height of the group, is refused.
// With the time given to the layout (its budget), the search goes further: wider
// exchanges, blocks of publications, then restarts from the best drawing, shaken at
// random (from a fixed seed); the drawing with the fewest crossings is kept.

import { seeded } from "./random.js";

// First descent, always done: each publication against the next WINDOW ones from the
// top, at most PASSES passes (the result is stable well before).
const WINDOW = 8;
const PASSES = 6;
// With time left: each publication against the next WIDE_WINDOW ones, and blocks of up
// to MAX_BLOCK publications consecutive in height exchanged with the block under them.
const WIDE_WINDOW = 24;
const MAX_BLOCK = 4;
// A restart makes KICK_SHARE of the publications (at least MIN_KICKS) exchange at random
// before the next descent.
const KICK_SHARE = 0.05;
const MIN_KICKS = 2;
// The deadline is read every CHECK_EVERY tries: reading the clock costs too.
const CHECK_EVERY = 32;
// Up to this many edges, the first descent is always done, whatever the deadline (30 ms
// for the 130 edges of a corpus). Beyond, everything waits for the deadline, and the
// group is left as it is when the time to prepare it (SETUP_MS_PER_PAIR for each pair of
// edges) does not fit.
const ALWAYS_MAX_LINKS = 300;
const SETUP_MS_PER_PAIR = 1e-5;
// The links to the publications without a date (the band under the timeline, layout.js)
// count too: their other end is taken as fixed, under the group by BAND_DEPTH of its
// height.
const BAND_DEPTH = 0.1;
// Rounding: an exchange that crowds by less than this (pixels) crowds no more.
const CROWDING_TOLERANCE = 1e-6;

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

// For each publication, those closer than closeX in date: the only ones it may overlap.
function closeInDate(xs, closeX) {
    const order = xs.map((_, i) => i).sort((a, b) => xs[a] - xs[b]);
    const close = xs.map(() => []);
    for (let p = 0; p < order.length; p++) {
        for (let q = p + 1; q < order.length && xs[order[q]] - xs[order[p]] < closeX; q++) {
            close[order[p]].push(order[q]);
            close[order[q]].push(order[p]);
        }
    }
    return close;
}

// The crossing pairs of links [e, f], each once, between the links touched (a Set) and
// all the links; stops past limit pairs.
function crossingPairs(touched, tangle, ys, limit = Infinity) {
    const pairs = [];
    for (const e of touched) {
        for (const f of tangle.overlaps[e]) {
            if (!(f < e && touched.has(f)) && crossAt(tangle, e, f, ys)) {
                pairs.push([e, f]);
                if (pairs.length > limit) {
                    return pairs;
                }
            }
        }
    }
    return pairs;
}

// Adds step to the number of crossings of each link of the pairs, and to the total.
function count(tangle, pairs, step) {
    for (const [e, f] of pairs) {
        tangle.crossings[e] += step;
        tangle.crossings[f] += step;
    }
    tangle.total += step * pairs.length;
}

// Counts every crossing again, at the heights ys.
function recount(tangle, ys) {
    tangle.crossings.fill(0);
    tangle.total = 0;
    count(tangle, crossingPairs(new Set(tangle.from.keys()), tangle, ys), 1);
}

// The moves (node -> dy) that exchange the block upper with the block lower, just under
// it, each publication with its leaves: lower goes up to where upper starts, upper down
// to where lower ends, the gaps inside each block kept. Two single publications exchange
// their heights.
function exchangeMoves(upper, lower, tangle, ys) {
    const moves = new Map();
    const down = ys[lower.at(-1)] - ys[upper.at(-1)];
    const up = ys[upper[0]] - ys[lower[0]];
    for (const k of upper) {
        moves.set(k, down);
    }
    for (const k of lower) {
        moves.set(k, up);
    }
    for (const [k, dy] of [...moves]) {
        for (const leaf of tangle.leaves[k]) {
            if (!moves.has(leaf)) {
                moves.set(leaf, dy);
            }
        }
    }
    return moves;
}

function apply(moves, ys, sign) {
    for (const [k, dy] of moves) {
        ys[k] += sign * dy;
    }
}

// How much the publications the moves touch are crowded: for each pair close in date,
// how much closer in height they are than the simulation keeps them (their radii and the
// spacing).
function crowding(moves, tangle, ys) {
    let crowded = 0;
    for (const k of moves.keys()) {
        for (const m of tangle.close[k]) {
            if (!(m < k && moves.has(m))) {
                crowded += Math.max(0, tangle.room[k] + tangle.room[m] - Math.abs(ys[k] - ys[m]));
            }
        }
    }
    return crowded;
}

// Whether the publications moved stay within the heights of the group after the
// simulation: a taller group would be squeezed more to fit the frame (layout.js), its
// nodes brought closer on the screen.
function withinSpan(moves, tangle, ys) {
    for (const k of moves.keys()) {
        if (ys[k] < tangle.top || ys[k] > tangle.bottom) {
            return false;
        }
    }
    return true;
}

// Exchanges the blocks upper and lower if fewer links cross then, without crowding any
// more nodes; whether they were. Skipped when none of their links crosses any other.
// forced (a restart): done whatever the crossings, never crowding any more nodes.
function tryExchange(upper, lower, tangle, ys, forced = false) {
    const moves = exchangeMoves(upper, lower, tangle, ys);
    const touched = new Set([...moves.keys()].flatMap((k) => tangle.around[k]));
    if (!forced && ![...touched].some((e) => tangle.crossings[e] > 0)) {
        return false;
    }
    const before = crossingPairs(touched, tangle, ys);
    const crowdedBefore = crowding(moves, tangle, ys);
    apply(moves, ys, 1);
    if (withinSpan(moves, tangle, ys) && crowding(moves, tangle, ys) <= crowdedBefore + CROWDING_TOLERANCE) {
        const after = crossingPairs(touched, tangle, ys, forced ? Infinity : before.length - 1);
        if (forced || after.length < before.length) {
            count(tangle, before, -1);
            count(tangle, after, 1);
            return true;
        }
    }
    apply(moves, ys, -1);
    return false;
}

// The publications that move, from the top.
function fromTop(tangle, ys) {
    return Array.from({ length: tangle.movable }, (_, i) => i).sort((p, q) => ys[p] - ys[q]);
}

// A clock that says when the deadline is past, read every CHECK_EVERY calls.
function makeClock(deadline) {
    let calls = 0;
    let past = performance.now() >= deadline;
    return () => {
        if (!past && ++calls % CHECK_EVERY === 0) {
            past = performance.now() >= deadline;
        }
        return past;
    };
}

const never = () => false;

// One pass from the top: each publication against the next `window` ones, then each block
// of up to maxBlock publications against the block under it. Whether anything was
// exchanged.
function untanglePass(tangle, ys, window, maxBlock, isLate) {
    const order = fromTop(tangle, ys);
    let changed = false;
    for (let k = 0; k < order.length && !isLate(); k++) {
        for (let d = 1; d <= window && k + d < order.length; d++) {
            if (tryExchange([order[k]], [order[k + d]], tangle, ys)) {
                [order[k], order[k + d]] = [order[k + d], order[k]];
                changed = true;
            }
        }
        for (let size = 3; size <= 2 * maxBlock; size++) {
            for (let a = Math.max(1, size - maxBlock); a <= Math.min(maxBlock, size - 1); a++) {
                if (k + size > order.length) {
                    continue;
                }
                const upper = order.slice(k, k + a);
                const lower = order.slice(k + a, k + size);
                if (tryExchange(upper, lower, tangle, ys)) {
                    order.splice(k, size, ...lower, ...upper);
                    changed = true;
                }
            }
        }
    }
    return changed;
}

// Passes until nothing changes, at most `passes`.
function descend(tangle, ys, { window, maxBlock, passes, isLate }) {
    for (let pass = 0; pass < passes && !isLate(); pass++) {
        if (!untanglePass(tangle, ys, window, maxBlock, isLate)) {
            return;
        }
    }
}

// A random shake: a few exchanges at random, of publications or of blocks, whatever the
// crossings.
function kick(tangle, ys, random) {
    const order = fromTop(tangle, ys);
    const pick = (n) => Math.floor(random() * n);
    const moves = Math.max(MIN_KICKS, Math.round(order.length * KICK_SHARE));
    for (let m = 0; m < moves; m++) {
        const a = 1 + pick(MAX_BLOCK);
        const b = 1 + pick(MAX_BLOCK);
        if (order.length < a + b) {
            continue;
        }
        const k = pick(order.length - a - b + 1);
        tryExchange(order.slice(k, k + a), order.slice(k + a, k + a + b), tangle, ys, true);
    }
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

// For each publication, its leaves: the publications linked to it alone, among the first
// `movable` (the others are the fixed ends of the links to the band).
function leavesAround(around, links, movable) {
    const other = (i, e) => (links[e][0] === i ? links[e][1] : links[e][0]);
    return around.map((edges, i) =>
        edges.map((e) => other(i, e)).filter((k) => k < movable && around[k].length === 1),
    );
}

// What the exchanges need, the first `movable` publications only moving.
function makeTangle(xs, ys, links, sizes, movable, { closeX, spacing }) {
    const around = linksAround(xs.length, links);
    const own = ys.slice(0, movable);
    return {
        xs,
        movable,
        top: Math.min(...own),
        bottom: Math.max(...own),
        from: links.map(([a]) => a),
        to: links.map(([, b]) => b),
        around,
        leaves: leavesAround(around, links, movable),
        overlaps: overlapping(links, xs),
        close: closeInDate(xs.slice(0, movable), closeX),
        // Half of the room the simulation keeps between two close nodes.
        room: sizes.map((size) => size / 2 + spacing / 2),
        crossings: links.map(() => 0),
        total: 0,
    };
}

// Restarts from the best drawing until the deadline: shaken, then a wide descent; a
// drawing with as few crossings is kept to go on from (the search moves along), one with
// more is dropped. Ends on the best drawing.
function restart(tangle, ys, wide, random) {
    let best = { ys: [...ys], total: tangle.total };
    while (best.total > 0 && !wide.isLate()) {
        kick(tangle, ys, random);
        descend(tangle, ys, wide);
        if (tangle.total <= best.total) {
            best = { ys: [...ys], total: tangle.total };
        } else {
            ys.splice(0, ys.length, ...best.ys);
            recount(tangle, ys);
        }
    }
    ys.splice(0, ys.length, ...best.ys);
    tangle.total = best.total;
}

// The positions and the links of a group, with a fixed end under it for each link to the
// band (anchors: [publication, x of the other end]).
function withAnchors(xs, ys, links, anchors) {
    const top = Math.min(...ys);
    const bottom = Math.max(...ys);
    const anchorY = bottom + (bottom - top) * BAND_DEPTH;
    return {
        xs: [...xs, ...anchors.map(([, x]) => x)],
        ys: [...ys, ...anchors.map(() => anchorY)],
        links: [...links, ...anchors.map(([i], k) => [i, xs.length + k])],
    };
}

// Exchanges heights (ys, changed) to remove crossings; returns how many are left, or null
// for a large group without the time to prepare it. links: pairs of indices of the
// publications; sizes: their sizes. options: deadline (performance.now()), wide (after
// the first descent, the wide one and the restarts until the deadline), anchors (the
// links to the band: [publication, x of the publication without a date]), closeX and
// spacing (two publications closer than closeX in date keep spacing between their
// edges), seed of the restarts.
export function untangle(xs, ys, links, sizes, options) {
    const { deadline = -Infinity, wide = false, anchors = [], seed = 1 } = options;
    const all = withAnchors(xs, ys, links, anchors);
    const large = all.links.length > ALWAYS_MAX_LINKS;
    if (large && performance.now() + all.links.length ** 2 * SETUP_MS_PER_PAIR > deadline) {
        return null;
    }
    const tangle = makeTangle(all.xs, all.ys, all.links, sizes, xs.length, options);
    recount(tangle, all.ys);
    const isLate = makeClock(deadline);
    descend(tangle, all.ys, { window: WINDOW, maxBlock: 1, passes: PASSES, isLate: large ? isLate : never });
    if (wide) {
        const search = { window: WIDE_WINDOW, maxBlock: MAX_BLOCK, passes: Infinity, isLate };
        descend(tangle, all.ys, search);
        restart(tangle, all.ys, search, seeded(seed));
    }
    ys.splice(0, ys.length, ...all.ys.slice(0, xs.length));
    return tangle.total;
}
