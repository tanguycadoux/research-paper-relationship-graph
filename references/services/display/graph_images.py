"""
Graphs too large to be drawn in the page (#328): the graph of all the authors has
9 500 nodes and 56 000 edges on the bench base (2 minutes of layout in the browser,
6.8 MB of data), the graph of the base 1 800 publications. Beyond LARGE_GRAPH nodes,
the page draws nothing and offers the full graph as an image, computed in the
background on the server and kept as SVG:

- layout by igraph, group by group, the leaves in crowns around their node
  (large_graph_layout.py);
- one circle per node, its size from its publications (authors) or its citations
  (publications), a link to its page and its name on hover; the names of the largest
  nodes written beside them;
- the edges in a few paths, by width: an SVG of one element per edge would weigh
  as much as the data of the page.

The image is common to everyone; its signature (a summary of the base) says when the
base has changed since.
"""

import json
import math
import threading
from xml.sax.saxutils import escape, quoteattr

from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections, connection
from django.db.models import Max
from django.utils import formats, timezone

from ...models import (
    Author,
    AuthorPublication,
    CitedReference,
    FetchRequest,
    GraphImage,
    Publication,
)
from ..imports import fetch_queue
from . import wording
from .author_graph import LARGE_COLLABORATION, all_authors_graph
from .graph import base_graph
from .large_graph_layout import positions

Kind = GraphImage.Kind
Action = FetchRequest.Action
Status = GraphImage.Status

# Beyond this many nodes, a graph is offered as an image rather than drawn in the page.
LARGE_GRAPH = 1000
# Names written beside the nodes: the largest ones only, the others on hover.
LABELED_NODES = 150
# Colours of the graph (assets/css/source.css, --color-graph-*).
NODE_COLOR = "#179e6e"
EDGE_COLOR = "#8a8983"
# Space around the drawing, and above it for its title, in pixels.
MARGIN = 40
TOP = 80


def node_count(kind):
    """The number of nodes of the graph, without building it."""
    if kind == Kind.AUTHORS:
        return AuthorPublication.objects.values("author_id").distinct().count()
    return Publication.objects.count()


def is_large(kind):
    return node_count(kind) > LARGE_GRAPH


def signature(kind):
    """A summary of what the graph is drawn from: another one, and the image is old."""
    if kind == Kind.AUTHORS:
        slots = AuthorPublication.objects.aggregate(last=Max("pk"))
        return f"{AuthorPublication.objects.count()}:{slots['last']}:{Author.objects.count()}"
    citations = CitedReference.objects.filter(target__isnull=False).count()
    last = Publication.objects.aggregate(last=Max("pk"))["last"]
    return f"{Publication.objects.count()}:{last}:{citations}"


def image_state(kind):
    """The image of the graph, if any, and whether the base has changed since."""
    image = GraphImage.objects.filter(kind=kind).defer("svg", "node_list").first()
    return {
        "image": image,
        "pending": bool(image and image.status == Status.PENDING and not is_stuck(image)),
        "outdated": bool(
            image and image.status == Status.DONE and image.signature != signature(kind)
        ),
        "kind": kind,
        "nodes": node_count(kind),
        "noun": "auteurs" if kind == Kind.AUTHORS else "publications",
    }


def request_image(kind, user):
    """
    Start computing the image of the graph, unless it is already being computed.
    Return False when it was.
    """
    image = GraphImage.objects.filter(kind=kind).first()
    if image and image.status == Status.PENDING and not is_stuck(image):
        return False
    if image is None:
        image = GraphImage(kind=kind)
    image.status = Status.PENDING
    image.requested_at = timezone.now()
    image.requested_by = user if user.is_authenticated else None
    image.error = ""
    image.save()
    if fetch_queue.worker_alive():
        fetch_queue.enqueue_action(Action.GRAPH_IMAGE, user, identifier=kind)
    else:
        run_in_background(generate, kind)
    return True


def run_in_background(function, *args):
    """Without a worker of the queue (#380): a thread of the server."""
    threading.Thread(target=in_own_connection, args=(function, *args), daemon=True).start()


def in_own_connection(function, *args):
    close_old_connections()
    try:
        function(*args)
    finally:
        connection.close()


def generate(kind):
    """Compute the image of the graph and keep it; keep the error otherwise. Return it."""
    image = GraphImage.objects.get(kind=kind)
    try:
        current = signature(kind)
        graph = all_authors_graph() if kind == Kind.AUTHORS else base_graph(AnonymousUser())
        image.svg, image.node_list = render(graph, kind, timezone.now())
        image.signature = current
        image.nodes = len(graph["nodes"])
        image.edges = len(graph["edges"])
        image.status = Status.DONE
    # Whatever fails, the page must say so.
    except Exception as error:  # noqa: BLE001
        image.status = Status.FAILED
        image.error = f"{type(error).__name__} : {error}"
    image.finished_at = timezone.now()
    image.save()
    return image


