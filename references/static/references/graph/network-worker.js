// Web Worker of the network view (#202): lays out a large graph out of the page, which
// keeps responding. Started as a module by layOutAside (network.js). Receives the URL of
// Cytoscape, the size of the frame, the nodes (with their size and starting position) and
// the edges; sends back the positions of the nodes by id, or an error. The positions are
// those of networkPositions in the page.

import { networkPositions } from "./network.js";

self.onmessage = async ({ data }) => {
    try {
        // A script, not a module: it defines the global `cytoscape`, as in the page.
        await import(data.library);
        const positions = networkPositions(data.nodes, data.edges, data.frame);
        self.postMessage({ positions: Object.fromEntries(positions) });
    } catch (error) {
        self.postMessage({ error: String(error) });
    }
};
