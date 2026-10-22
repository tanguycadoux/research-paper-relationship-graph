// Citation graph: publications placed on a timeline (x = publication date).
(function () {
    "use strict";

    const MARGIN = 40;
    // Minimum distance, in pixels, between two labels of the year axis: the step
    // depends on the zoom, not on the visible span, so labels never pile up.
    const MIN_LABEL_SPACING = 60;
    const TICK_STEPS = [1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000];
    const UNDATED_OFFSET_RATIO = 0.05;

    function fractionalYear(isoDate) {
        const date = new Date(isoDate);
        const start = Date.UTC(date.getUTCFullYear(), 0, 1);
        const end = Date.UTC(date.getUTCFullYear() + 1, 0, 1);
        return date.getUTCFullYear() + (date.getTime() - start) / (end - start);
    }

    function yearRange(nodes) {
        const years = nodes.filter((n) => n.data.date).map((n) => fractionalYear(n.data.date));
        if (years.length === 0) {
            const now = new Date().getFullYear();
            return { min: now, max: now };
        }
        return { min: Math.min(...years), max: Math.max(...years) };
    }

    function lightness(citedBy, min, max) {
        // Same mapping as the former Plotly graph: from 25% (least cited) to 75%.
        if (max === min) {
            return 50;
        }
        return 25 + ((citedBy - min) * 50) / (max - min);
    }

    function nodeColor(data, citedRange) {
        if (data.isSource) {
            return "lightgreen";
        }
        return `hsl(240, 80%, ${lightness(data.citedBy, citedRange.min, citedRange.max)}%)`;
    }

    function citedByRange(nodes) {
        const counts = nodes.filter((n) => !n.data.isSource).map((n) => n.data.citedBy);
        return { min: Math.min(...counts), max: Math.max(...counts) };
    }

    // Maps years to x and rows to y, each axis scaled to the container independently.
    function makeScale(years, rowCount, container) {
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

    function placeNodes(nodes, scale) {
        const yearOf = (n) => (n.data.date ? fractionalYear(n.data.date) : scale.undatedYear);
        const sorted = [...nodes].sort((a, b) => yearOf(a) - yearOf(b));
        const citedRange = citedByRange(nodes);
        return sorted.map((n, row) => ({
            data: { ...n.data, color: nodeColor(n.data, citedRange) },
            position: { x: scale.x(yearOf(n)), y: scale.y(row) },
        }));
    }

    function tickStep(pixelsPerYear) {
        return (
            TICK_STEPS.find((step) => step * pixelsPerYear >= MIN_LABEL_SPACING) ||
            TICK_STEPS.at(-1)
        );
    }

    // The year axis is an HTML strip above the canvas: it stays in view, and its ticks
    // follow the horizontal zoom and pan of the graph (#62).
    function axisLabel(text, x) {
        const label = document.createElement("span");
        label.className = "absolute top-1/2 -translate-x-1/2 -translate-y-1/2 whitespace-nowrap";
        label.style.left = `${x}px`;
        label.textContent = String(text);
        return label;
    }

    function drawYearAxis(axis, cy, years, scale) {
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

    const STYLE = [
        {
            selector: "node",
            style: {
                width: 20,
                height: 20,
                "background-color": "data(color)",
                "border-width": 1.5,
                "border-color": "black",
            },
        },
        {
            selector: "node.hovered",
            style: {
                label: "data(label)",
                "font-size": 12,
                "text-wrap": "wrap",
                "text-max-width": 300,
                "text-background-color": "white",
                "text-background-opacity": 0.9,
                "z-index": 10,
            },
        },
        {
            selector: "edge",
            style: { width: 1.5, "line-color": "black", "curve-style": "straight" },
        },
        // Selection (#61): the publication, its references and the publications citing it.
        { selector: ".faded", style: { opacity: 0.15 } },
        { selector: "node.selected", style: { "border-width": 4 } },
        { selector: "edge.reference", style: { width: 3, "line-color": "#1d4ed8", "z-index": 5 } },
        { selector: "edge.citing", style: { width: 3, "line-color": "#b45309", "z-index": 5 } },
    ];

    // French plural: 0 and 1 take the singular.
    function publications(count) {
        return `${count} publication${count > 1 ? "s" : ""}`;
    }

    function fillCard(card, data, referenceCount, citingCount) {
        const field = (name) => card.querySelector(`[data-card="${name}"]`);
        const showRow = (name, visible) => {
            card.querySelector(`[data-card-row="${name}"]`).hidden = !visible;
        };
        field("title").textContent = data.label;
        const etAl = data.authorCount > data.authors.length ? " et al." : "";
        field("authors").textContent = data.authors.join(", ") + etAl;
        showRow("authors", data.authorCount > 0);
        field("year").textContent = data.date ? data.date.slice(0, 4) : "";
        showRow("year", Boolean(data.date));
        const doiLink = field("doi").querySelector("a");
        doiLink.href = `https://doi.org/${data.doi}`;
        doiLink.firstChild.nodeValue = data.doi;
        showRow("doi", Boolean(data.doi));
        field("isbn").textContent = data.isbn;
        showRow("isbn", Boolean(data.isbn));
        field("references").textContent = `cite ${publications(referenceCount)}`;
        field("citing").textContent = `citée par ${publications(citingCount)}`;
        field("cited-by").textContent = `citée par ${publications(data.citedBy)}`;
        card.querySelector("[data-card-link] a").href = data.url;
        card.hidden = false;
    }

    function clearSelection(cy, card) {
        cy.elements().removeClass("faded selected reference citing");
        card.hidden = true;
    }

    // An edge goes from the citing publication to the cited one.
    function selectNode(cy, node, card) {
        clearSelection(cy, card);
        const references = node.outgoers("edge");
        const citing = node.incomers("edge");
        const kept = node.union(references).union(references.targets());
        cy.elements().not(kept.union(citing).union(citing.sources())).addClass("faded");
        node.addClass("selected");
        references.addClass("reference");
        citing.addClass("citing");
        fillCard(card, node.data(), references.length, citing.length);
    }

    function bindInteractions(cy, card) {
        cy.on("mouseover", "node[url]", (event) => event.target.addClass("hovered"));
        cy.on("mouseout", "node[url]", (event) => event.target.removeClass("hovered"));
        cy.on("tap", "node[url]", (event) => selectNode(cy, event.target, card));
        cy.on("tap", (event) => {
            if (event.target === cy) {
                clearSelection(cy, card);
            }
        });
        cy.on("dbltap", "node[url]", (event) => {
            window.location.href = event.target.data("url");
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                clearSelection(cy, card);
            }
        });
        card.querySelector("[data-card-close] button").addEventListener("click", () =>
            clearSelection(cy, card),
        );
    }

    function render() {
        const container = document.getElementById("citation-graph");
        const graph = JSON.parse(document.getElementById("citation-graph-data").textContent);
        const years = yearRange(graph.nodes);
        const scale = makeScale(years, graph.nodes.length, container);
        const cy = cytoscape({
            container,
            elements: [...placeNodes(graph.nodes, scale), ...graph.edges],
            style: STYLE,
            // Axes are already scaled to the container: fitting only corrects small offsets.
            layout: { name: "preset", fit: true, padding: MARGIN / 2 },
            autoungrabify: true,
            autounselectify: true,
        });
        bindInteractions(cy, document.getElementById("citation-graph-card"));
        const axis = document.getElementById("citation-graph-axis");
        const drawAxis = () => drawYearAxis(axis, cy, years, scale);
        cy.on("viewport", drawAxis);
        drawAxis();
        keepFitted(cy, container);
    }

    function keepFitted(cy, container) {
        // The container may change size after initialization (page layout, window resize).
        new ResizeObserver(() => {
            cy.resize();
            cy.fit(undefined, MARGIN / 2);
        }).observe(container);
    }

    render();
})();
