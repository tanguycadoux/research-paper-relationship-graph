// Web Worker of the network view (#202): runs cose on a large graph, out of the page, which
// keeps responding. Started as a module by layOutAside (network.js). Receives the URL of
// Cytoscape, the size of the frame and the elements (nodes with their size and starting
// position, edges); sends back the positions of the nodes by id, or an error. The positions
// are the same as those of cose in the page (docs/banc-graphe.md).

import { COSE, LAYOUT_STYLE } from "./network.js";

self.onmessage = async ({ data }) => {
    try {
        // A script, not a module: it defines the global `cytoscape`, as in the page.
        await import(data.library);
        const cy = cytoscape({
            headless: true,
            // cose reads the sizes of the nodes from the style.
            styleEnabled: true,
            style: LAYOUT_STYLE,
            elements: data.elements,
            // Otherwise the null layout would put every node at (0, 0), and cose would
            // separate them at random.
            layout: { name: "preset", fit: false },
        });
        // cose pulls the nodes towards the centre of the frame (cy.width(), cy.height()),
        // which a headless Cytoscape does not have: the size of the frame of the page.
        cy.width = () => data.width;
        cy.height = () => data.height;
        cy.layout(COSE).run();
        const positions = {};
        cy.nodes().forEach((node) => {
            positions[node.id()] = node.position();
        });
        self.postMessage({ positions });
    } catch (error) {
        self.postMessage({ error: String(error) });
    }
};
