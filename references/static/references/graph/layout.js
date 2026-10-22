// Positions of the nodes: x is the publication date, one row per publication.

import { fractionalYear } from "./scale.js";
import { citedByRange, nodeColor } from "./style.js";

export function placeNodes(nodes, scale) {
    const yearOf = (n) => (n.data.date ? fractionalYear(n.data.date) : scale.undatedYear);
    const sorted = [...nodes].sort((a, b) => yearOf(a) - yearOf(b));
    const citedRange = citedByRange(nodes);
    return sorted.map((n, row) => ({
        data: { ...n.data, color: nodeColor(n.data, citedRange) },
        position: { x: scale.x(yearOf(n)), y: scale.y(row) },
    }));
}
