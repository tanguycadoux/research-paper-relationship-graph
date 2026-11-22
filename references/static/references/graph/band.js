// The band of the publications without a date, under the timeline (#288): a dashed line
// across the frame, with its label, half way between the lowest dated publication and the
// band. It is HTML over the canvas, like the year axis, and follows the zoom, the pan and
// the stretch of a selection (#291).

import { BAND_GAP } from "./layout.js";

// bandY(): the height of the band in the layout, null without any; it changes when the
// graph is developed or reduced (#451).
export function bindUndatedBand(cy, band, bandY, stretch) {
    const container = cy.container();
    const place = () => {
        if (bandY() === null) {
            band.hidden = true;
            return;
        }
        const y = stretch.y(bandY() - BAND_GAP / 2) * cy.zoom() + cy.pan().y;
        band.hidden = y < 0 || y > cy.height();
        band.style.top = `${container.offsetTop + y}px`;
    };
    cy.on("viewport stretch", place);
    place();
}
