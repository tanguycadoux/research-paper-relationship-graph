// The displayed graph as a PNG image (#175): what is on screen, selection included, with
// the year axis above it (on the timeline only: the network has none, #195) and the
// legend below. Both are HTML, outside the canvas of
// Cytoscape: they are drawn again on the image from the page. Without hovering, a dot
// does not say which publication it is: the image names some of them (#289,
// export_labels.js).

import { drawNodeLabels } from "./export_labels.js";

// Twice the size on screen (times the pixel density), sharp enough for a slide or a report.
const SCALE = 2;
// Around the legend, and between its items and rows, in pixels (as on the page).
const LEGEND_PADDING = 12;
const ITEM_GAP = 20;
const ROW_GAP = 4;

function loadImage(blob) {
    return new Promise((resolve, reject) => {
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = reject;
        image.src = URL.createObjectURL(blob);
    });
}

function drawAxis(context, axis, width) {
    const style = getComputedStyle(axis);
    const height = axis.offsetHeight;
    context.fillStyle = style.color;
    context.font = `${style.fontSize} ${style.fontFamily}`;
    context.textAlign = "center";
    context.textBaseline = "middle";
    for (const label of axis.children) {
        context.fillText(label.textContent, parseFloat(label.style.left), height / 2);
    }
    // The border under the axis.
    context.fillStyle = style.borderBottomColor;
    context.fillRect(0, height - 1, width, 1);
}

// The band of the publications without a date (#288), when it is on screen: its dashed
// line and its label, at the height graph/band.js gave it.
function drawBand(context, band, cy, top, width) {
    if (!band || band.hidden) {
        return;
    }
    const style = getComputedStyle(band);
    const label = band.firstElementChild;
    const y = top + parseFloat(band.style.top) - cy.container().offsetTop;
    context.strokeStyle = style.borderTopColor;
    context.lineWidth = 1;
    context.setLineDash([3, 3]);
    context.beginPath();
    context.moveTo(0, y + 0.5);
    context.lineTo(width, y + 0.5);
    context.stroke();
    context.setLineDash([]);
    context.font = `${style.fontSize} ${style.fontFamily}`;
    context.fillStyle = style.color;
    context.textAlign = "left";
    context.textBaseline = "top";
    context.fillText(label.textContent, label.offsetLeft + 4, y + 4);
}

// The outline of a swatch (the gathered duplicates of a coauthorship graph, #419), or null.
function swatchOutline(style) {
    const width = parseFloat(style.outlineWidth);
    if (style.outlineStyle === "none" || !width) {
        return null;
    }
    return { width, offset: parseFloat(style.outlineOffset) || 0, color: style.outlineColor };
}

// The border of a round swatch (a publication of level 2, hollow, #451), or null.
function swatchBorder(style) {
    const width = parseFloat(style.borderTopWidth);
    return width ? { width, color: style.borderTopColor } : null;
}

// An icon of the legend (the mark of the references to identify, #452): drawn as an image,
// loaded before the legend is drawn (loadLegendImages).
function svgPart(svg, style) {
    const box = svg.getBoundingClientRect();
    return {
        svg,
        width: box.width,
        height: box.height,
        before: parseFloat(style.marginLeft),
        margin: parseFloat(style.marginRight),
    };
}

async function loadLegendImages(rows) {
    const parts = rows.flatMap((row) => row.flatMap((item) => item.parts)).filter((part) => part.svg);
    for (const part of parts) {
        const source = new XMLSerializer().serializeToString(part.svg);
        part.image = await loadImage(new Blob([source], { type: "image/svg+xml" }));
        URL.revokeObjectURL(part.image.src);
    }
}

// Each item of the legend as a list of parts: texts, and the swatches (dots and lines)
// with their size and colour.
function legendItems(legend) {
    return [...legend.children].map((item) => {
        const parts = [...item.childNodes].flatMap((node) => {
            if (node.nodeType === Node.TEXT_NODE) {
                const text = node.textContent.replace(/\s+/g, " ");
                return text.trim() ? [{ text }] : [];
            }
            if (node.nodeType !== Node.ELEMENT_NODE) {
                return [];
            }
            const style = getComputedStyle(node);
            if (node instanceof SVGSVGElement) {
                return [svgPart(node, style)];
            }
            return [
                {
                    width: node.offsetWidth,
                    height: node.offsetHeight,
                    before: parseFloat(style.marginLeft),
                    margin: parseFloat(style.marginRight),
                    color: style.backgroundColor,
                    round: style.borderRadius !== "0px",
                    outline: swatchOutline(style),
                    border: swatchBorder(style),
                },
            ];
        });
        const first = parts[0];
        const last = parts.at(-1);
        if (first.text) {
            first.text = first.text.trimStart();
        }
        if (last.text) {
            last.text = last.text.trimEnd();
        }
        return parts;
    });
}

function partWidth(context, part) {
    if (part.text) {
        return context.measureText(part.text).width;
    }
    return part.before + part.width + part.margin;
}

