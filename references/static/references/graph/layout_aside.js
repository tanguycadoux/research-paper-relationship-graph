// A layout of a citation graph out of the page, in a Web Worker (layout-worker.js, #202,
// #323): the page keeps responding, and shows that it waits. A small graph given little
// time is laid out in the page, without a message that would only flash. One layout at a
// time: a new one stops the one in progress.

import { LIVE_SIZES_MAX_ELEMENTS } from "./viewport.js";

// Beyond this many elements (nodes and edges), the layout goes to the worker, whatever the
// time given to it: 2.9 s for a network of 1 800 publications.
const WORKER_MIN_ELEMENTS = LIVE_SIZES_MAX_ELEMENTS;
// Up to this time given to the layout (milliseconds), a smaller graph is laid out in the
// page: the page holds about as long.
const IN_PAGE_MAX_BUDGET = 100;

// What a layout stopped by a newer one resolves to.
export const CANCELLED = Symbol("cancelled");

let running = null;

function startWorker() {
    try {
        return new Worker(new URL("./layout-worker.js", import.meta.url), { type: "module" });
    } catch {
        return null;
    }
}

// message: the view ("frise" or "reseau"), the nodes, the edges, the frame ({width,
// height}), the budget (milliseconds), and the years of the timeline. waiting(on): shows
// and hides what says that the layout runs. always: in the worker whatever the size (a new
// layout asked from the panel, which shows that it runs). Resolves to the reply of the
// worker ({positions} of the network by id, {timeline}: the elements and bandY), to null
// when the layout is to be done in the page instead (small graph, or the worker failed),
// or to CANCELLED when a newer layout started meanwhile.
export function layOutAside(message, waiting, always = false) {
    const small = message.nodes.length + message.edges.length <= WORKER_MIN_ELEMENTS;
    if (!always && small && message.budget <= IN_PAGE_MAX_BUDGET) {
        return Promise.resolve(null);
    }
    running?.cancel();
    const worker = startWorker();
    if (!worker) {
        return Promise.resolve(null);
    }
    waiting(true);
    return new Promise((resolve) => {
        const end = (reply) => {
            worker.terminate();
            running = null;
            waiting(false);
            resolve(reply);
        };
        running = { cancel: () => end(CANCELLED) };
        const failed = (error) => {
            console.error("Layout failed in the Web Worker, done in the page instead:", error);
            end(null);
        };
        worker.onmessage = ({ data }) => (data.error ? failed(data.error) : end(data));
        worker.onerror = (event) => failed(event.message);
        // The worker loads the same Cytoscape as the page.
        const library = document.querySelector('script[src$="/cytoscape.min.js"]').src;
        worker.postMessage({ ...message, library });
    });
}
