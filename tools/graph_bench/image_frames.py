"""
Frames of the page that browses the image of a large graph (#453,
graph/image_viewer.js): loading, zoom with the mouse wheel, drag of the view, hover of
nodes of the image and of rows of the list, with real mouse input sent through DevTools
like frames.py, whose recording of the frames (frames.js) it reuses.

    DJANGO_DEBUG=1 python manage.py runserver 8140          # a base with its images computed
    python tools/graph_bench/image_frames.py http://127.0.0.1:8140 --kind authors --out /tmp/f

For each gesture: the median, 90th percentile and longest interval between frames, in
milliseconds, and the number of frames over 50 ms; median of --repeat rounds. Screenshots
of the first round in --out.
"""

import argparse
import json
import statistics
import time
from pathlib import Path

import bench
from frames import EVENT_GAP, SETTLE, call, mouse

HERE = Path(__file__).resolve().parent
GESTURES = ("zoom", "drag", "hover", "rows", "checked zoom")
# Where the gestures go: the middle of the frame, circles of the image, rows of the list.
POINTS = """(() => {
    const centre = (element) => {
        const box = element.getBoundingClientRect();
        return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    };
    const frame = document.querySelector("[data-image-frame]").getBoundingClientRect();
    const inside = ({ x, y }) =>
        x > frame.x + 20 && x < frame.right - 220 && y > frame.y + 60 && y < frame.bottom - 20;
    const circles = [...document.querySelectorAll("[data-image-stage] circle[data-node]")]
        .map(centre).filter(inside);
    const step = Math.max(1, Math.floor(circles.length / 40));
    return {
        centre: { x: frame.x + frame.width / 2, y: frame.y + frame.height / 2 },
        circles: circles.filter((_, i) => i % step === 0).slice(0, 40),
        rows: [...document.querySelectorAll("[data-image-rows] > li")].slice(0, 12).map(centre),
    };
})()"""


def load(tools, url):
    """The page, until its image is in the frame: the time it took, in ms."""
    tools.call("Page.navigate", url=url)
    start = time.perf_counter()
    for _ in range(600):
        time.sleep(0.05)
        if tools.evaluate("!!document.querySelector('[data-image-stage] svg[viewBox]')"):
            break
    loaded = (time.perf_counter() - start) * 1000
    time.sleep(SETTLE)
    tools.evaluate((HERE / "frames.js").read_text())
    return round(loaded)


def wheel(tools, point, out=None, name="zoom"):
    mouse(tools, "mouseMoved", point)
    call(tools, "start()")
    for i in range(30):
        mouse(tools, "mouseWheel", point, deltaX=0, deltaY=-60)
        time.sleep(EVENT_GAP)
        if out and i == 15:
            tools.screenshot(f"{out}/{name}-during.png")
    time.sleep(SETTLE)
    result = call(tools, "stop()")
    if out:
        tools.screenshot(f"{out}/{name}-after.png")
    return result


def drag(tools, start):
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


def hover(tools, points, out=None, name="hover"):
    call(tools, "start()")
    for point in points:
        mouse(tools, "mouseMoved", point)
        time.sleep(0.05)
    if out:
        tools.screenshot(f"{out}/{name}.png")
    time.sleep(SETTLE)
    return call(tools, "stop()")


def show_all(tools):
    tools.evaluate("document.querySelector('[data-image-zoom=all] button').click()")
    time.sleep(SETTLE)


def one_round(tools, url, out):
    result = {"load": load(tools, url)}
    if out:
        tools.screenshot(f"{out}/overview.png")
    points = tools.evaluate(POINTS)
    result["zoom"] = wheel(tools, points["centre"], out)
    result["drag"] = drag(tools, points["centre"])
    show_all(tools)
    result["hover"] = hover(tools, tools.evaluate(POINTS)["circles"], out)
    result["rows"] = hover(tools, points["rows"], out, "rows")
    # Three rows checked, their links drawn over the image; then a zoom again.
    tools.evaluate(
        "[...document.querySelectorAll('[data-row-check]')].slice(0, 3)"
        ".forEach((box) => box.click())"
    )
    time.sleep(SETTLE)
    if out:
        tools.screenshot(f"{out}/checked.png")
    result["checked zoom"] = wheel(tools, points["centre"], out, "checked-zoom")
    return result


def merged(rounds):
    result = {"load": statistics.median(r["load"] for r in rounds)}
    for gesture in GESTURES:
        result[gesture] = {
            key: statistics.median(r[gesture][key] for r in rounds)
            for key in ("median", "p90", "max", "slow")
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("server")
    parser.add_argument("--kind", default="authors", choices=("authors", "base"))
    parser.add_argument("--out", help="screenshots, taken during the first round")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--port", type=int, default=9440, help="DevTools port of Chrome")
    parser.add_argument("--width", type=int, default=1400)
    parser.add_argument("--height", type=int, default=1000)
    args = parser.parse_args()
    if args.out:
        Path(args.out).mkdir(parents=True, exist_ok=True)
    chrome, tools = bench.start_chrome(args.width, args.height, args.port)
    url = f"{args.server}/graph/image/{args.kind}/"
    try:
        rounds = [one_round(tools, url, args.out if r == 0 else None) for r in range(args.repeat)]
        print(json.dumps({"kind": args.kind, **merged(rounds)}), flush=True)
    finally:
        chrome.terminate()


if __name__ == "__main__":
    main()
