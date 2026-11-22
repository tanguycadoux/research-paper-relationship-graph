// Web Worker of the network view (#202): runs cose on a large graph, out of the page, which
// keeps responding. Started as a module by layOutAside (network.js). Receives the URL of
// Cytoscape, the size of the frame and the elements (nodes with their size and starting
// position, edges); sends back the positions of the nodes by id, or an error. The positions
// are the same as those of cose in the page (docs/banc-graphe.md).

import { positionsByCose } from "./network.js";

self.onmessage = async ({ data }) => {
    try {
        // A script, not a module: it defines the global `cytoscape`, as in the page.
        await import(data.library);
        // cose pulls the nodes towards the centre of the frame of the page.
        self.postMessage({ positions: positionsByCose(data.elements, data.width, data.height) });
    } catch (error) {
        self.postMessage({ error: String(error) });
    }
};
