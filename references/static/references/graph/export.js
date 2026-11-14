// The displayed graph as a PNG image (#175): what is on screen, selection included, with
// the year axis above it (on the timeline only: the network has none, #195) and the
// legend below. Both are HTML, outside the canvas of
// Cytoscape: they are drawn again on the image from the page. Without hovering, a dot
// does not say which publication it is: the image names some of them (#289).

// Twice the size on screen (times the pixel density), sharp enough for a slide or a report.
const SCALE = 2;
// Around the legend, and between its items and rows, in pixels (as on the page).
const LEGEND_PADDING = 12;
const ITEM_GAP = 20;
const ROW_GAP = 4;
// Labels of the publications, in pixels of the page (twice as many on the image).
const LABEL_FONT_SIZE = 11;
const LABEL_PADDING = 3;
const LABEL_GAP = 4;

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

// The publications named on the image (#289): with a selection, the selected one and its
// neighbours; otherwise the sources (the publication of the graph, or the corpus). The
// selected publication first, then the most cited: they keep their label when two
// labels would overlap.
function labelledNodes(cy) {
    const selected = cy.nodes(".selected");
    const nodes = selected.nonempty()
        ? selected.union(cy.nodes(".reference-node, .citing-node"))
        : cy.nodes('[role = "source"]');
    return nodes
        .filter((node) => node.data("shortLabel"))
        .sort(
            (a, b) =>
                Number(b.hasClass("selected")) - Number(a.hasClass("selected")) ||
                b.data("citedBy") - a.data("citedBy"),
        );
}

function overlaps(a, b) {
    return a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2;
}

function box(x1, y1, width, height) {
    return { x1, y1, x2: x1 + width, y2: y1 + height };
}

// Where the label of a node may go, in order: right of the node, left, above, below.
function labelPlaces(x, y, radius, width, height) {
    return [
        box(x + radius + LABEL_GAP, y - height / 2, width, height),
        box(x - radius - LABEL_GAP - width, y - height / 2, width, height),
        box(x - width / 2, y - radius - LABEL_GAP - height, width, height),
        box(x - width / 2, y + radius + LABEL_GAP, width, height),
    ];
}

function inView(nodes, width, height) {
    return nodes.filter((node) => {
        const { x, y } = node.renderedPosition();
        return x >= 0 && x <= width && y >= 0 && y <= height;
    });
}

function discs(nodes) {
    return nodes.map((node) => {
        const { x, y } = node.renderedPosition();
        const radius = node.renderedWidth() / 2;
        return box(x - radius, y - radius, 2 * radius, 2 * radius);
    });
}

// The labels placed in the visible graph (width x height, in pixels of the page). Each
// goes in the first place that stays inside and covers no other label nor any node; if
// there is none, in the first that covers no other label nor a labelled node (an
// unlabelled node may then be partly hidden). A label without such a place is left out.
function placeLabels(context, cy, nodes, width, height) {
    const labelled = inView(nodes, width, height);
    const allDiscs = discs(inView(cy.nodes(), width, height));
    const labelledDiscs = discs(labelled);
    const fits = (candidate, obstacles) =>
        candidate.x1 >= 0 &&
        candidate.x2 <= width &&
        candidate.y1 >= 0 &&
        candidate.y2 <= height &&
        !obstacles.some((other) => overlaps(candidate, other));
    const placed = [];
    for (const node of labelled) {
        const text = node.data("shortLabel");
        const { x, y } = node.renderedPosition();
        const labelWidth = context.measureText(text).width + 2 * LABEL_PADDING;
        const labelHeight = LABEL_FONT_SIZE + 2 * LABEL_PADDING;
        const places = labelPlaces(x, y, node.renderedWidth() / 2, labelWidth, labelHeight);
        const place =
            places.find((candidate) => fits(candidate, [...placed, ...allDiscs])) ??
            places.find((candidate) => fits(candidate, [...placed, ...labelledDiscs]));
        if (place) {
            placed.push({ ...place, text });
        }
    }
    return placed;
}

// Each label on a light background, readable over the lines of the graph.
function drawLabels(context, labels, top, color) {
    context.textAlign = "left";
    context.textBaseline = "middle";
    for (const label of labels) {
        context.fillStyle = "rgba(255, 255, 255, 0.85)";
        context.strokeStyle = "rgba(0, 0, 0, 0.15)";
        context.beginPath();
        context.roundRect(label.x1, top + label.y1, label.x2 - label.x1, label.y2 - label.y1, 3);
        context.fill();
        context.stroke();
        context.fillStyle = color;
        context.fillText(label.text, label.x1 + LABEL_PADDING, top + (label.y1 + label.y2) / 2);
    }
}

function download(blob, name) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${name}.png`;
    link.click();
    // Once the download has started.
    setTimeout(() => URL.revokeObjectURL(link.href));
}

async function exportImage(cy, { axis, band, legend }, name) {
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
    const graphTop = axis ? axis.offsetHeight : 0;
    const legendTop = graphTop + cy.height();
    const legendHeight = 2 * LEGEND_PADDING + rows.length * lineHeight + (rows.length - 1) * ROW_GAP;
    // Resizing the canvas resets the context.
    canvas.width = graph.width;
    canvas.height = Math.ceil((legendTop + legendHeight) * scale);
    context.scale(scale, scale);
    context.fillStyle = "white";
    context.fillRect(0, 0, width, legendTop + legendHeight);
    if (axis) {
        drawAxis(context, axis, width);
    }
    context.drawImage(graph, 0, graphTop, width, cy.height());
    drawBand(context, band, cy, graphTop, width);
    context.font = `${LABEL_FONT_SIZE}px ${legendStyle.fontFamily}`;
    const labels = placeLabels(context, cy, labelledNodes(cy), width, cy.height());
    drawLabels(context, labels, graphTop, legendStyle.color);
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

// page: the axis, band (null in the network) and legend elements; viewport: what bindViewport returns.
export function bindExport(cy, page, wrapper, viewport) {
    wrapper
        .querySelector("button")
        .addEventListener("click", () =>
            exportImage(cy, page, fileName(cy, wrapper.dataset.graphExport, viewport)),
        );
}
