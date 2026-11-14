// Measures of the layout of a citation graph (#202), run in a page of the application by
// bench.py (Chrome DevTools). The code of the application is not changed: placeNodes is
// called with a timings object, in which layout.js adds up the time of each step.
//
// Called as an expression with OPTIONS replaced by a JSON object:
//   {graph: "page" | {nodes: n, components: k, undated: share, seed: s}, repeat: r,
//    width: px, height: px}
// Returns the medians of the timings, in milliseconds, the number of crossings of edges
// in the result, and the sizes of the work.

(async (OPTIONS) => {
    const base = "/static/references/graph/";
    const layout = await import(`${base}layout.js`);
    const { makeScale, yearRange } = await import(`${base}scale.js`);

    // A synthetic graph: components of decreasing size, each publication citing 2 or 3
    // older ones of its component, the most cited more often (preferential attachment),
    // dates spread over 1960–2025 with more recent ones, a share without a date.
    function synthetic({ nodes: count, components, undated, seed }) {
        let state = seed;
        const random = () => {
            state = (state * 1103515245 + 12345) % 2147483648;
            return state / 2147483648;
        };
        const nodes = [];
        const edges = [];
        const weights = Array.from({ length: components }, (_, k) => 2 ** (components - k));
        const total = weights.reduce((a, b) => a + b, 0);
        let next = 0;
        weights.forEach((weight, component) => {
            const size = Math.max(2, Math.round((count * weight) / total));
            const members = [];
            for (let i = 0; i < size && next < count; i++, next++) {
                const year = 2025 - Math.floor(65 * random() ** 2);
                const month = 1 + Math.floor(12 * random());
                const date = random() < undated ? null : `${year}-${String(month).padStart(2, "0")}-01`;
                const id = String(next);
                nodes.push({ data: { id, date, label: `P${id}`, citedBy: 0, component } });
                members.push({ id, year });
            }
            members.sort((a, b) => a.year - b.year);
            const cites = new Map();
            members.forEach((member, i) => {
                const older = members.slice(0, i).filter((m) => m.year <= member.year);
                const wanted = Math.min(older.length, 2 + Math.floor(2 * random()));
                const chosen = new Set();
                while (chosen.size < wanted) {
                    // Preferential attachment: one more chance per citation already received.
                    const pool = older.flatMap((m) => Array(1 + (cites.get(m.id) || 0)).fill(m));
                    chosen.add(pool[Math.floor(random() * pool.length)].id);
                }
                for (const target of chosen) {
                    cites.set(target, (cites.get(target) || 0) + 1);
                    edges.push({ data: { id: `${member.id}-${target}`, source: member.id, target } });
                }
            });
            for (const node of nodes) {
                if (node.data.component === component) {
                    node.data.citedBy = cites.get(node.data.id) || 0;
                }
            }
        });
        return { nodes, edges };
    }

    const graph = OPTIONS.graph === "page"
        ? JSON.parse(document.getElementById("citation-graph-data").textContent)
        : synthetic(OPTIONS.graph);
    const frame = OPTIONS.graph === "page"
        ? document.getElementById("citation-graph")
        : { clientWidth: OPTIONS.width, clientHeight: OPTIONS.height };

    const median = (values) => {
        const sorted = [...values].sort((a, b) => a - b);
        return sorted[Math.floor(sorted.length / 2)];
    };
    const time = (f) => {
        const start = performance.now();
        const result = f();
        return [performance.now() - start, result];
    };

    // Edges that cross, in the result (sharing an end is not crossing).
    const crossings = (elements) => {
        const at = new Map(elements.map((e) => [e.data.id, e.position]));
        const segments = graph.edges
            .map(({ data }) => [data.source, data.target, at.get(data.source), at.get(data.target)])
            .filter(([, , p, q]) => p && q);
        const side = (p, q, r) => Math.sign((q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x));
        let count = 0;
        for (let i = 0; i < segments.length; i++) {
            const [a, b, p1, p2] = segments[i];
            for (let j = i + 1; j < segments.length; j++) {
                const [c, d, q1, q2] = segments[j];
                if (a === c || a === d || b === c || b === d) continue;
                if (side(p1, p2, q1) * side(p1, p2, q2) < 0 && side(q1, q2, p1) * side(q1, q2, p2) < 0) {
                    count++;
                }
            }
        }
        return count;
    };

    const runs = [];
    let elements;
    for (let r = 0; r < OPTIONS.repeat; r++) {
        const timings = {};
        const scale = makeScale(yearRange(graph.nodes), graph.nodes.length, frame);
        // The whole layout, as main.js calls it, and its steps.
        let placed;
        [timings.placeNodes, placed] = time(() =>
            layout.placeNodes(graph.nodes, graph.edges, scale, timings),
        );
        elements = placed.elements;
        runs.push(timings);
    }
    const result = { nodes: graph.nodes.length, edges: graph.edges.length };
    result.undated = graph.nodes.filter((n) => !n.data.date).length;
    result.crossings = crossings(elements);
    for (const key of Object.keys(runs[0])) {
        result[key] = Math.round(median(runs.map((run) => run[key])) * 10) / 10;
    }
    if (OPTIONS.render) {
        Object.assign(result, await render(graph));
    }
    return result;

    // A synthetic graph drawn by Cytoscape as the page does (style of style.js, sizes fixed
    // on the screen): the creation, then frames while zooming, as with the mouse wheel.
    async function render(graph) {
        const { graphStyle } = await import(`${base}style.js`);
        const container = document.createElement("div");
        container.style.cssText = `position:fixed;left:0;top:0;width:${OPTIONS.width}px;height:${OPTIONS.height}px;background:white;z-index:1000`;
        document.body.append(container);
        const scale = makeScale(yearRange(graph.nodes), graph.nodes.length, container);
        const { elements } = layout.placeNodes(graph.nodes, graph.edges, scale);
        const [create, cy] = time(() =>
            cytoscape({
                container,
                elements: [...elements, ...graph.edges],
                style: graphStyle(),
                layout: { name: "preset", fit: true },
            }),
        );
        const frames = await zoomFrames(cy);
        cy.destroy();
        container.remove();
        return { cytoscapeCreate: Math.round(create), ...frames };
    }

    // Intervals between frames while the zoom changes at each frame (style re-evaluated, as
    // keepScreenSize does in main.js).
    function zoomFrames(cy) {
        return new Promise((resolve) => {
            const intervals = [];
            let last = performance.now();
            let count = 0;
            const step = () => {
                const now = performance.now();
                intervals.push(now - last);
                last = now;
                cy.zoom({ level: cy.zoom() * 1.02, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
                cy.style().update();
                if (++count < 40) {
                    requestAnimationFrame(step);
                } else {
                    resolve({
                        zoomFrameMedian: Math.round(median(intervals.slice(2))),
                        zoomFrameMax: Math.round(Math.max(...intervals.slice(2))),
                    });
                }
            };
            requestAnimationFrame(step);
        });
    }
})(OPTIONS)
