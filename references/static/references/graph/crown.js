// Leaves of the network view (#323): a publication linked to a single other one, its hub,
// itself linked to others (a reference cited by a single publication of the corpus, say).
// cose lays out the rest of the graph, the core, where each hub takes the room of its
// crown; its leaves then go around it, in the widest gaps between its links to the core:
// away from the rest of the graph, their edges no longer cross it, and the leaves of two
// neighbouring hubs do not mix. Then the whole drawing is turned to fill the frame.

// Between two leaves of a crown, along it, in pixels.
const LEAF_GAP = 10;
// The smallest radius of a crown: an edge of cose (idealEdgeLength, network.js).
const CROWN_MIN_RADIUS = 48;
// The room kept around a hub fits its leaves on this share of the circle: the rest is for
// its links to the core.
const CROWN_FILL = 0.6;
// Leaves keep at least this angle (radians) from the links of their hub to the core.
const LINK_MARGIN = 0.35;
// The drawing is turned by a multiple of this angle (radians) to fill the frame best.
const TURN_STEP = Math.PI / 12;

function neighbourSets(nodes, edges) {
    const around = new Map(nodes.map((n) => [n.data.id, new Set()]));
    for (const { data } of edges) {
        if (data.source !== data.target && around.has(data.source) && around.has(data.target)) {
            around.get(data.source).add(data.target);
            around.get(data.target).add(data.source);
        }
    }
    return around;
}

// The leaves of each hub, by the id of the hub, in the order of the nodes.
export function findCrowns(nodes, edges) {
    const around = neighbourSets(nodes, edges);
    const leavesOf = new Map();
    for (const node of nodes) {
        const others = around.get(node.data.id);
        const [hub] = others;
        if (others.size === 1 && around.get(hub).size > 1) {
            if (!leavesOf.has(hub)) {
                leavesOf.set(hub, []);
            }
            leavesOf.get(hub).push(node);
        }
    }
    return leavesOf;
}

// The length of the crown along its circle.
function crownLength(leaves) {
    return leaves.reduce((sum, leaf) => sum + leaf.data.size + LEAF_GAP, 0);
}

// The radius of the room kept around a hub: its leaves on CROWN_FILL of the circle.
function roomRadius(leaves) {
    return Math.max(CROWN_MIN_RADIUS, crownLength(leaves) / (2 * Math.PI * CROWN_FILL));
}

// The size cose gives a hub: its crown, leaves included.
export function hubSize(hub, leaves) {
    const largest = Math.max(...leaves.map((leaf) => leaf.data.size));
    return Math.max(hub.data.size, 2 * roomRadius(leaves) + largest);
}

// The gaps between the directions of the given angles, the widest first, each with the
// part leaves may use (away from the links by LINK_MARGIN, or a quarter of the gap).
function gaps(angles) {
    if (angles.length === 0) {
        return [{ start: -Math.PI / 2, width: 2 * Math.PI }];
    }
    const sorted = [...angles].sort((a, b) => a - b);
    return sorted
        .map((angle, i) => {
            const next = i + 1 < sorted.length ? sorted[i + 1] : sorted[0] + 2 * Math.PI;
            const margin = Math.min(LINK_MARGIN, (next - angle) / 4);
            return { start: angle + margin, width: next - angle - 2 * margin };
        })
        .sort((a, b) => b.width - a.width);
}

// How many leaves go in each gap: the widest gaps first, each taking as many as fit at the
// radius of the room; if they do not all fit, one by one where the radius they need stays
// the smallest.
function gapCounts(gapList, count, room, slot) {
    let left = count;
    const counts = gapList.map((gap) => {
        const fit = Math.min(left, Math.floor((gap.width * room) / slot));
        left -= fit;
        return fit;
    });
    if (left === 0) {
        return counts;
    }
    const spread = gapList.map(() => 0);
    for (let leaf = 0; leaf < count; leaf++) {
        const next = (g) => (spread[g] + 1) / gapList[g].width;
        const best = spread.reduce((chosen, _, g) => (next(g) < next(chosen) ? g : chosen), 0);
        spread[best] += 1;
    }
    return spread;
}

// The angles of the leaves, spread evenly in their gaps, and the radius of the crown: the
// smallest at which they fit, at least CROWN_MIN_RADIUS.
function crownAngles(leaves, linkAngles) {
    const slot = crownLength(leaves) / leaves.length;
    const gapList = gaps(linkAngles);
    const counts = gapCounts(gapList, leaves.length, roomRadius(leaves), slot);
    const radius = Math.max(
        CROWN_MIN_RADIUS,
        ...gapList.map((gap, g) => (counts[g] ? (counts[g] * slot) / gap.width : 0)),
    );
    const angles = gapList.flatMap((gap, g) =>
        Array.from({ length: counts[g] }, (_, k) => gap.start + (gap.width * (k + 0.5)) / counts[g]),
    );
    return { angles, radius };
}

