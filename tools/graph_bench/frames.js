// Frames of a citation graph while it moves (#202): run in a page of the application by
// frames.py, which drives real mouse input (wheel, drag, hover) through Chrome DevTools.
// Defines window.graphFrames:
//   start() / stop(): record the intervals between frames (requestAnimationFrame);
//   mount(options): replace the graph of the page with a synthetic one, drawn by the
//     modules of the application as main.js does (style, viewport, stretch, selection,
//     axis), positions cheaply placed (x: the date, y: spread over the frame) so that the
//     layout, measured by bench.js, does not count here;
//   points(): where the gestures go, in pixels of the page;
//   select() / deselect() / showAll(): the selection of the most connected publication,
//     and back to the view of the whole graph.

window.graphFrames = (() => {
    const base = "/static/references/graph/";
    const container = () => document.getElementById("citation-graph");
    const cyOf = () => container()._cyreg.cy;
    let recording = null;

    function start() {
        const intervals = [];
        let last = performance.now();
        recording = { intervals, running: true };
        const step = () => {
            if (!recording?.running) {
                return;
            }
            const now = performance.now();
            intervals.push(now - last);
            last = now;
            requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    }

    function stop() {
        recording.running = false;
        const sorted = recording.intervals.slice(1).sort((a, b) => a - b);
        const at = (q) => Math.round(sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))]);
        return {
            frames: sorted.length,
            median: at(0.5),
            p90: at(0.9),
            max: Math.round(sorted.at(-1)),
            slow: sorted.filter((interval) => interval > 50).length,
        };
    }

    // The same generator as bench.js: components of decreasing size, each publication
    // citing 2 or 3 older ones of its component (preferential attachment), dates over
    // 1960–2025 with more recent ones, a share without a date.
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
                const date =
                    random() < undated ? null : `${year}-${String(month).padStart(2, "0")}-01`;
                const id = String(next);
                nodes.push({
                    data: {
                        id,
                        date,
                        label: `P${id}`,
                        url: "#",
                        role: "cited",
                        firstAuthor: "Auteur",
                        authorCount: 1,
                        venue: "",
                        citedBy: 0,
                        component,
                    },
                });
                members.push({ id, year });
            }
            members.sort((a, b) => a.year - b.year);
            const cites = new Map();
            members.forEach((member, i) => {
                const older = members.slice(0, i).filter((m) => m.year <= member.year);
                const wanted = Math.min(older.length, 2 + Math.floor(2 * random()));
                const chosen = new Set();
                while (chosen.size < wanted) {
                    const pool = older.flatMap((m) => Array(1 + (cites.get(m.id) || 0)).fill(m));
                    chosen.add(pool[Math.floor(random() * pool.length)].id);
                }
                for (const target of chosen) {
                    cites.set(target, (cites.get(target) || 0) + 1);
                    edges.push({
                        data: { id: `${member.id}-${target}`, source: member.id, target },
                    });
                }
            });
            for (const node of nodes) {
                if (node.data.component === component) {
                    node.data.citedBy = cites.get(node.data.id) || 0;
                }
            }
        });
        return { nodes, edges, random };
    }

    // A fresh copy of an element: the listeners of the graph of the page are dropped.
    function fresh(element) {
        const copy = element.cloneNode(true);
        element.replaceWith(copy);
        return copy;
    }

    async function mount(options) {
        const [style, scaleModule, viewportModule, stretchModule, focusModule, selection, axisModule] =
            await Promise.all(
                ["style", "scale", "viewport", "stretch", "focus", "selection", "axis"].map(
                    (name) => import(`${base}${name}.js`),
                ),
            );
        cyOf().destroy();
        const frame = fresh(container());
        frame.replaceChildren();
        const graph = synthetic(options);
        const years = scaleModule.yearRange(graph.nodes);
        const scale = scaleModule.makeScale(years, graph.nodes.length, frame);
        const sizes = style.nodeSizes(graph.nodes);
        const height = frame.clientHeight - 2 * scaleModule.MARGIN;
        const elements = graph.nodes.map((node, i) => ({
            data: { ...node.data, size: sizes[i] },
            position: {
                x: scale.x(node.data.date ? scaleModule.fractionalYear(node.data.date) : years.min),
                y: scaleModule.MARGIN + graph.random() * height,
            },
        }));
        const cy = cytoscape({
            container: frame,
            elements: [...elements, ...graph.edges],
            style: style.graphStyle(),
            layout: { name: "preset", fit: false },
            autoungrabify: true,
            autounselectify: true,
            // As main.js does, when the application has them.
            ...(viewportModule.rendererOptions?.(elements.length + graph.edges.length) ?? {}),
        });
        const stretch = stretchModule.makeStretch(cy);
        const button = fresh(document.querySelector("[data-graph-show-all] button"));
        const viewport = viewportModule.bindViewport(cy, frame, button, stretch);
        const card = fresh(document.getElementById("citation-graph-card"));
        selection.bindInteractions(cy, card, focusModule.bindFocus(cy, viewport, stretch));
        const axis = document.getElementById("citation-graph-axis");
        const drawAxis = () => axisModule.drawYearAxis(axis, cy, years, scale, stretch);
        cy.on("viewport stretch", drawAxis);
        drawAxis();
        return { nodes: cy.nodes().length, edges: cy.edges().length };
    }

    // In pixels of the page: the centre of the frame, a point without any node near it
    // (to drag the view), and the most connected publications in view (to hover them).
    function points(count = 30) {
        const cy = cyOf();
        const box = container().getBoundingClientRect();
        const rendered = cy.nodes().map((node) => node.renderedPosition());
        let empty = null;
        let farthest = -1;
        for (let x = 40; x < cy.width() - 40; x += 20) {
            for (let y = 40; y < cy.height() - 40; y += 20) {
                const nearest = Math.min(...rendered.map((p) => Math.hypot(p.x - x, p.y - y)));
                if (nearest > farthest) {
                    farthest = nearest;
                    empty = { x: box.left + x, y: box.top + y };
                }
            }
        }
        const hover = cy
            .nodes("[url]")
            .filter((node) => {
                const p = node.renderedPosition();
                return p.x > 10 && p.y > 10 && p.x < cy.width() - 10 && p.y < cy.height() - 10;
            })
            .sort((a, b) => b.degree() - a.degree())
            .slice(0, count)
            .map((node) => ({
                x: box.left + node.renderedPosition().x,
                y: box.top + node.renderedPosition().y,
            }));
        const centre = { x: box.left + cy.width() / 2, y: box.top + cy.height() / 2 };
        return { centre, empty, hover, nodes: cy.nodes().length, edges: cy.edges().length };
    }

    function select() {
        const cy = cyOf();
        const hub = cy.nodes("[url]").sort((a, b) => b.degree() - a.degree())[0];
        hub.emit("tap");
        return { label: hub.data("label").slice(0, 50), degree: hub.degree() };
    }

    // A tap on the background deselects (selection.js).
    function deselect() {
        cyOf().emit("tap");
    }

    function showAll() {
        const button = document.querySelector("[data-graph-show-all] button");
        if (!button.disabled) {
            button.click();
        }
    }

    return { start, stop, mount, points, select, deselect, showAll };
})();
