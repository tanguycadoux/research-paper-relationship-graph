"""
Benchmark of the citation graphs (#202): pages of a running server, and synthetic graphs,
measured in headless Chrome through the DevTools protocol (pure Python, no dependency).

    DJANGO_DEBUG=1 python manage.py runserver 8120          # on a copy of the base
    python tools/graph_bench/bench.py http://127.0.0.1:8120 --out /tmp/bench \\
        --page /graph/ --page /publications/123/graph/ --session <sessionid>

For each page: the time to the response and to DOMContentLoaded (main.js runs placeNodes
and creates the graph before it), the size of the graph data, the steps of the layout
(bench.js), the frames of the animation of a selection and of a zoom, and screenshots.
For synthetic graphs (--synthetic 500 1000 2000): the layout and the drawing alone.
"""

import argparse
import base64
import json
import os
import socket
import statistics
import struct
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
PORT = 9420
CY = "document.getElementById('citation-graph')._cyreg.cy"


class DevTools:
    """A minimal WebSocket client of the DevTools protocol of one page."""

    def __init__(self, url):
        host, rest = url[len("ws://") :].split("/", 1)
        name, port = host.split(":")
        self.sock = socket.create_connection((name, int(port)))
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                f"GET /{rest} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
                f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        buffer = b""
        while b"\r\n\r\n" not in buffer:
            buffer += self.sock.recv(4096)
        self.buffer = buffer.split(b"\r\n\r\n", 1)[1]
        self.id = 0

    def _send(self, text):
        data = text.encode()
        header = bytearray([0x81])
        if len(data) < 126:
            header.append(0x80 | len(data))
        elif len(data) < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", len(data))
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", len(data))
        mask = os.urandom(4)
        self.sock.sendall(bytes(header) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n):
        while len(self.buffer) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise EOFError
            self.buffer += chunk
        out, self.buffer = self.buffer[:n], self.buffer[n:]
        return out

    def _receive(self):
        message = b""
        while True:
            first, second = self._read(2)
            n = second & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            message += self._read(n)
            if first & 0x80:
                return message.decode()

    def call(self, method, **params):
        self.id += 1
        self._send(json.dumps({"id": self.id, "method": method, "params": params}))
        while True:
            message = json.loads(self._receive())
            if message.get("id") == self.id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    def evaluate(self, expression):
        result = self.call(
            "Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True
        )
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result["result"].get("value")

    def screenshot(self, path):
        data = self.call("Page.captureScreenshot", format="png")["data"]
        Path(path).write_bytes(base64.b64decode(data))


def start_chrome(width, height):
    profile = tempfile.mkdtemp(prefix="graph-bench-")
    chrome = subprocess.Popen(
        [
            CHROME,
            "--headless=new",
            "--hide-scrollbars",
            f"--remote-debugging-port={PORT}",
            f"--window-size={width},{height}",
            f"--user-data-dir={profile}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(100):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
            break
        except OSError:
            time.sleep(0.1)
    page = next(tab for tab in tabs if tab["type"] == "page")
    tools = DevTools(page["webSocketDebuggerUrl"])
    tools.call("Page.enable")
    tools.call("Network.enable")
    tools.call(
        "Emulation.setDeviceMetricsOverride",
        width=width,
        height=height,
        deviceScaleFactor=1,
        mobile=False,
    )
    return chrome, tools


def load(tools, url):
    """Open url and wait for the graph; the navigation timings, in milliseconds."""
    tools.call("Page.navigate", url=url)
    # Up to 5 minutes: a large graph takes long to lay out (that is what is measured).
    for _ in range(3000):
        time.sleep(0.1)
        ready = tools.evaluate(
            "document.readyState === 'complete' && !!document.getElementById('citation-graph')"
            " && !!document.getElementById('citation-graph')._cyreg"
        )
        if ready:
            break
    return tools.evaluate(
        """(() => { const t = performance.getEntriesByType('navigation')[0];
        return {response: Math.round(t.responseEnd - t.requestStart),
                domContentLoaded: Math.round(t.domContentLoadedEventEnd - t.startTime),
                bytes: t.transferSize,
                data: (document.getElementById('citation-graph-data')
                       || {textContent: ''}).textContent.length}; })()"""
    )


SELECTION_FRAMES = """new Promise((resolve) => {
    const cy = CY;
    const hub = cy.nodes('[url]').sort((a, b) => b.degree() - a.degree())[0];
    const intervals = [];
    let last = performance.now();
    const start = last;
    const step = () => {
        const now = performance.now();
        intervals.push(now - last);
        last = now;
        if (now - start < 700) requestAnimationFrame(step);
        else {
            intervals.sort((a, b) => a - b);
            resolve({selected: hub.data('label').slice(0, 50), degree: hub.degree(),
                     frames: intervals.length,
                     frameMedian: Math.round(intervals[intervals.length >> 1]),
                     frameMax: Math.round(intervals[intervals.length - 1])});
        }
    };
    hub.emit('tap');
    requestAnimationFrame(step);
})""".replace("CY", CY)

POSITIONS_WRITE = """(() => { const cy = CY; const t = performance.now();
    cy.batch(() => cy.nodes().forEach(
        (n) => n.position({x: n.position('x') * 1.0001, y: n.position('y')})));
    return Math.round((performance.now() - t) * 10) / 10; })()""".replace("CY", CY)


def run_bench(tools, options):
    script = (HERE / "bench.js").read_text().replace("})(OPTIONS)", f"}})({json.dumps(options)})")
    return tools.evaluate(script)


def measure_page(tools, server, path, out, repeat):
    url = server + path
    timings = [load(tools, url) for _ in range(repeat)]
    navigation = {
        key: statistics.median([t[key] for t in timings])
        if key not in ("bytes", "data")
        else timings[0][key]
        for key in timings[0]
    }
    name = path.strip("/").replace("/", "-") or "home"
    tools.screenshot(f"{out}/{name}.png")
    layout = run_bench(tools, {"graph": "page", "repeat": repeat})
    write = tools.evaluate(POSITIONS_WRITE)
    selection = tools.evaluate(SELECTION_FRAMES)
    time.sleep(0.5)
    tools.screenshot(f"{out}/{name}-selection.png")
    return {"page": path, **navigation, **layout, "positionsWrite": write, **selection}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("server")
    parser.add_argument("--out", required=True)
    parser.add_argument("--page", action="append", default=[])
    parser.add_argument("--session", help="cookie sessionid, for the pages of a corpus")
    parser.add_argument("--synthetic", type=int, nargs="*", default=[])
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--width", type=int, default=1400)
    parser.add_argument("--height", type=int, default=1000)
    args = parser.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    chrome, tools = start_chrome(args.width, args.height)
    try:
        if args.session:
            tools.call("Network.setCookie", name="sessionid", value=args.session, url=args.server)
        for path in args.page:
            print(
                json.dumps(measure_page(tools, args.server, path, args.out, args.repeat)),
                flush=True,
            )
        if args.synthetic:
            # Any page of the application serves its modules and Cytoscape.
            load(tools, args.server + (args.page[0] if args.page else "/graph/"))
            for count in args.synthetic:
                options = {
                    "graph": {"nodes": count, "components": 4, "undated": 0.02, "seed": 7},
                    "repeat": args.repeat if count <= 1000 else 1,
                    "width": 690,
                    "height": 767,
                    "render": True,
                }
                print(json.dumps({"synthetic": count, **run_bench(tools, options)}), flush=True)
    finally:
        chrome.terminate()


if __name__ == "__main__":
    main()
