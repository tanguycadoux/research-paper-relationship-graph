// Look of the graph: node colours and the Cytoscape stylesheet.

function lightness(citedBy, min, max) {
    // Same mapping as the former Plotly graph: from 25% (least cited) to 75%.
    if (max === min) {
        return 50;
    }
    return 25 + ((citedBy - min) * 50) / (max - min);
}

export function citedByRange(nodes) {
    const counts = nodes.filter((n) => !n.data.isSource).map((n) => n.data.citedBy);
    return { min: Math.min(...counts), max: Math.max(...counts) };
}

export function nodeColor(data, citedRange) {
    if (data.isSource) {
        return "lightgreen";
    }
    return `hsl(240, 80%, ${lightness(data.citedBy, citedRange.min, citedRange.max)}%)`;
}

export const STYLE = [
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
