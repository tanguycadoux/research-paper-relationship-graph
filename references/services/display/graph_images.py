"""
Graphs too large to be drawn in the page (#328): the graph of all the authors has
9 500 nodes and 56 000 edges on the bench base (2 minutes of layout in the browser,
6.8 MB of data), the graph of the base 1 800 publications. Beyond LARGE_GRAPH nodes,
the page draws nothing and offers the full graph as an image, computed in the
background on the server and kept as SVG:

- layout by igraph (Fruchterman-Reingold: 0.7 s for the 9 500 authors);
- one circle per node, its size from its publications (authors) or its citations
  (publications), a link to its page and its name on hover; the names of the largest
  nodes written beside them;
- the edges in a few paths, by width: an SVG of one element per edge would weigh
  as much as the data of the page.

The image is common to everyone; its signature (a summary of the base) says when the
base has changed since.
"""

import math
import threading
from xml.sax.saxutils import escape, quoteattr

import igraph
from django.contrib.auth.models import AnonymousUser
from django.db import close_old_connections, connection
from django.db.models import Max
from django.utils import formats, timezone

from ...models import Author, AuthorPublication, CitedReference, GraphImage, Publication
from . import wording
from .author_graph import LARGE_COLLABORATION, all_authors_graph
from .graph import base_graph

Kind = GraphImage.Kind
Status = GraphImage.Status

# Beyond this many nodes, a graph is offered as an image rather than drawn in the page.
LARGE_GRAPH = 1000
# Names written beside the nodes: the largest ones only, the others on hover.
LABELED_NODES = 150
# Colours of the graph (assets/css/source.css, --color-graph-*).
NODE_COLOR = "#179e6e"
EDGE_COLOR = "#8a8983"


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
    image = GraphImage.objects.filter(kind=kind).defer("svg").first()
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
    run_in_background(generate, kind)
    return True


def run_in_background(function, *args):
    """A thread for now: the queue of #246 will take it over."""
    threading.Thread(target=in_own_connection, args=(function, *args), daemon=True).start()


def in_own_connection(function, *args):
    close_old_connections()
    try:
        function(*args)
    finally:
        connection.close()


def generate(kind):
    """Compute the image of the graph and keep it; keep the error otherwise."""
    image = GraphImage.objects.get(kind=kind)
    try:
        current = signature(kind)
        graph = all_authors_graph() if kind == Kind.AUTHORS else base_graph(AnonymousUser())
        image.svg = render_svg(graph, kind, timezone.now())
        image.signature = current
        image.nodes = len(graph["nodes"])
        image.edges = len(graph["edges"])
        image.status = Status.DONE
    except Exception as error:  # noqa: BLE001: whatever fails, the page must say so.
        image.status = Status.FAILED
        image.error = f"{type(error).__name__} : {error}"
    image.finished_at = timezone.now()
    image.save()


def render_svg(graph, kind, when):
    """The SVG of the graph: its layout by igraph, then circles, edges and names."""
    nodes = [node["data"] for node in graph["nodes"]]
    index = {node["id"]: i for i, node in enumerate(nodes)}
    edges = [
        (
            index[edge["data"]["source"]],
            index[edge["data"]["target"]],
            edge["data"].get("weight", 1),
        )
        for edge in graph["edges"]
        if edge["data"]["source"] in index and edge["data"]["target"] in index
    ]
    size_key = "publications" if kind == Kind.AUTHORS else "citedBy"
    radii = node_radii([node.get(size_key) or 0 for node in nodes])
    points, side, drawing_height, alone_title_y, alone_count = positions(len(nodes), edges, radii)
    title = GraphImage.Kind(kind).label
    noun = "auteurs" if kind == Kind.AUTHORS else "publications"
    header = (
        f"{title} : {formats.number_format(len(nodes), force_grouping=True)} {noun}, "
        f"{formats.number_format(len(edges), force_grouping=True)} liens. "
        f"Image du {formats.date_format(timezone.localtime(when), 'j F Y à H:i')}."
    )
    margin, top = 40, 80
    width, height = side + 2 * margin, drawing_height + margin + top
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" font-family="system-ui, sans-serif">',
        f"<title>{escape(title)}</title>",
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{margin}" y="48" font-size="24" fill="#0b0b0b">{escape(header)}</text>',
        f'<g transform="translate({margin} {top})">',
        *edge_paths(edges, points),
        *node_circles(nodes, points, radii),
        *node_labels(nodes, points, radii),
        *alone_caption(alone_count, alone_title_y, noun),
        "</g></svg>",
    ]
    return "\n".join(parts)


