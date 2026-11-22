// The time given to the layout of a citation graph (#323): the field « Temps de calcul »
// of the panel (_citation_graph.html), in seconds. The longer, the fewer crossings: the
// layouts go on until then and keep their best drawing (untangle.js, network.js). The
// time is remembered in the browser (localStorage), for every citation graph. Changing it
// lays the graph out again, out of the page (layout_aside.js), with « Calcul en cours… »
// over the frame; then the nodes move to their new positions.

import { CANCELLED } from "./layout_aside.js";

const STORAGE_KEY = "citation-graph-layout-time";
// In seconds; the default is that of the field (about the time the layouts took before).
const MIN_SECONDS = 0.1;
const MAX_SECONDS = 10;
const DEFAULT_SECONDS = 0.1;
// A new value waits this long (ms) for the next one: the arrows of the field give several.
const SETTLE_DELAY = 400;
// The nodes move to their new positions in this long (ms), as a selection does (focus.js).
const DURATION = 600;

const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);

// Within the bounds, to a tenth of a second.
function bounded(seconds) {
    return Math.min(MAX_SECONDS, Math.max(MIN_SECONDS, Math.round(seconds * 10) / 10));
}

// The time remembered, or null. The storage may be refused (private window, blocked
// site data): the default then.
function remembered() {
    try {
        const seconds = parseFloat(localStorage.getItem(STORAGE_KEY));
        return Number.isFinite(seconds) ? bounded(seconds) : null;
    } catch {
        return null;
    }
}

function remember(seconds) {
    try {
        localStorage.setItem(STORAGE_KEY, String(seconds));
    } catch {
        // Not remembered: the field still applies to this page.
    }
}

// The field, set to the time remembered. Returns it, and the time it gives, in
// milliseconds.
export function layoutTimeField() {
    const input = document.getElementById("graph-layout-time");
    const fallback = input ? bounded(input.valueAsNumber || DEFAULT_SECONDS) : DEFAULT_SECONDS;
    const seconds = remembered() ?? fallback;
    if (input) {
        input.value = seconds;
    }
    return { input, budget: seconds * 1000 };
}

// The nodes move from their positions to the new ones (by id), frame by frame, through
// the positions of the layout (stretch.js): a selection being undone moves with them.
// Then the whole graph is shown, measured again. At once on a large graph, as a selection
// (focus.js), or when motion is reduced.
function moveTo(cy, { stretch, viewport }, positions) {
    const from = new Map(cy.nodes().map((node) => [node.id(), { ...stretch.layoutPosition(node) }]));
    const still = !viewport.live || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const start = performance.now();
    let frame = null;
    const step = (now) => {
        const t = still ? 1 : Math.min(1, (now - start) / DURATION);
        const e = easeInOutCubic(t);
        const at = new Map();
        for (const [id, to] of positions) {
            const was = from.get(id);
            if (was) {
                at.set(id, { x: was.x + (to.x - was.x) * e, y: was.y + (to.y - was.y) * e });
            }
        }
        stretch.moveLayout(at);
        if (t < 1) {
            frame = requestAnimationFrame(step);
            return;
        }
        frame = null;
        viewport.showAll();
    };
    step(start);
    return () => frame !== null && cancelAnimationFrame(frame);
}

// Binds the field to the graph. bound: what bindGraph returns (the stretch and the view);
// card: that of the selection, deselected first; relayout(budget, waiting): the new
// positions by id (a Map), or CANCELLED (layout_aside.js) when a newer layout started.
export function bindLayoutTime(cy, field, { bound, card, relayout }) {
    const { input } = field;
    if (!input) {
        return;
    }
    const status = document.querySelector("[data-graph-computing]");
    const waiting = (on) => {
        status.hidden = !on;
    };
    let current = bounded(input.valueAsNumber);
    let settle = null;
    let stopMoving = () => {};
    const run = async () => {
        const asked = input.valueAsNumber;
        if (!Number.isFinite(asked)) {
            input.value = current;
            return;
        }
        const seconds = bounded(asked);
        input.value = seconds;
        if (seconds === current) {
            return;
        }
        current = seconds;
        remember(seconds);
        const positions = await relayout(seconds * 1000, waiting);
        if (positions === CANCELLED) {
            return;
        }
        stopMoving();
        // The selection is undone: the view goes back to the whole graph as the nodes move.
        if (!card.querySelector("[data-card-content]").hidden) {
            card.querySelector("[data-card-close] button").click();
        }
        stopMoving = moveTo(cy, bound, positions);
    };
    input.addEventListener("change", () => {
        clearTimeout(settle);
        settle = setTimeout(run, SETTLE_DELAY);
    });
}
