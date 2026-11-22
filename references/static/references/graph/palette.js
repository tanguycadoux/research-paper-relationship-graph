// Colours of the graphs (#470), in OKLCH: the hue says the role of a node, its lightness
// its level. Four groups: the centre (the publication of the graph, the publications of
// the corpus, the author), the past (the publications cited), the future (those citing),
// and the neutral grey of the other publications of the graph of the base (#477). Their
// hue and chroma are the theme variables of assets/css/source.css (--color-graph-source,
// -cited, -citing, -base, written oklch(L C H)), shared with the legend;
// the lightness of each level is computed here, the same curve as the legend's swatches.
// Cytoscape does not read oklch(): the colours are converted to sRGB, the chroma lowered
// until the colour fits (the hue and the lightness are kept).

// L(n) = CEILING - (CEILING - FLOOR) * RATIO^n: 0.6 for the centre (level 0), 0.70 for
// level 1, 0.767 for level 2, towards 0.9 and never white.
const FLOOR = 0.6;
const CEILING = 0.9;
const RATIO = 2 / 3;
// The contour of a node: its colour, this much darker.
const CONTOUR_DROP = 0.2;

const GROUPS = { source: "source", cited: "cited", citing: "citing", base: "base" };

export function levelLightness(level) {
    return CEILING - (CEILING - FLOOR) * RATIO ** Math.max(0, level);
}

// [l, c, h] of an oklch() text, or null.
function parseOklch(text) {
    const match = /oklch\(\s*([\d.]+%?)\s+([\d.]+)\s+([\d.]+)/i.exec(text);
    if (!match) {
        return null;
    }
    const l = match[1].endsWith("%") ? parseFloat(match[1]) / 100 : parseFloat(match[1]);
    return [l, parseFloat(match[2]), parseFloat(match[3])];
}

// Linear sRGB of an OKLCH colour (Björn Ottosson's matrices).
function linearRgb(l, c, h) {
    const a = c * Math.cos((h * Math.PI) / 180);
    const b = c * Math.sin((h * Math.PI) / 180);
    const l1 = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
    const m1 = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
    const s1 = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
    return [
        4.0767416621 * l1 - 3.3077115913 * m1 + 0.2309699292 * s1,
        -1.2684380046 * l1 + 2.6097574011 * m1 - 0.3413193965 * s1,
        -0.0041960863 * l1 - 0.7034186147 * m1 + 1.707614701 * s1,
    ];
}

const inGamut = (rgb) => rgb.every((x) => x >= -1e-4 && x <= 1 + 1e-4);

function encode(x) {
    const v = Math.min(1, Math.max(0, x));
    const srgb = v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055;
    return Math.round(srgb * 255)
        .toString(16)
        .padStart(2, "0");
}

// The hex colour of l, c, h; c lowered (bisection) while the colour is outside sRGB.
export function oklchToHex(l, c, h) {
    let rgb = linearRgb(l, c, h);
    if (!inGamut(rgb)) {
        let [low, high] = [0, c];
        for (let i = 0; i < 20; i++) {
            const mid = (low + high) / 2;
            if (inGamut(linearRgb(l, mid, h))) {
                low = mid;
            } else {
                high = mid;
            }
        }
        rgb = linearRgb(l, low, h);
    }
    return `#${rgb.map(encode).join("")}`;
}

// A colour of the theme as Cytoscape reads it: an oklch() one converted, others as they are.
export function cssColor(text) {
    const lch = parseOklch(text);
    return lch ? oklchToHex(...lch) : text;
}

// [chroma, hue] of each group, read once from the theme.
let tones = null;
function tone(group) {
    if (!tones) {
        const style = getComputedStyle(document.documentElement);
        tones = Object.fromEntries(
            Object.keys(GROUPS).map((name) => {
                const [, c, h] = parseOklch(style.getPropertyValue(`--color-graph-${name}`)) ?? [0, 0, 0];
                return [name, [c, h]];
            }),
        );
    }
    return tones[group] ?? tones.cited;
}

const cache = new Map();

// The colour of a group at a level; contour: the darker one of its outline.
export function groupColor(group, level, contour = false) {
    const key = `${group}:${level}:${contour}`;
    if (!cache.has(key)) {
        const [c, h] = tone(group);
        const l = levelLightness(level) - (contour ? CONTOUR_DROP : 0);
        cache.set(key, oklchToHex(l, c, h));
    }
    return cache.get(key);
}

// The group of a node by its role (services/display/graph.py, author_graph.py): the
// centre, the future, the neutral publications of the graph of the base, or the past
// (cited, and the « other » authors).
export function nodeGroup(node) {
    return GROUPS[node.data("role")] ?? "cited";
}

// Its level: 0 for the centre, the level of the data (#451), else 1.
export function nodeLevel(node) {
    if (node.data("role") === "source") {
        return 0;
    }
    return node.data("level") ?? 1;
}
