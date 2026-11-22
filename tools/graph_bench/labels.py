"""
Check of the labels of the exported image (#421, graph/export_labels.js), in headless
Chrome: a node near the right edge of the image keeps its label inside the image, moved
to its left or shortened with « … ».

    DJANGO_DEBUG=1 python manage.py runserver 8120          # any base
    python tools/graph_bench/labels.py http://127.0.0.1:8120

Node is not needed: the module runs in the page, served by Django like on the graphs.
Exits with 1 if a case fails.
"""

import argparse
import json
import sys
import time

from bench import PORT, start_chrome

# A fake Cytoscape: the nodes of the frame, each with its name, position and diameter.
CASES = """
const node = (label, x, y, size = 10) => ({
    data: (key) => (key === "shortLabel" ? label : undefined),
    renderedPosition: () => ({ x, y }),
    renderedWidth: () => size,
});
const long = "RFQ NEWGAIN: RF and Thermomechanical";
const cases = {
    // Right of the node there is no room: the label goes to its left.
    "left of a node at the right edge": [400, [node(long, 395, 50)]],
    // Neither right nor left is wide enough: shortened, with « … ».
    "shortened in a narrow frame": [120, [node(long, 115, 50)]],
    // Too long for either side, and too close to the top to go above: shortened on the
    // right, where there is the most room.
    "shortened on the right": [300, [node(long, 200, 20)]],
};
const context = document.createElement("canvas").getContext("2d");
context.font = "11px sans-serif";
const results = {};
for (const [name, [width, nodes]] of Object.entries(cases)) {
    const cy = { nodes: () => nodes };
    const labels = placeLabels(context, cy, [nodes[0]], width, 100);
    results[name] = labels.map((label) => ({
        text: label.text,
        x1: label.x1,
        x2: label.x2,
        textWidth: context.measureText(label.text).width,
        width,
    }));
}
return results;
"""


def check(results):
    failures = []
    for name, labels in results.items():
        if len(labels) != 1:
            failures.append(f"{name}: {len(labels)} labels")
            continue
        label = labels[0]
        inside = label["x1"] >= 0 and label["x2"] <= label["width"]
        if not inside or label["textWidth"] > label["x2"] - label["x1"]:
            failures.append(f"{name}: out of the image {label}")
        if name.startswith("shortened") and not label["text"].endswith("…"):
            failures.append(f"{name}: not shortened {label}")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("server")
    parser.add_argument("--devtools-port", type=int, default=PORT)
    args = parser.parse_args()
    chrome, tools = start_chrome(800, 600, args.devtools_port)
    try:
        # Any page of the server: the module is imported from its origin.
        tools.call("Page.navigate", url=f"{args.server}/static/references/graph/export_labels.js")
        time.sleep(1)
        results = tools.evaluate(
            "(async () => { const { placeLabels } = await import("
            "'/static/references/graph/export_labels.js');"
            f"{CASES} }})()"
        )
    finally:
        chrome.kill()
    print(json.dumps(results, indent=2, ensure_ascii=False))
    failures = check(results)
    for failure in failures:
        print("FAIL", failure)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