def render(graph, kind, when):
    """
    The SVG of the graph (its layout by igraph, then circles, edges and names) and the
    list of its nodes, for the page that browses the image (#453), as JSON.
    """
    nodes = [node["data"] for node in graph["nodes"]]
    edges = indexed_edges(nodes, graph["edges"])
    size_key = "publications" if kind == Kind.AUTHORS else "citedBy"
    sizes = [node.get(size_key) or 0 for node in nodes]
    radii = node_radii(sizes)
    points, side, drawing_height, alone_title_y, alone_count = positions(len(nodes), edges, radii)
    noun = "auteurs" if kind == Kind.AUTHORS else "publications"
    width, height = side + 2 * MARGIN, drawing_height + MARGIN + TOP
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="system-ui, sans-serif">',
        f"<title>{escape(Kind(kind).label)}</title>",
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{MARGIN}" y="48" font-size="24" fill="#0b0b0b">'
        f"{escape(header(kind, nodes, edges, when))}</text>",
        f'<g transform="translate({MARGIN} {TOP})">',
        *edge_paths(edges, points),
        *node_circles(nodes, points, radii),
        *node_labels(nodes, points, radii),
        *alone_caption(alone_count, alone_title_y, noun),
        "</g></svg>",
    ]
    return "\n".join(parts), node_list(nodes, sizes, points, radii, edges)


def indexed_edges(nodes, graph_edges):
    """The edges as (node, node, weight), the nodes by their rank."""
    index = {node["id"]: i for i, node in enumerate(nodes)}
    return [
        (
            index[edge["data"]["source"]],
            index[edge["data"]["target"]],
            edge["data"].get("weight", 1),
        )
        for edge in graph_edges
        if edge["data"]["source"] in index and edge["data"]["target"] in index
    ]


def header(kind, nodes, edges, when):
    noun = "auteurs" if kind == Kind.AUTHORS else "publications"
    return (
        f"{Kind(kind).label} : {formats.number_format(len(nodes), force_grouping=True)} {noun}, "
        f"{formats.number_format(len(edges), force_grouping=True)} liens. "
        f"Image du {formats.date_format(timezone.localtime(when), 'j F Y à H:i')}."
    )


def node_list(nodes, sizes, points, radii, edges):
    """
    The nodes of the image, by their rank (data-node of their circle): name, size, page,
    and centre and radius in units of the image; the edges as a flat list of ranks.
    """
    return json.dumps(
        {
            "nodes": [
                [
                    node["label"],
                    sizes[i],
                    node["url"],
                    round(points[i][0] + MARGIN, 1),
                    round(points[i][1] + TOP, 1),
                    round(radii[i], 1),
                ]
                for i, node in enumerate(nodes)
            ],
            "edges": [end for a, b, _ in edges for end in (a, b)],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def alone_caption(count, y, noun):
    """The title of the grid of the nodes without link."""
    if not count or y is None:
        return []
    singular = noun.removesuffix("s")
    text = wording.count(count, f"{singular} sans lien", f"{noun} sans lien")
    text = text.replace(str(count), formats.number_format(count, force_grouping=True), 1)
    if noun == "auteurs":
        text += f" : seuls, ou sur des publications de plus de {LARGE_COLLABORATION} auteurs"
    return [f'<text x="0" y="{y + 20:.0f}" font-size="20" fill="#3f3e3b">{escape(text)}</text>']


def node_radii(sizes, smallest=3, largest=18):
    most = max(sizes, default=0) or 1
    return [smallest + (largest - smallest) * math.sqrt(size / most) for size in sizes]


def edge_paths(edges, points, widths=(0.4, 0.8, 1.6, 3.0)):
    """
    The edges in one path per width, the width from the weight (its quartile). Neither
    they nor the names take the pointer: hit-testing paths of 56 000 segments at each move
    of the mouse made the hover of the nodes take 110 ms a frame (#453).
    """
    if not edges:
        return []
    weights = sorted(weight for _, _, weight in edges)
    limits = [weights[len(weights) * q // 4] for q in (1, 2, 3)]
    buckets = [[] for _ in widths]
    for a, b, weight in edges:
        bucket = sum(weight > limit for limit in limits)
        (x1, y1), (x2, y2) = points[a], points[b]
        buckets[bucket].append(f"M{x1:.1f} {y1:.1f}L{x2:.1f} {y2:.1f}")
    return [
        f'<path d="{"".join(segments)}" stroke="{EDGE_COLOR}" stroke-width="{width}" '
        f'stroke-opacity="0.45" fill="none" pointer-events="none"/>'
        for width, segments in zip(widths, buckets, strict=True)
        if segments
    ]


def node_circles(nodes, points, radii):
    """A circle per node, the largest last (on top), each a link to its page."""
    order = sorted(range(len(nodes)), key=lambda i: radii[i])
    return [
        f"<a href={quoteattr(nodes[i]['url'])}>"
        f'<circle data-node="{i}" cx="{points[i][0]:.1f}" cy="{points[i][1]:.1f}" '
        f'r="{radii[i]:.1f}" '
        f'fill="{NODE_COLOR}" stroke="white" stroke-width="1">'
        f"<title>{escape(nodes[i]['label'])}</title></circle></a>"
        for i in order
    ]


def node_labels(nodes, points, radii):
    """The short names of the largest nodes, beside them, on a white halo."""
    largest = sorted(range(len(nodes)), key=lambda i: -radii[i])[:LABELED_NODES]
    return [
        f'<text x="{points[i][0] + radii[i] + 3:.1f}" y="{points[i][1] + 4:.1f}" '
        f'font-size="12" fill="#0b0b0b" stroke="white" stroke-width="3" paint-order="stroke" '
        'pointer-events="none">'
        f"{escape(nodes[i].get('shortLabel') or nodes[i]['label'])}</text>"
        for i in largest
    ]


# A computation still « en cours » after this long died with its thread (a restart of
# the server): it can be asked again.
STUCK_AFTER = timezone.timedelta(minutes=5)


def is_stuck(image):
    return image.status == Status.PENDING and timezone.now() - image.requested_at > STUCK_AFTER
