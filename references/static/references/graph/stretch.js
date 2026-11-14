// Stretch of the graph along each axis, around a centre (#291). Cytoscape has a single
// zoom for both axes: to make a selection fill the whole frame, its positions are spread
// further apart along the axis where there is room left. x stays a date: the year axis
// reads the same stretch, so the years stay under the nodes. Without a selection, the
// stretch is the identity: positions are the ones of the layout.

export const IDENTITY = { sx: 1, sy: 1, cx: 0, cy: 0 };

export function isIdentity(stretch) {
    return stretch.sx === 1 && stretch.sy === 1;
}

// The point of the layout at (x, y), once stretched.
function stretched(stretch, x, y) {
    return {
        x: stretch.cx + (x - stretch.cx) * stretch.sx,
        y: stretch.cy + (y - stretch.cy) * stretch.sy,
    };
}

// A box of the layout ({x1, x2, y1, y2}), once stretched.
export function stretchedBox(stretch, box) {
    const start = stretched(stretch, box.x1, box.y1);
    const end = stretched(stretch, box.x2, box.y2);
    return { x1: start.x, y1: start.y, x2: end.x, y2: end.y };
}

// Positions of the layout are kept on creation: a stretch is always applied to them, so
// that any number of stretches ends exactly where it began. Emits "stretch" on the graph.
export function makeStretch(cy) {
    const layout = new Map();
    cy.nodes().forEach((node) => layout.set(node.id(), { ...node.position() }));
    let current = IDENTITY;
    const apply = (stretch) => {
        current = stretch;
        cy.batch(() => {
            cy.nodes().forEach((node) => {
                const point = layout.get(node.id());
                node.position(stretched(stretch, point.x, point.y));
            });
        });
        cy.emit("stretch");
    };
    return {
        current: () => current,
        // Position of a node in the layout, whatever the stretch.
        layoutPosition: (node) => layout.get(node.id()),
        // x of the graph for an x of the layout, and back (the year axis).
        x: (x) => current.cx + (x - current.cx) * current.sx,
        layoutX: (x) => current.cx + (x - current.cx) / current.sx,
        // y of the graph for a y of the layout (the band of the publications without a date).
        y: (y) => current.cy + (y - current.cy) * current.sy,
        apply,
    };
}