// The positions of the leaves around their hubs, added to positions (by id), from those
// of the core. coreEdges: the edges between the nodes of the core.
export function placeCrowns(leavesOf, positions, coreEdges) {
    const linked = new Map([...leavesOf.keys()].map((hub) => [hub, []]));
    for (const { data } of coreEdges) {
        linked.get(data.source)?.push(data.target);
        linked.get(data.target)?.push(data.source);
    }
    for (const [hub, leaves] of leavesOf) {
        const centre = positions.get(hub);
        const linkAngles = linked.get(hub).map((other) => {
            const at = positions.get(other);
            return Math.atan2(at.y - centre.y, at.x - centre.x);
        });
        const { angles, radius } = crownAngles(leaves, linkAngles);
        leaves.forEach((leaf, i) => {
            const x = centre.x + radius * Math.cos(angles[i]);
            positions.set(leaf.data.id, { x, y: centre.y + radius * Math.sin(angles[i]) });
        });
    }
}

// The publications linked to the same two others only (references shared by two
// publications of the corpus), by their pair, when there are several.
function sharedByPairs(nodes, around, leavesOf) {
    const byPair = new Map();
    for (const node of nodes) {
        const others = around.get(node.data.id);
        if (others.size === 2 && !leavesOf.has(node.data.id)) {
            const pair = [...others].sort().join(" ");
            byPair.set(pair, [...(byPair.get(pair) || []), node]);
        }
    }
    return [...byPair].filter(([, shared]) => shared.length > 1);
}

// The publications shared by the same two others on a line across the middle of these two,
// in the order cose gave them along it, LEAF_GAP apart: none of their edges cross, since
// each of the two is on its own side of the line. Changes positions (by id).
export function lineUpShared(nodes, edges, leavesOf, positions) {
    for (const [pair, shared] of sharedByPairs(nodes, neighbourSets(nodes, edges), leavesOf)) {
        const [a, b] = pair.split(" ").map((id) => positions.get(id));
        const length = Math.hypot(b.x - a.x, b.y - a.y) || 1;
        const across = { x: -(b.y - a.y) / length, y: (b.x - a.x) / length };
        const along = (at) => (at.x - a.x) * across.x + (at.y - a.y) * across.y;
        const ordered = [...shared].sort((p, q) => along(positions.get(p.data.id)) - along(positions.get(q.data.id)));
        const total = crownLength(shared) - LEAF_GAP;
        const mean = shared.reduce((sum, node) => sum + along(positions.get(node.data.id)), 0) / shared.length;
        let offset = mean - total / 2;
        for (const node of ordered) {
            const at = offset + node.data.size / 2;
            const x = (a.x + b.x) / 2 + at * across.x;
            positions.set(node.data.id, { x, y: (a.y + b.y) / 2 + at * across.y });
            offset += node.data.size + LEAF_GAP;
        }
    }
}

// How much the drawing turned by this angle must shrink to fit the frame (larger: fills
// it better).
function fitRatio(points, angle, frame) {
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    let [x1, y1, x2, y2] = [Infinity, Infinity, -Infinity, -Infinity];
    for (const { x, y, size } of points) {
        const u = x * cos - y * sin;
        const v = x * sin + y * cos;
        [x1, x2] = [Math.min(x1, u - size / 2), Math.max(x2, u + size / 2)];
        [y1, y2] = [Math.min(y1, v - size / 2), Math.max(y2, v + size / 2)];
    }
    return Math.min(frame.width / (x2 - x1 || 1), frame.height / (y2 - y1 || 1));
}

// The positions (by id) turned so that the drawing fills the frame best: a network has no
// direction, and fitted to the frame, a drawing wider than the frame left empty bands
// above and under it. sizes: by id; frame: its width and height.
export function turnToFrame(positions, sizes, frame) {
    const points = [...positions].map(([id, at]) => ({ ...at, size: sizes.get(id) }));
    let best = { angle: 0, ratio: fitRatio(points, 0, frame) };
    for (let angle = TURN_STEP; angle < Math.PI; angle += TURN_STEP) {
        const ratio = fitRatio(points, angle, frame);
        // Turned only when it fills the frame noticeably better.
        if (ratio > best.ratio * 1.02) {
            best = { angle, ratio };
        }
    }
    const cos = Math.cos(best.angle);
    const sin = Math.sin(best.angle);
    for (const [id, { x, y }] of positions) {
        positions.set(id, { x: x * cos - y * sin, y: x * sin + y * cos });
    }
    return positions;
}
