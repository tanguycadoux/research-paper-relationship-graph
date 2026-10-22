// The year axis is an HTML strip above the canvas: it stays in view, and its ticks
// follow the horizontal zoom and pan of the graph (#62).

// Minimum distance, in pixels, between two labels of the year axis: the step
// depends on the zoom, not on the visible span, so labels never pile up.
const MIN_LABEL_SPACING = 60;
const TICK_STEPS = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000];

export function tickStep(pixelsPerYear) {
    return (
        TICK_STEPS.find((step) => step * pixelsPerYear >= MIN_LABEL_SPACING) || TICK_STEPS.at(-1)
    );
}

function axisLabel(text, x) {
    const label = document.createElement("span");
    label.className = "absolute top-1/2 -translate-x-1/2 -translate-y-1/2 whitespace-nowrap";
    label.style.left = `${x}px`;
    label.textContent = String(text);
    return label;
}

export function drawYearAxis(axis, cy, years, scale) {
    const renderedX = (year) => scale.x(year) * cy.zoom() + cy.pan().x;
    const extent = cy.extent();
    // Ticks only over the dated publications, in the visible part of the graph.
    const first = Math.max(scale.year(extent.x1), Math.floor(years.min));
    const last = Math.min(scale.year(extent.x2), Math.ceil(years.max));
    const step = tickStep(renderedX(1) - renderedX(0));
    const undatedX = renderedX(scale.undatedYear);
    const labels = [axisLabel("Non daté", undatedX)];
    for (let year = Math.ceil(first / step) * step; year <= last; year += step) {
        const x = renderedX(year);
        if (Math.abs(x - undatedX) >= MIN_LABEL_SPACING) {
            labels.push(axisLabel(year, x));
        }
    }
    axis.replaceChildren(...labels);
}
