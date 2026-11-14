// Dates and the scale of the timeline: x follows the publication date, y the row.

export const MARGIN = 40;

export function fractionalYear(isoDate) {
    const date = new Date(isoDate);
    const start = Date.UTC(date.getUTCFullYear(), 0, 1);
    const end = Date.UTC(date.getUTCFullYear() + 1, 0, 1);
    return date.getUTCFullYear() + (date.getTime() - start) / (end - start);
}

export function yearRange(nodes) {
    const years = nodes.filter((n) => n.data.date).map((n) => fractionalYear(n.data.date));
    if (years.length === 0) {
        const now = new Date().getFullYear();
        return { min: now, max: now };
    }
    return { min: Math.min(...years), max: Math.max(...years) };
}

// Maps years to x and rows to y, each axis scaled to the container independently. The
// timeline starts at the oldest year: the publications without a date are on a band
// under it (#288), not in a column of their own.
export function makeScale(years, rowCount, container) {
    const start = years.min;
    const width = container.clientWidth - 2 * MARGIN;
    const height = container.clientHeight - 2 * MARGIN;
    const yearSpan = Math.max(years.max - start, 1);
    return {
        start,
        x: (year) => MARGIN + ((year - start) / yearSpan) * width,
        year: (x) => start + ((x - MARGIN) / width) * yearSpan,
        y: (row) => MARGIN + (row / Math.max(rowCount - 1, 1)) * height,
    };
}
