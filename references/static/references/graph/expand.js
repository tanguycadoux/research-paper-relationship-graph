// A citation graph developed or reduced without reloading the page (#451): « Développer »
// and « Réduire » on the card of a publication, and the choice of the level in the panel.
// Their links stay, for a page without JavaScript; here, the same view gives the elements
// of the new graph (Accept: application/json, views/graphs.py), laid out aside by the
// layout of the page (layOut: the timeline or the network, main.js). Then, in one motion
// (focus.js): the new publications come out of the one developed, or of a neighbour, and
// fade in; those removed go back into it and fade out; the others slide to their new
// place, the axes with them; the view goes to the selection, or to the whole graph. The
// panel and the card are those of the new graph. The URL follows (history.pushState), and
// Back goes back the same way (popstate).

import { spiralPosition } from "./network.js";
import { LIVE_SIZES_MAX_ELEMENTS } from "./viewport.js";

const LEVEL_LINKS = '[data-graph-variants] [data-variant="niveau"] a';
const TOGGLE_LINKS = '[data-card="develop"] a, [data-card="reduce"] a';
const TOGGLE_SHOWN = '[data-card="develop"]:not([hidden]) a, [data-card="reduce"]:not([hidden]) a';
// The entries of the history made here, or the page itself: Back changes the graph.
const STATE = { graphExpansion: true };
// New nodes of a network start around the node they come out of, this much closer than on
// the starting spiral of a network.
const NEAR = 0.3;

const lerp = (a, b, e) => a + (b - a) * e;
const between = (a, b, e) => ({ x: lerp(a.x, b.x, e), y: lerp(a.y, b.y, e) });

// A click that opens the link here: not in a new tab or window.
function plainClick(event) {
    return event.button === 0 && !(event.metaKey || event.ctrlKey || event.shiftKey || event.altKey);
}

// The ids of the neighbours of each node, in a list of edges (the data of the server).
function neighbours(edges) {
    const around = new Map();
    const link = (a, b) => {
        if (!around.has(a)) around.set(a, []);
        around.get(a).push(b);
    };
    for (const { data } of edges) {
        link(data.source, data.target);
        link(data.target, data.source);
    }
    return around;
}

// For each id, the node of both graphs (kept) that it comes out of or goes back into: the
// publication developed or reduced (preferred) when it is a neighbour, else a neighbour; null
// without any (it fades in or out where it is).
function origins(ids, around, kept, preferred) {
    return new Map(
        ids.map((id) => {
            const near = (around.get(id) ?? []).filter((other) => kept.has(other));
            return [id, near.includes(preferred) ? preferred : (near[0] ?? null)];
        }),
    );
}

// What changes between the graph shown and the next one, by id: the nodes kept, added and
// removed, and where each added or removed node comes from or goes.
function planChange(cy, next, preferred) {
    const shown = new Set(cy.nodes().map((node) => node.id()));
    const nextIds = new Set(next.nodes.map((node) => node.data.id));
    const kept = new Set([...shown].filter((id) => nextIds.has(id)));
    const added = [...nextIds].filter((id) => !shown.has(id));
    const removed = [...shown].filter((id) => !nextIds.has(id));
    const shownEdges = cy.edges().map((edge) => ({ data: edge.data() }));
    return {
        added,
        removed,
        comeFrom: origins(added, neighbours(next.edges), kept, preferred),
        goTo: origins(removed, neighbours(shownEdges), kept, preferred),
    };
}

// Where a node of the next graph starts the network layout (main.js): where it is, or
// around the node it comes out of.
function networkStart(cy, stretch, plan) {
    const index = new Map(plan.added.map((id, i) => [id, i]));
    return (id) => {
        if (!index.has(id)) {
            return { ...stretch.layoutPosition(cy.getElementById(id)) };
        }
        const origin = plan.comeFrom.get(id);
        const centre = origin ? stretch.layoutPosition(cy.getElementById(origin)) : { x: 0, y: 0 };
        const around = spiralPosition(index.get(id) + 1);
        return { x: centre.x + around.x * NEAR, y: centre.y + around.y * NEAR };
    };
}

