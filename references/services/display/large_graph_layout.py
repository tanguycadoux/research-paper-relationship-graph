"""
The layout of the images of the large graphs (#328, #420), in pixels.

Each connected group is laid out on its own, and the groups are packed in rows, the
largest first; the nodes without link follow in a grid. Within a group:

- the leaves (nodes of a single link) are set aside: on the graph of the base, the
  references cited once make most of the nodes, and laid out with the others they
  wrapped each article in a tight « dandelion »;
- the heart (the other nodes) is laid out by igraph (Fruchterman-Reingold), its links
  weighted: two authors who often sign together are pulled closer than the cosigners
  of a single large article;
- the leaves of each node go in rings around it (its crown), and the nodes are pushed
  apart until no crown covers another.
"""

import math
import random
import statistics
from collections import defaultdict
from contextlib import contextmanager

import igraph

# Iterations of Fruchterman-Reingold: more than the 500 of igraph, the image is computed
# once, in the background (3 s for the 2 800 authors of the largest group of the bench).
LAYOUT_ITERATIONS = 3000
# The weights of the links, relative to their median, kept within these bounds: a pair
# of authors of a hundred publications together must not collapse into one point.
WEIGHT_BOUNDS = (0.25, 8)
# Space around each node or crown, in pixels: what keeps them apart.
NODE_GAP = 10
# Between the leaves of a crown, and between the node and its first ring.
LEAF_GAP = 8
# The median link of the heart, in diameters of its two ends (crowns included).
LINK_LENGTH = 4
# The box of a heart, in areas of its discs (gaps included).
SPACE = 6
# Passes pushing apart the nodes whose crowns overlap.
SEPARATION_PASSES = 80
# Between two groups, and above the grid of the nodes without link.
GROUP_GAP = 40
MIN_WIDTH = 1600


def positions(count, edges, radii):
    """
    The position of each node, the width of the image, the height of the drawing, the
    height of the caption of the nodes without link (or None) and their number.
    edges: (node, node, weight); radii: the radius of each node.
    """
    graph = igraph.Graph(n=count, edges=[(a, b) for a, b, _ in edges])
    graph.es["weight"] = [weight or 1 for _, _, weight in edges]
    groups = sorted(graph.connected_components(), key=len, reverse=True)
    linked = [group for group in groups if len(group) > 1]
    alone = sorted((group[0] for group in groups if len(group) == 1), key=lambda n: -radii[n])
    shapes = [group_layout(graph, group, radii) for group in linked]
    points = [None] * count
    width, top = pack(shapes, points)
    if linked:
        top += GROUP_GAP + 40
    height = place_alone(alone, radii, points, width, top)
    return points, width, height, (top - 40 if alone and linked else None), len(alone)


def pack(shapes, points):
    """
    Each group in rows of the width of the image, the largest first: set its nodes in
    points. The width of the image, and the bottom of the last row.
    """
    area = sum(w * h for _, w, h in shapes)
    width = max(MIN_WIDTH, max((w for _, w, _ in shapes), default=0), 1.2 * math.sqrt(area))
    x = y = row_height = 0
    for placed, w, h in shapes:
        if x and x + w > width:
            x, y, row_height = 0, y + row_height + GROUP_GAP, 0
        for node, (px, py) in placed.items():
            points[node] = (x + px, y + py)
        x += w + GROUP_GAP
        row_height = max(row_height, h)
    return width, y + row_height


