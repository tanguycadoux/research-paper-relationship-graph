// The displayed graph as a PNG image (#175): what is on screen, selection included, with
// the year axis above it and the legend below. Both are HTML, outside the canvas of
// Cytoscape: they are drawn again on the image from the page.

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

// Each item of the legend as a list of parts: texts, and the swatches (dots and lines)
// with their size and colour.
function legendItems(legend) {
    return [...legend.children].map((item) => {
        const parts = [...item.childNodes].flatMap((node) => {
            if (node.nodeType === Node.TEXT_NODE) {
                const text = node.textContent.replace(/\s+/g, " ");
                return text.trim() ? [{ text }] : [];
            }
            const style = getComputedStyle(node);
            return [
                {
                    width: node.offsetWidth,
                    height: node.offsetHeight,
                    margin: parseFloat(style.marginRight),
                    color: style.backgroundColor,
                    round: style.borderRadius !== "0px",
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
    return part.text ? context.measureText(part.text).width : part.width + part.margin;
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
                } else {
                    context.fillStyle = part.color;
                    context.beginPath();
                    if (part.round) {
                        context.arc(x + part.width / 2, middle, part.width / 2, 0, 2 * Math.PI);
                    } else {
                        context.rect(x, middle - part.height / 2, part.width, part.height);
                    }
                    context.fill();
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

async function exportImage(cy, { axis, legend }, name) {
    const graph = await loadImage(
        await cy.png({ output: "blob-promise", scale: SCALE, bg: "white" }),
    );
    URL.revokeObjectURL(graph.src);
    // Everything is drawn in pixels of the page. cy.png also multiplies by the pixel
    // density of the screen: the image is drawn at the scale actually produced.
    const width = cy.width();
    const scale = graph.width / width;
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    const legendStyle = getComputedStyle(legend);
    const font = `${legendStyle.fontSize} ${legendStyle.fontFamily}`;
    context.font = font;
    const rows = layoutLegend(context, legendItems(legend), width);
    const lineHeight = parseFloat(legendStyle.lineHeight);
    const graphTop = axis.offsetHeight;
    const legendTop = graphTop + cy.height();
    const legendHeight = 2 * LEGEND_PADDING + rows.length * lineHeight + (rows.length - 1) * ROW_GAP;
    // Resizing the canvas resets the context.
    canvas.width = graph.width;
    canvas.height = Math.ceil((legendTop + legendHeight) * scale);
    context.scale(scale, scale);
    context.fillStyle = "white";
    context.fillRect(0, 0, width, legendTop + legendHeight);
    drawAxis(context, axis, width);
    context.drawImage(graph, 0, graphTop, width, cy.height());
    context.font = font;
    drawLegend(context, rows, legendStyle, legendTop, lineHeight);
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

// page: the axis and legend elements; viewport: what bindViewport returns.
export function bindExport(cy, page, wrapper, viewport) {
    wrapper
        .querySelector("button")
        .addEventListener("click", () =>
            exportImage(cy, page, fileName(cy, wrapper.dataset.graphExport, viewport)),
        );
}
