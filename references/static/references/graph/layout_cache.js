// The positions of the layouts of the citation graphs, kept in the browser (#327): the same
// graph, in the same view, frame and time given, is shown again at once, as it was. The key
// is a digest of everything the layout reads (the nodes and edges with their data, the
// view, the size of the frame, the years of the timeline, the time given): data that
// changes lays the graph out again. Kept in IndexedDB, at most MAX_KEPT layouts, the least
// recently used forgotten first; about 45 KB for 1 800 nodes. The browser may refuse it
// (private window, blocked site data, no IndexedDB): the graph is then laid out each time,
// as before.

import { nodeSizes } from "./style.js";

const DATABASE = "citation-graph-layouts";
const STORE = "layouts";
// Part of the key: raised when a layout changes its result for the same data, so that the
// positions kept from before are not shown again.
const LAYOUT_VERSION = 1;
// Layouts kept: a few graphs in both views and a couple of times each.
const MAX_KEPT = 20;
// Beyond this (milliseconds), a database that does not open is done without (it opens in
// a few milliseconds).
const OPEN_TIMEOUT = 300;

let database = null;

// The database, or null without one.
function openDatabase() {
    database ??= new Promise((resolve) => {
        setTimeout(() => resolve(null), OPEN_TIMEOUT);
        try {
            const request = indexedDB.open(DATABASE, 1);
            request.onupgradeneeded = () => {
                request.result.createObjectStore(STORE, { keyPath: "key" }).createIndex("used", "used");
            };
            request.onsuccess = () => resolve(request.result);
            request.onerror = () => resolve(null);
            request.onblocked = () => resolve(null);
        } catch {
            resolve(null);
        }
    });
    return database;
}

function completed(request) {
    return new Promise((resolve, reject) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

// A digest of 64 bits of a text (two 32-bit multiplicative hashes, cyrb53's mixing).
function digest(text) {
    let h1 = 0xdeadbeef;
    let h2 = 0x41c6ce57;
    for (let i = 0; i < text.length; i++) {
        const c = text.charCodeAt(i);
        h1 = Math.imul(h1 ^ c, 2654435761);
        h2 = Math.imul(h2 ^ c, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    return [h2, h1].map((h) => (h >>> 0).toString(16).padStart(8, "0")).join("");
}

// The key of a layout: its message (layout_aside.js) is everything it reads.
export function layoutKey(message) {
    const { view, nodes, edges, frame, budget, years = null } = message;
    const text = JSON.stringify([LAYOUT_VERSION, view, frame, budget, years, nodes, edges]);
    return `${view}:${nodes.length}:${edges.length}:${digest(text)}`;
}

// What is kept of a reply of the layout: the ids of the nodes in their order, their
// positions side by side, and the height of the band of the timeline.
function packed(key, reply) {
    const placed = reply.timeline
        ? reply.timeline.elements.map((element) => [element.data.id, element.position])
        : Object.entries(reply.positions);
    const xy = new Float64Array(2 * placed.length);
    placed.forEach(([, { x, y }], i) => {
        xy[2 * i] = x;
        xy[2 * i + 1] = y;
    });
    const bandY = reply.timeline ? reply.timeline.bandY : null;
    return { key, used: Date.now(), ids: placed.map(([id]) => id), xy, bandY };
}

// The reply of the layout again, as the Web Worker gives it, or null when the entry does
// not fit the nodes of the message. The elements of the timeline are those of placeNodes
// (layout.js): the data of the node with its size.
function unpacked(entry, message) {
    const nodes = new Map(message.nodes.map((node) => [node.data.id, node]));
    if (entry.ids.length !== nodes.size || !entry.ids.every((id) => nodes.has(id))) {
        return null;
    }
    const at = (i) => ({ x: entry.xy[2 * i], y: entry.xy[2 * i + 1] });
    if (message.view !== "frise") {
        return { positions: Object.fromEntries(entry.ids.map((id, i) => [id, at(i)])) };
    }
    const all = nodeSizes(message.nodes);
    const sizes = new Map(message.nodes.map((node, i) => [node.data.id, all[i]]));
    return {
        timeline: {
            elements: entry.ids.map((id, i) => ({ data: { ...nodes.get(id).data, size: sizes.get(id) }, position: at(i) })),
            bandY: entry.bandY,
        },
    };
}

// The reply kept for this message under this key, or null.
export async function keptLayout(key, message) {
    try {
        const db = await openDatabase();
        if (!db) {
            return null;
        }
        const entry = await completed(db.transaction(STORE).objectStore(STORE).get(key));
        const reply = entry ? unpacked(entry, message) : null;
        if (reply) {
            // Used again: the last one to be forgotten.
            db.transaction(STORE, "readwrite").objectStore(STORE).put({ ...entry, used: Date.now() });
        }
        return reply;
    } catch {
        return null;
    }
}

// Keeps a reply of the layout under its key; then forgets the least recently used layouts
// beyond MAX_KEPT. Nothing is kept when the browser refuses (quota, private window).
export async function keepLayout(key, reply) {
    try {
        const db = await openDatabase();
        if (!db) {
            return;
        }
        const store = db.transaction(STORE, "readwrite").objectStore(STORE);
        store.put(packed(key, reply));
        const extra = (await completed(store.count())) - MAX_KEPT;
        if (extra <= 0) {
            return;
        }
        let left = extra;
        const cursors = store.index("used").openCursor();
        cursors.onsuccess = () => {
            const cursor = cursors.result;
            if (cursor && left-- > 0) {
                cursor.delete();
                cursor.continue();
            }
        };
    } catch {
        // Not kept: the layout is done again next time.
    }
}
