// The displayed graph as a PNG image (#175): what is on screen, selection included, with
// the year axis above it. The axis is HTML, outside the canvas of Cytoscape: its labels
// are drawn again on the image, where the page shows them.

// Twice the size on screen (times the pixel density), sharp enough for a slide or a report.
const SCALE = 2;

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
    return height;
}

function download(blob, name) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${name}.png`;
    link.click();
    // Once the download has started.
    setTimeout(() => URL.revokeObjectURL(link.href));
}

async function exportImage(cy, axis, name) {
    const graph = await loadImage(
        await cy.png({ output: "blob-promise", scale: SCALE, bg: "white" }),
    );
    URL.revokeObjectURL(graph.src);
    // cy.png also multiplies by the pixel density of the screen: the axis follows the
    // scale of the image actually produced.
    const width = cy.width();
    const scale = graph.width / width;
    const canvas = document.createElement("canvas");
    canvas.width = graph.width;
    canvas.height = Math.round(axis.offsetHeight * scale) + graph.height;
    const context = canvas.getContext("2d");
    context.fillStyle = "white";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.scale(scale, scale);
    const top = drawAxis(context, axis, width);
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.drawImage(graph, 0, Math.round(top * scale));
    canvas.toBlob((blob) => download(blob, name), "image/png");
}

// The wrapper of the button carries the file name, without extension.
export function bindExport(cy, axis, wrapper) {
    wrapper
        .querySelector("button")
        .addEventListener("click", () => exportImage(cy, axis, wrapper.dataset.graphExport));
}