// A dot or a line of the legend, centred on the height middle, from x.
function drawSwatch(context, part, x, middle) {
    context.fillStyle = part.color;
    context.beginPath();
    if (part.round) {
        context.arc(x + part.width / 2, middle, part.width / 2, 0, 2 * Math.PI);
    } else {
        context.rect(x, middle - part.height / 2, part.width, part.height);
    }
    context.fill();
    const border = part.border;
    if (border && part.round) {
        context.strokeStyle = border.color;
        context.lineWidth = border.width;
        context.beginPath();
        context.arc(x + part.width / 2, middle, (part.width - border.width) / 2, 0, 2 * Math.PI);
        context.stroke();
    }
    const outline = part.outline;
    if (outline && part.round) {
        const radius = part.width / 2 + outline.offset + outline.width / 2;
        context.strokeStyle = outline.color;
        context.lineWidth = outline.width;
        context.beginPath();
        context.arc(x + part.width / 2, middle, radius, 0, 2 * Math.PI);
        context.stroke();
    }
}

// Items placed in rows as wide as the graph, like the wrapping list of the page.
function layoutLegend(context, items, width) {
    const rows = [[]];
    let x = LEGEND_PADDING;
    for (const parts of items) {
        const itemWidth = parts.reduce((sum, part) => sum + partWidth(context, part), 0);
        if (x > LEGEND_PADDING && x + itemWidth > width - LEGEND_PADDING) {
            rows.push([]);
            x = LEGEND_PADDING;
        }
        rows.at(-1).push({ x, parts });
        x += itemWidth + ITEM_GAP;
    }
    return rows;
}

function drawLegend(context, rows, style, top, lineHeight) {
    context.textAlign = "left";
    context.textBaseline = "middle";
    rows.forEach((row, index) => {
        const middle = top + LEGEND_PADDING + index * (lineHeight + ROW_GAP) + lineHeight / 2;
        for (const { x: start, parts } of row) {
            let x = start;
            for (const part of parts) {
                if (part.text) {
                    context.fillStyle = style.color;
                    context.fillText(part.text, x, middle);
                } else if (part.image) {
                    context.drawImage(part.image, x + part.before, middle - part.height / 2, part.width, part.height);
                } else {
                    drawSwatch(context, part, x + part.before, middle);
                }
                x += partWidth(context, part);
            }
        }
    });
}

function download(blob, name) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${name}.png`;
    link.click();
    // Once the download has started.
    setTimeout(() => URL.revokeObjectURL(link.href));
}

async function graphImage(cy) {
    const graph = await loadImage(
        await cy.png({ output: "blob-promise", scale: SCALE, bg: "white" }),
    );
    URL.revokeObjectURL(graph.src);
    return graph;
}

// The legend laid out for the image, as wide as the graph: its style, font, rows, height
// of a line and whole height.
function legendLayout(context, legend, width) {
    const style = getComputedStyle(legend);
    const font = `${style.fontSize} ${style.fontFamily}`;
    context.font = font;
    const rows = layoutLegend(context, legendItems(legend), width);
    const lineHeight = parseFloat(style.lineHeight);
    const height = 2 * LEGEND_PADDING + rows.length * lineHeight + (rows.length - 1) * ROW_GAP;
    return { style, font, rows, lineHeight, height };
}

async function exportImage(cy, { axis, band, legend }, name) {
    const graph = await graphImage(cy);
    // Everything is drawn in pixels of the page. cy.png also multiplies by the pixel
    // density of the screen: the image is drawn at the scale actually produced.
    const width = cy.width();
    const scale = graph.width / width;
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    const key = legendLayout(context, legend, width);
    await loadLegendImages(key.rows);
    const graphTop = axis ? axis.offsetHeight : 0;
    const legendTop = graphTop + cy.height();
    // Resizing the canvas resets the context.
    canvas.width = graph.width;
    canvas.height = Math.ceil((legendTop + key.height) * scale);
    context.scale(scale, scale);
    context.fillStyle = "white";
    context.fillRect(0, 0, width, legendTop + key.height);
    if (axis) {
        drawAxis(context, axis, width);
    }
    context.drawImage(graph, 0, graphTop, width, cy.height());
    drawBand(context, band, cy, graphTop, width);
    drawNodeLabels(context, cy, { top: graphTop, fontFamily: key.style.fontFamily, color: key.style.color });
    context.font = key.font;
    drawLegend(context, key.rows, key.style, legendTop, key.lineHeight);
    canvas.toBlob((blob) => download(blob, name), "image/png");
}

// The file tells what the image shows: the graph (from the wrapper of the button), then
// the selected publication, or a zoomed or moved view.
function fileName(cy, base, viewport) {
    const selected = cy.nodes(".selected");
    if (selected.nonempty()) {
        return `${base}-selection-${selected.id()}`;
    }
    return viewport.showsAll() ? base : `${base}-zoom`;
}

// page: the axis, band (null in the network) and legend elements; viewport: what bindViewport returns.
export function bindExport(cy, page, wrapper, viewport) {
    wrapper
        .querySelector("button")
        .addEventListener("click", () =>
            exportImage(cy, page, fileName(cy, wrapper.dataset.graphExport, viewport)),
        );
}
