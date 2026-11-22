// Crossings of straight edges (#323), to choose between layouts: two edges cross when the
// ends of each are strictly on either side of the other; edges sharing an end never cross.

function side(p, q, r) {
    return Math.sign((q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x));
}

// Whether the segments p1 p2 and q1 q2 cross.
export function cross(p1, p2, q1, q2) {
    return side(p1, p2, q1) * side(p1, p2, q2) < 0 && side(q1, q2, p1) * side(q1, q2, p2) < 0;
}

// Whether two links [a, b] (ends by any key) cross, at(key) giving the position of an end.
export function linksCross([a, b], [c, d], at) {
    if (a === c || a === d || b === c || b === d) {
        return false;
    }
    return cross(at(a), at(b), at(c), at(d));
}

// The number of crossings between the links, each a pair of ends [a, b].
export function countCrossings(links, at) {
    let count = 0;
    for (let i = 0; i < links.length; i++) {
        for (let j = i + 1; j < links.length; j++) {
            if (linksCross(links[i], links[j], at)) {
                count++;
            }
        }
    }
    return count;
}
