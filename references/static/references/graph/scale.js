// Dates and the scale of the timeline: x follows the publication date, y the row.

export const MARGIN = 40;
const UNDATED_OFFSET_RATIO = 0.05;

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

// Maps years to x and rows to y, each axis scaled to the container independently.
export function makeScale(years, rowCount, container) {
    const span = Math.max(years.max - years.min, 1);
    const undatedYear = years.min - Math.max(span * UNDATED_OFFSET_RATIO, 1);
    const width = container.clientWidth - 2 * MARGIN;
    const height = container.clientHeight - 2 * MARGIN;
    const yearSpan = years.max - undatedYear;
    return {
        undatedYear,
        x: (year) => MARGIN + ((year - undatedYear) / yearSpan) * width,
        year: (x) => undatedYear + ((x - MARGIN) / width) * yearSpan,
        y: (row) => MARGIN + (row / Math.max(rowCount - 1, 1)) * height,
    };
}
