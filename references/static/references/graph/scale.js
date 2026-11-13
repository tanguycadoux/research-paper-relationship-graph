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

// Maps years to x and rows to y, each axis scaled to the container independently. With
// undatedColumn, the publications without a date get a column left of the oldest year;
// otherwise (band under the timeline, #288) the timeline starts at the oldest year.
export function makeScale(years, rowCount, container, undatedColumn = true) {
    const span = Math.max(years.max - years.min, 1);
    // The left end of the timeline: the column of the publications without a date, or
    // the oldest year. Undated publications are placed there in the column variant only.
    const undatedYear = undatedColumn
        ? years.min - Math.max(span * UNDATED_OFFSET_RATIO, 1)
        : years.min;
    const width = container.clientWidth - 2 * MARGIN;
    const height = container.clientHeight - 2 * MARGIN;
    const yearSpan = Math.max(years.max - undatedYear, 1);
    return {
        undatedYear,
        x: (year) => MARGIN + ((year - undatedYear) / yearSpan) * width,
        year: (x) => undatedYear + ((x - MARGIN) / width) * yearSpan,
        y: (row) => MARGIN + (row / Math.max(rowCount - 1, 1)) * height,
    };
}
