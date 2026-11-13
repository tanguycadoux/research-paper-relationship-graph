// The band of the publications without a date, under the timeline (#288): a dashed line
// across the frame, with its label, half way between the lowest dated publication and the
// band. It is HTML over the canvas, like the year axis, and follows the zoom and the pan.

import { BAND_GAP } from "./layout.js";

export function bindUndatedBand(cy, band, bandY) {
    if (bandY === null) {
        return;
    }
    const container = cy.container();
    const place = () => {
        const y = (bandY - BAND_GAP / 2) * cy.zoom() + cy.pan().y;
        band.hidden = y < 0 || y > cy.height();
        band.style.top = `${container.offsetTop + y}px`;
    };
    cy.on("viewport", place);
    place();
}
