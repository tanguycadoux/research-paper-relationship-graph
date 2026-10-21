// Citation graph: publications placed on a timeline (x = publication date).
(function () {
    "use strict";

    const MARGIN = 40;
    const TICK_ROW_OFFSET = 30;
    const MAX_TICKS = 12;
    const TICK_STEPS = [1, 2, 5, 10, 20, 25, 50, 100];
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
        const height = container.clientHeight - 2 * MARGIN - TICK_ROW_OFFSET;
        return {
            undatedYear,
            x: (year) => MARGIN + ((year - undatedYear) / (years.max - undatedYear)) * width,
            y: (row) => MARGIN + TICK_ROW_OFFSET + (row / Math.max(rowCount - 1, 1)) * height,
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

    function tickStep(span) {
        return TICK_STEPS.find((step) => span / step <= MAX_TICKS) || TICK_STEPS.at(-1);
    }

    function tickNode(label, year, scale) {
        return {
            data: { id: `tick-${label}`, label: String(label) },
            position: { x: scale.x(year), y: MARGIN },
            classes: "tick",
            selectable: false,
            grabbable: false,
        };
    }

    function yearTicks(years, scale) {
        const step = tickStep(years.max - years.min);
        const ticks = [tickNode("Non daté", scale.undatedYear, scale)];
        for (let year = Math.ceil(years.min / step) * step; year <= years.max; year += step) {
            ticks.push(tickNode(year, year, scale));
        }
        return ticks;
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
            selector: "node.tick",
            style: {
                label: "data(label)",
                "background-opacity": 0,
                "border-width": 0,
                color: "dimgray",
                events: "no",
            },
        },
        {
            selector: "edge",
            style: { width: 1.5, "line-color": "black", "curve-style": "straight" },
        },
    ];

    function bindInteractions(cy) {
        cy.on("mouseover", "node[url]", (event) => event.target.addClass("hovered"));
        cy.on("mouseout", "node[url]", (event) => event.target.removeClass("hovered"));
        cy.on("tap", "node[url]", (event) => {
            window.location.href = event.target.data("url");
        });
    }

    function render() {
        const container = document.getElementById("citation-graph");
        const graph = JSON.parse(document.getElementById("citation-graph-data").textContent);
        const years = yearRange(graph.nodes);
        const scale = makeScale(years, graph.nodes.length, container);
        const cy = cytoscape({
            container,
            elements: [...yearTicks(years, scale), ...placeNodes(graph.nodes, scale), ...graph.edges],
            style: STYLE,
            // Axes are already scaled to the container: fitting only corrects small offsets.
            layout: { name: "preset", fit: true, padding: MARGIN / 2 },
            autoungrabify: true,
        });
        bindInteractions(cy);
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