// The layouts the nodes move between, {id: point}: every node of both graphs.
function layouts(cy, stretch, plan, target) {
    const from = new Map();
    const to = new Map();
    const at = (id) => ({ ...stretch.layoutPosition(cy.getElementById(id)) });
    for (const [id, element] of target) {
        if (!plan.comeFrom.has(id)) {
            from.set(id, at(id));
        }
        to.set(id, { ...element.position });
    }
    for (const id of plan.added) {
        const origin = plan.comeFrom.get(id);
        from.set(id, origin ? { ...from.get(origin) } : to.get(id));
    }
    for (const id of plan.removed) {
        const origin = plan.goTo.get(id);
        from.set(id, at(id));
        to.set(id, origin ? { ...to.get(origin) } : from.get(id));
    }
    return { from, to };
}

// The data of the kept nodes (level, toggle…) is that of the next graph, but their size,
// which moves; the added nodes and edges join, still transparent. Returns the added
// elements, and the kept nodes whose size changes, with their sizes.
function joinNext(cy, next, target) {
    const sizes = [];
    const edgeIds = new Set(cy.edges().map((edge) => edge.id()));
    let added = cy.collection();
    cy.batch(() => {
        for (const [id, element] of target) {
            const node = cy.getElementById(id);
            if (node.empty()) {
                added = added.union(cy.add({ group: "nodes", ...element }));
                continue;
            }
            const size = node.data("size");
            const gone = Object.keys(node.data()).filter((key) => !(key in element.data));
            if (gone.length) {
                node.removeData(gone.join(" "));
            }
            node.data({ ...element.data, size });
            if (size !== element.data.size) {
                sizes.push({ node, from: size, to: element.data.size });
            }
        }
        added = added.union(cy.add(next.edges.filter((edge) => !edgeIds.has(edge.data.id))));
    });
    return { added, sizes };
}

// The elements of the graph shown that the next one does not have.
function leaving(cy, next, target) {
    const edgeIds = new Set(next.edges.map((edge) => edge.data.id));
    const nodes = cy.nodes().filter((node) => !target.has(node.id()));
    return nodes.union(nodes.connectedEdges()).union(cy.edges().filter((edge) => !edgeIds.has(edge.id())));
}

// The selection stays on its publication when the next graph has it, and is marked on the
// next graph alone (the card counts its neighbours there); otherwise it is cleared. Returns
// the nodes the view goes to, or null.
function selectAgain(cy, selection, removed) {
    const selected = selection.selected();
    removed.remove();
    let shown = null;
    if (selected && !selected.removed()) {
        shown = selection.mark(selected);
    } else {
        selection.clear();
    }
    removed.restore();
    return shown;
}

// The opacity of each element as its style gives it, before it moves.
function opacities(elements) {
    return new Map(elements.map((element) => [element.id(), element.pstyle("opacity").value]));
}

// The motion from the graph shown to the next one: placed, the elements of its nodes with
// their positions; moveAxes(e), the axes of the timeline at eased progress e.
function morph(cy, bound, next, placed, plan, moveAxes) {
    const { stretch, focus, selection } = bound;
    const target = new Map(placed.map((element) => [element.data.id, element]));
    const { from, to } = layouts(cy, stretch, plan, target);
    const removed = leaving(cy, next, target);
    const { added, sizes } = joinNext(cy, next, target);
    const nodes = selectAgain(cy, selection, removed);
    const shown = opacities(added);
    const hidden = opacities(removed);
    // A publication on its way out is not hovered nor selected any more.
    removed.nodes().style("events", "no");
    added.style("opacity", 0);
    const onFrame = (e) => {
        for (const [id, point] of from) {
            stretch.setLayout(id, between(point, to.get(id), e));
        }
        cy.batch(() => {
            for (const { node, from: start, to: end } of sizes) {
                node.data("size", lerp(start, end, e));
            }
            added.forEach((element) => element.style("opacity", shown.get(element.id()) * e));
            removed.forEach((element) => element.style("opacity", hidden.get(element.id()) * (1 - e)));
        });
        moveAxes(e);
    };
    const complete = () => {
        removed.nodes().forEach((node) => stretch.forgetLayout(node.id()));
        cy.remove(removed);
        added.removeStyle("opacity");
    };
    focus.morph({ from, to, nodes, onFrame, complete });
}

