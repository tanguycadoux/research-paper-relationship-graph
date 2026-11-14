"""
Frames of the drawing of the citation graphs while they move (#202): zoom with the mouse
wheel, drag of the view, animation of a selection, hover of publications. Real mouse
input is sent through the DevTools protocol (Cytoscape only takes its shortcuts of a
moving view on real gestures), and the intervals between frames are recorded in the page
(frames.js). Uses the DevTools client of bench.py, on its own port.

    DJANGO_DEBUG=1 python manage.py runserver 8140          # on a copy of the base
    python tools/graph_bench/frames.py http://127.0.0.1:8140 --out /tmp/frames \\
        --page /graph/ --synthetic 500 1000 2000 --mount-page /publications/12/graph/

For each graph and each gesture: the median, 90th percentile and longest interval between
frames, in milliseconds, and the number of frames over 50 ms. Screenshots during and after
a zoom, and during the animation of a selection.
"""

import argparse
import json
import statistics
import time
from pathlib import Path

import bench

HERE = Path(__file__).resolve().parent
# Between two wheel or mouse events: about one per frame.
EVENT_GAP = 0.02
# After a gesture: the last frames, sizes evaluated again included.
SETTLE = 0.5


def mouse(tools, kind, point, **extra):
    tools.call("Input.dispatchMouseEvent", type=kind, x=point["x"], y=point["y"], **extra)


def call(tools, expression):
    return tools.evaluate(f"window.graphFrames.{expression}")


def wheel_zoom(tools, points, out, prefix):
    centre = points["centre"]
    mouse(tools, "mouseMoved", centre)
    call(tools, "start()")
    for i in range(30):
        mouse(tools, "mouseWheel", centre, deltaX=0, deltaY=-60)
        time.sleep(EVENT_GAP)
        if out and i == 15:
            tools.screenshot(f"{out}/{prefix}-zoom-during.png")
    time.sleep(SETTLE)
    result = call(tools, "stop()")
    if out:
        tools.screenshot(f"{out}/{prefix}-zoom-after.png")
    return result


def drag(tools, points):
    start = points["empty"]
    mouse(tools, "mouseMoved", start)
    mouse(tools, "mousePressed", start, button="left", buttons=1, clickCount=1)
    call(tools, "start()")
    for i in range(1, 31):
        mouse(tools, "mouseMoved", {"x": start["x"] - 6 * i, "y": start["y"] + 2 * i}, buttons=1)
        time.sleep(EVENT_GAP)
    end = {"x": start["x"] - 180, "y": start["y"] + 60}
    mouse(tools, "mouseReleased", end, button="left", buttons=0, clickCount=1)
    time.sleep(SETTLE)
    return call(tools, "stop()")


def selection(tools, out, prefix):
    call(tools, "start()")
    selected = call(tools, "select()")
    if out:
        time.sleep(0.12)
        tools.screenshot(f"{out}/{prefix}-selection-during.png")
    time.sleep(0.8)
    result = call(tools, "stop()")
    if out:
        tools.screenshot(f"{out}/{prefix}-selection-after.png")
    call(tools, "deselect()")
    time.sleep(0.8)
    return {**result, "selected": selected["label"], "degree": selected["degree"]}


def hover(tools, points):
    call(tools, "start()")
    for point in points["hover"]:
        mouse(tools, "mouseMoved", point)
        time.sleep(0.05)
    time.sleep(SETTLE)
    mouse(tools, "mouseMoved", {"x": 5, "y": 5})
    return call(tools, "stop()")


def gestures(tools, out, prefix):
    """One round of the four gestures, each starting from the view of the whole graph."""
    points = call(tools, "points()")
    result = {"nodes": points["nodes"], "edges": points["edges"]}
    result["zoom"] = wheel_zoom(tools, points, out, prefix)
    # Dragging needs room to move: the view stays zoomed in.
    result["drag"] = drag(tools, call(tools, "points()"))
    call(tools, "showAll()")
    time.sleep(SETTLE)
    result["selection"] = selection(tools, out, prefix)
    call(tools, "showAll()")
    time.sleep(SETTLE)
    result["hover"] = hover(tools, call(tools, "points()"))
    return result


def merged(rounds):
    """Medians over the rounds, gesture by gesture."""
    result = {key: rounds[0][key] for key in ("nodes", "edges")}
    for gesture in ("zoom", "drag", "selection", "hover"):
        result[gesture] = {
            key: statistics.median(r[gesture][key] for r in rounds)
            for key in ("median", "p90", "max", "slow")
        }
    return result


def arguments():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("server")
    parser.add_argument("--out", help="screenshots, taken during the first round")
    parser.add_argument("--page", action="append", default=[])
    parser.add_argument("--session", help="cookie sessionid, for the pages of a corpus")
    parser.add_argument("--synthetic", type=int, nargs="*", default=[])
    parser.add_argument("--mount-page", help="a light page with a graph, for the synthetic ones")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--port", type=int, default=9440, help="DevTools port of Chrome")
    parser.add_argument("--width", type=int, default=1400)
    parser.add_argument("--height", type=int, default=1000)
    return parser.parse_args()


def one_round(tools, args, script, kind, target, shots):
    """Load the graph (a page, or a synthetic one mounted in a page) and run the gestures."""
    bench.load(tools, args.server + (target if kind == "page" else args.mount_page))
    tools.evaluate(script)
    if kind == "synthetic":
        options = {"nodes": target, "components": 4, "undated": 0.02, "seed": 7}
        tools.evaluate(f"window.graphFrames.mount({json.dumps(options)})")
        time.sleep(SETTLE)
    name = (
        str(target).strip("/").replace("/", "-") or "home"
        if kind == "page"
        else f"synthetic-{target}"
    )
    return gestures(tools, shots, name)


def main():
    args = arguments()
    if args.out:
        Path(args.out).mkdir(parents=True, exist_ok=True)
    bench.PORT = args.port
    script = (HERE / "frames.js").read_text()
    chrome, tools = bench.start_chrome(args.width, args.height)
    try:
        if args.session:
            tools.call("Network.setCookie", name="sessionid", value=args.session, url=args.server)
        targets = [("page", path) for path in args.page]
        targets += [("synthetic", count) for count in args.synthetic]
        for kind, target in targets:
            rounds = [
                one_round(tools, args, script, kind, target, args.out if r == 0 else None)
                for r in range(args.repeat)
            ]
            print(json.dumps({kind: target, **merged(rounds)}), flush=True)
    finally:
        chrome.terminate()


if __name__ == "__main__":
    main()