def place_alone(alone, radii, points, width, top):
    """The nodes without link in a grid under the groups; the bottom of the grid."""
    if not alone:
        return top
    step = 2 * max(radii[node] for node in alone) + 6
    per_row = max(1, int(width // step))
    for rank, node in enumerate(alone):
        points[node] = ((rank % per_row) * step + step / 2, top + (rank // per_row) * step)
    return top + math.ceil(len(alone) / per_row) * step


def group_layout(graph, group, radii):
    """
    One connected group: {node: (x, y)} from the top left corner of its box, and the
    width and height of the box.
    """
    group = sorted(group)
    sub = graph.induced_subgraph(group)
    sizes = [radii[node] for node in group]
    heart, leaves = split_leaves(sub)
    crowns = {parent: crown(children, sizes, sizes[parent]) for parent, children in leaves.items()}
    discs = [max(sizes[node], crowns[node][1] if node in crowns else 0) for node in heart]
    coords = heart_layout(sub.induced_subgraph(heart), discs)
    local = dict(zip(heart, coords, strict=True))
    for parent, (offsets, _) in crowns.items():
        px, py = local[parent]
        for child, (dx, dy) in offsets:
            local[child] = (px + dx, py + dy)
    return boxed({group[i]: point for i, point in local.items()}, radii)


def split_leaves(sub):
    """
    The heart of a group (its nodes of two links or more) and its leaves, by node of the
    heart. A pair has no heart: its first node is.
    """
    degrees = sub.degree()
    heart = [i for i, degree in enumerate(degrees) if degree > 1] or [0]
    kept = set(heart)
    leaves = defaultdict(list)
    for i in range(sub.vcount()):
        if i not in kept:
            leaves[sub.neighbors(i)[0]].append(i)
    return heart, leaves


def crown(children, sizes, centre):
    """
    The leaves of a node in rings around it, the largest inside, each ring holding as
    many as its perimeter allows: [(leaf, (dx, dy))], and the outer radius of the crown.
    """
    order = sorted(children, key=lambda child: -sizes[child])
    step = 2 * max(sizes[child] for child in children) + LEAF_GAP
    rings, room = [], 0
    while room < len(order):
        radius = centre + LEAF_GAP + step / 2 + len(rings) * step
        rings.append((radius, max(1, int(2 * math.pi * radius / step))))
        room += rings[-1][1]
    offsets, start = [], 0
    for index, (radius, _) in enumerate(rings):
        # The leaves shared out between the rings like their room: no lonely last ring.
        count = round(len(order) * sum(c for _, c in rings[: index + 1]) / room) - start
        turn = 0.5 * (index % 2)
        for k, child in enumerate(order[start : start + count]):
            angle = 2 * math.pi * (k + turn) / count
            offsets.append((child, (radius * math.cos(angle), radius * math.sin(angle))))
        start += count
    return offsets, rings[-1][0] + step / 2


def heart_layout(heart, discs):
    """The heart by igraph, scaled to the size of its discs, then pushed apart."""
    if heart.vcount() == 1:
        return [(0.0, 0.0)]
    weights = link_weights(heart.es["weight"])
    with fixed_randomness(heart.vcount()):
        coords = heart.layout_fruchterman_reingold(weights=weights, niter=LAYOUT_ITERATIONS)
    coords = scaled(coords.coords, heart.get_edgelist(), discs)
    return separated(coords, [disc + NODE_GAP / 2 for disc in discs])


@contextmanager
def fixed_randomness(seed):
    """
    igraph drawing from its own generator, seeded: the same base gives the same image.
    (Its start positions given as seed= are not enough: it draws again while it runs.)
    """
    igraph.set_random_number_generator(random.Random(seed))
    try:
        yield
    finally:
        igraph.set_random_number_generator(random)


def link_weights(weights):
    middle = statistics.median(weights) or 1
    low, high = WEIGHT_BOUNDS
    return [min(high, max(low, weight / middle)) for weight in weights]


def scaled(coords, links, discs):
    """
    The layout scaled so that its median link is LINK_LENGTH times its ends, and its
    discs cover at most 1 / SPACE of its square: pushing the nodes apart then only moves
    them a little, without blurring its groups.
    """
    lengths = [math.dist(coords[a], coords[b]) for a, b in links]
    wanted = [LINK_LENGTH * (discs[a] + discs[b]) for a, b in links]
    factor = statistics.median(wanted) / (statistics.median(lengths) or 1)
    xs, ys = [x for x, _ in coords], [y for _, y in coords]
    # The square around the layout: a long chain is not crushed by a narrow box.
    side = max(max(xs) - min(xs), max(ys) - min(ys))
    if side:
        covered = sum(math.pi * (disc + NODE_GAP / 2) ** 2 for disc in discs)
        factor = max(factor, math.sqrt(SPACE * covered) / side)
    return [(x * factor, y * factor) for x, y in coords]


def separated(coords, discs):
    """The points pushed apart, pair by pair, until no two discs overlap."""
    points = [list(point) for point in coords]
    for _ in range(SEPARATION_PASSES):
        if not push_apart(points, discs):
            break
    return [tuple(point) for point in points]


def push_apart(points, discs):
    """One pass: each overlapping pair pushed apart, the smaller disc more. Any moved?"""
    moved = False
    for i, j in close_pairs(points, discs):
        (xi, yi), (xj, yj) = points[i], points[j]
        dx, dy = xj - xi, yj - yi
        distance = math.hypot(dx, dy)
        overlap = discs[i] + discs[j] - distance
        if overlap <= 0.01:
            continue
        if distance < 1e-6:
            # Two points at the same place: apart in a direction of their own.
            dx, dy, distance = math.cos(i + j), math.sin(i + j), 1
        share = discs[j] ** 2 / (discs[i] ** 2 + discs[j] ** 2)
        ux, uy = dx / distance * overlap, dy / distance * overlap
        points[i][0] -= ux * share
        points[i][1] -= uy * share
        points[j][0] += ux * (1 - share)
        points[j][1] += uy * (1 - share)
        moved = True
    return moved


def close_pairs(points, discs):
    """The pairs of discs that share a cell of a grid: those that may overlap."""
    cell = 2 * statistics.median(discs)
    grid = defaultdict(list)
    for i, ((x, y), disc) in enumerate(zip(points, discs, strict=True)):
        for cx in range(math.floor((x - disc) / cell), math.floor((x + disc) / cell) + 1):
            for cy in range(math.floor((y - disc) / cell), math.floor((y + disc) / cell) + 1):
                grid[cx, cy].append(i)
    pairs = set()
    for members in grid.values():
        for rank, i in enumerate(members):
            pairs.update((i, j) for j in members[rank + 1 :])
    return sorted(pairs)


def boxed(local, radii):
    """The points moved to the top left corner of their box; the box's size."""
    left = min(x - radii[node] for node, (x, _) in local.items())
    top = min(y - radii[node] for node, (_, y) in local.items())
    right = max(x + radii[node] for node, (x, _) in local.items())
    bottom = max(y + radii[node] for node, (_, y) in local.items())
    moved = {node: (x - left, y - top) for node, (x, y) in local.items()}
    return moved, right - left, bottom - top