// The panel of the next graph: what it shows (counts, missing bibliographies), its legend,
// its variants (their links keep the new query string) and the variants kept by the form
// of the tag. Rendered by the server as on the page (views/graphs.py).
function updatePanel(frame, data) {
    frame.card.querySelector("[data-card-empty]").innerHTML = data.summary;
    frame.legend.innerHTML = data.legend;
    const variants = document.querySelector("[data-graph-variants]");
    if (variants) {
        variants.innerHTML = data.variants;
    }
    const form = document.querySelector("form[data-autosubmit]");
    if (form) {
        form.querySelectorAll('input[type="hidden"]').forEach((input) => input.remove());
        for (const [name, value] of Object.entries(data.kept_params)) {
            const input = Object.assign(document.createElement("input"), { type: "hidden", name, value });
            form.prepend(input);
        }
    }
}

async function fetchGraph(url) {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) {
        throw new Error(`${response.status} ${url}`);
    }
    return response.json();
}

// A graph that changes side of LIVE_SIZES_MAX_ELEMENTS changes its rules (viewport.js,
// hover.js), set on creation: the page is loaded again instead, as without JavaScript.
function needsReload(bound, graph) {
    const count = graph.nodes.length + graph.edges.length;
    return graph.edges.length === 0 || (count <= LIVE_SIZES_MAX_ELEMENTS) !== bound.viewport.live;
}

// bound: what bindGraph returns; layOut(graph, start): the elements of the nodes of another
// graph placed by the layout of the page, from the positions start(id) (the network), and
// move(e), the axes at eased progress e (main.js).
export function bindExpansion(cy, frame, bound, layOut) {
    // Only the last request counts: a click during another one supersedes it.
    let latest = 0;
    const go = async (url, { push, preferred = null }) => {
        const ticket = ++latest;
        let data;
        try {
            data = await fetchGraph(url);
        } catch (error) {
            console.error("The graph could not be developed in the page, loaded again:", error);
            window.location.assign(url);
            return;
        }
        if (ticket !== latest) {
            return;
        }
        if (needsReload(bound, data.graph)) {
            window.location.assign(url);
            return;
        }
        if (push) {
            history.pushState(STATE, "", url);
        }
        // A motion on its way ends first: the plan starts from the graph as it ends.
        bound.focus.settle();
        const plan = planChange(cy, data.graph, preferred);
        const { elements, move } = await layOut(data.graph, networkStart(cy, bound.stretch, plan));
        if (ticket !== latest) {
            return;
        }
        morph(cy, bound, data.graph, elements, plan, move);
        updatePanel(frame, data);
    };
    history.replaceState({ ...history.state, ...STATE }, "");
    window.addEventListener("popstate", (event) => {
        if (event.state?.graphExpansion) {
            go(window.location.href, { push: false, preferred: bound.selection.selected()?.id() });
        }
    });
    document.addEventListener("click", (event) => {
        const link = event.target.closest(`${LEVEL_LINKS}, ${TOGGLE_LINKS}`);
        if (!link || !plainClick(event)) {
            return;
        }
        event.preventDefault();
        if (link.hasAttribute("aria-current")) {
            return;
        }
        const toggle = link.closest("[data-card]") !== null;
        go(link.href, { push: true, preferred: toggle ? bound.selection.selected()?.id() : null }).then(() => {
            // The other link of the card takes the focus: « Réduire » after « Développer ».
            if (toggle) {
                frame.card.querySelector(TOGGLE_SHOWN)?.focus();
            }
        });
    });
}
