// Measures of the layout of a citation graph (#202), run in a page of the application by
// bench.py (Chrome DevTools). The code of the application is not changed: layout.js is
// fetched, its internal functions are exported from a copy loaded as a module, and the
// steps of verticalPositions are timed one by one, as it runs them.
//
// Called as an expression with OPTIONS replaced by a JSON object:
//   {graph: "page" | {nodes: n, components: k, undated: share, seed: s}, repeat: r,
//    width: px, height: px}
// Returns the medians of the timings, in milliseconds, and the sizes of the work.

(async (OPTIONS) => {
    const base = "/static/references/graph/";
    const source = await (await fetch(`${base}layout.js`)).text();
    const exported = source.replace(/from "\.\//g, `from "${location.origin}${base}`) +
        "\nexport { linkPairs, closePairs, crossedEdges, pullLinked, clearEdges, separateClose };\n";
    const url = URL.createObjectURL(new Blob([exported], { type: "text/javascript" }));
    const layout = await import(url);
    const { makeScale, yearRange, fractionalYear } = await import(`${base}scale.js`);
    const { nodeSizes } = await import(`${base}style.js`);

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

    const runs = [];
    for (let r = 0; r < OPTIONS.repeat; r++) {
        const run = {};
        const years = yearRange(graph.nodes);
        const scale = makeScale(years, graph.nodes.length, frame);
        // The whole layout, as main.js calls it.
        [run.placeNodes] = time(() => layout.placeNodes(graph.nodes, graph.edges, scale));
        // Its steps, on the dated publications, as placeOnTimeline runs them.
        const dated = graph.nodes.filter((n) => n.data.date);
        const byDate = [...dated].sort(
            (a, b) => fractionalYear(a.data.date) - fractionalYear(b.data.date),
        );
        const sizesAll = nodeSizes(graph.nodes);
        const sizeOf = new Map(graph.nodes.map((n, i) => [n.data.id, sizesAll[i]]));
        const links = layout.linkPairs(byDate, graph.edges);
        let rows;
        [run.barycentreOrder, rows] = time(() => layout.barycentreOrder(byDate.length, links));
        const xs = byDate.map((n) => scale.x(fractionalYear(n.data.date)));
        const sizes = byDate.map((n) => sizeOf.get(n.data.id));
        let close;
        let crossed;
        [run.closePairs, close] = time(() => layout.closePairs(xs));
        [run.crossedEdges, crossed] = time(() => layout.crossedEdges(xs, links));
        const startYs = rows.map((row) => row * 36);
        const ys = [...startYs];
        run.pullLinked = 0;
        run.clearEdges = 0;
        run.separateClose = 0;
        for (let step = 0; step < 300; step++) {
            run.pullLinked += time(() => layout.pullLinked(ys, links))[0];
            run.clearEdges += time(() => layout.clearEdges(xs, ys, crossed, sizes))[0];
            run.separateClose += time(() => layout.separateClose(ys, close, startYs, sizes))[0];
        }
        run.closePairCount = close.length;
        run.crossedCount = crossed.length;
        runs.push(run);
    }
    const result = { nodes: graph.nodes.length, edges: graph.edges.length };
    result.undated = graph.nodes.filter((n) => !n.data.date).length;
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