def positions(count, edges, radii):
    """
    The position of each node, the width of the image and the height of the drawing.
    Each connected group is laid out by igraph on its own, in a square as large as it
    needs, and the squares are packed in rows, the largest first; the nodes without
    link follow in a grid. Laid out together, the small groups and the lonely nodes
    were spread over the whole image around a small linked heart (most authors of the
    bench base sign only large collaborations, which link nobody).
    """
    graph = igraph.Graph(n=count, edges=[(a, b) for a, b, _ in edges])
    groups = sorted(graph.connected_components(), key=len, reverse=True)
    linked = [group for group in groups if len(group) > 1]
    alone = sorted((group[0] for group in groups if len(group) == 1), key=lambda n: -radii[n])
    width = max(1600, 80 * math.sqrt(sum(len(group) for group in linked) or 1))
    points = [None] * count
    x = y = row_height = 0
    gap = 40
    for group in linked:
        side = min(width, max(120, 80 * math.sqrt(len(group))))
        if x + side > width:
            x, y, row_height = 0, y + row_height + gap, 0
        coords = graph.induced_subgraph(group).layout("fr").coords
        for node, (px, py) in zip(group, fitted(coords, side), strict=True):
            points[node] = (x + px, y + py)
        x += side + gap
        row_height = max(row_height, side)
    top = (y + row_height + gap + 40) if linked else 0
    step = 2 * max((radii[node] for node in alone), default=0) + 6
    per_row = max(1, int(width // step))
    for rank, node in enumerate(alone):
        points[node] = ((rank % per_row) * step + step / 2, top + (rank // per_row) * step)
    height = top + (math.ceil(len(alone) / per_row) * step if alone else 0)
    return points, width, height, (top - 40 if alone and linked else None), len(alone)


def fitted(coords, side):
    """The coordinates of the layout, scaled into a square of the side, in pixels."""
    if not coords:
        return []
    xs, ys = [x for x, _ in coords], [y for _, y in coords]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1
    return [((x - min(xs)) / span * side, (y - min(ys)) / span * side) for x, y in coords]


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
    """The edges in one path per width, the width from the weight (its quartile)."""
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
        f'stroke-opacity="0.45" fill="none"/>'
        for width, segments in zip(widths, buckets, strict=True)
        if segments
    ]


def node_circles(nodes, points, radii):
    """A circle per node, the largest last (on top), each a link to its page."""
    order = sorted(range(len(nodes)), key=lambda i: radii[i])
    return [
        f"<a href={quoteattr(nodes[i]['url'])}>"
        f'<circle cx="{points[i][0]:.1f}" cy="{points[i][1]:.1f}" r="{radii[i]:.1f}" '
        f'fill="{NODE_COLOR}" stroke="white" stroke-width="1">'
        f"<title>{escape(nodes[i]['label'])}</title></circle></a>"
        for i in order
    ]


def node_labels(nodes, points, radii):
    """The short names of the largest nodes, beside them, on a white halo."""
    largest = sorted(range(len(nodes)), key=lambda i: -radii[i])[:LABELED_NODES]
    return [
        f'<text x="{points[i][0] + radii[i] + 3:.1f}" y="{points[i][1] + 4:.1f}" '
        f'font-size="12" fill="#0b0b0b" stroke="white" stroke-width="3" paint-order="stroke">'
        f"{escape(nodes[i].get('shortLabel') or nodes[i]['label'])}</text>"
        for i in largest
    ]


# A computation still « en cours » after this long died with its thread (a restart of
# the server): it can be asked again.
STUCK_AFTER = timezone.timedelta(minutes=5)


def is_stuck(image):
    return image.status == Status.PENDING and timezone.now() - image.requested_at > STUCK_AFTER
