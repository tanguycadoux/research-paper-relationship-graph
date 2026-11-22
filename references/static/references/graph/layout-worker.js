// Web Worker of the layouts (#202, #323): lays a citation graph out of the page, which
// keeps responding. Started as a module by layout_aside.js. Receives the view, the nodes,
// the edges, the size of the frame and the time given to the layout (budget, in
// milliseconds); for the network, the URL of Cytoscape and the nodes with their size and
// starting position; for the timeline, the range of the years. Sends back the positions
// of the network by id, or the elements of the timeline and the height of its band, or an
// error. The result is that of the same functions in the page.

import { placeNodes } from "./layout.js";
import { networkPositions } from "./network.js";
import { makeScale } from "./scale.js";

self.onmessage = async ({ data }) => {
    try {
        if (data.view === "reseau") {
            // A script, not a module: it defines the global `cytoscape`, as in the page.
            await import(data.library);
            const positions = networkPositions(data.nodes, data.edges, data.frame, data.budget);
            self.postMessage({ positions: Object.fromEntries(positions) });
        } else {
            // makeScale reads the size of the frame as that of its container.
            const container = { clientWidth: data.frame.width, clientHeight: data.frame.height };
            const scale = makeScale(data.years, data.nodes.length, container);
            self.postMessage({ timeline: placeNodes(data.nodes, data.edges, scale, null, data.budget) });
        }
    } catch (error) {
        self.postMessage({ error: String(error) });
    }
};
