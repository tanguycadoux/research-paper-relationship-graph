"""
Coauthorship graphs (#222): one node per author, one edge per pair of authors who signed
a publication together. The graph of an author shows them, their coauthors and the links
between these coauthors; the graph of all authors uses the same code.

- Size of a node: the number of publications of the author in the base, all of them.
- Weight of an edge (Newman): each publication of n authors adds 1/(n - 1) to each pair
  of its authors, so that a publication of two authors weighs as much as all the links
  of one author on a publication of ten. One edge per pair, with the sum and the number
  of shared publications. No threshold: the width of the edge tells the strength.
- A publication of more than LARGE_COLLABORATION authors creates no link (LIGO and its
  thousand authors would make millions of pairs); it still counts in the size of the
  nodes, and the graph says how many were set aside.

Two queries whatever the size of the graph: the author slots of the publications, then
the authors.
"""

from collections import defaultdict
from itertools import combinations

from django.db.models import Count, Q
from django.urls import reverse

from ...models import Author, AuthorPublication, Publication

# Beyond this many authors, a publication links nobody (decision of #222).
LARGE_COLLABORATION = 50


def all_authors_graph():
    """Every author of the base with at least one publication, and every coauthorship."""
    slots = AuthorPublication.objects.all()
    authors = Author.objects.filter(pk__in=AuthorPublication.objects.values("author_id"))
    return coauthorship_graph(slots, authors)


def author_graph(author):
    """
    The author, their coauthors (on publications of at most LARGE_COLLABORATION authors)
    and the links between all of them, through any of their publications.
    """
    own = AuthorPublication.objects.filter(author=author).values("publication_id")
    linking = (
        Publication.objects.filter(pk__in=own)
        .annotate(people=Count("authorpublication__author", distinct=True))
        .filter(people__lte=LARGE_COLLABORATION)
        .values("pk")
    )
    coauthors = AuthorPublication.objects.filter(publication__in=linking).values("author_id")
    # Every publication of a member: their sizes, and the links between them.
    of_members = AuthorPublication.objects.filter(
        Q(author=author) | Q(author__in=coauthors)
    ).values("publication_id")
    slots = AuthorPublication.objects.filter(publication__in=of_members)
    members = Author.objects.filter(Q(pk=author.pk) | Q(pk__in=coauthors))
    return coauthorship_graph(slots, members, source_id=author.pk)


def publication_authors(slots):
    """{publication id: set of author ids}: each person once, even with several slots."""
    authors = defaultdict(set)
    for publication_id, author_id in slots.values_list("publication_id", "author_id").order_by():
        authors[publication_id].add(author_id)
    return authors


def coauthorship_graph(slots, authors, source_id=None):
    """
    The Cytoscape elements of the authors and of their coauthorships through the
    publications of the slots, which must hold every publication of every author.
    """
    by_publication = publication_authors(slots)
    people = list(authors.order_by("last_name", "first_name", "pk"))
    if source_id is not None:
        # The author of the graph first: at the centre of the starting spiral (network.js).
        people.sort(key=lambda person: person.pk != source_id)
    members = {person.pk for person in people}
    links, excluded = coauthorships(by_publication, members)
    counts = publication_counts(by_publication)
    return {
        "nodes": [
            node_data(person, counts[person.pk], person.pk == source_id) for person in people
        ],
        "edges": [edge_data(pair, weight, shared) for pair, (weight, shared) in links.items()],
        "excluded": excluded,
    }


def coauthorships(by_publication, members):
    """
    {(author id, author id): [weight, shared publications]} between members, in a stable
    order, and the number of large collaborations that would have linked two members.
    """
    links = defaultdict(lambda: [0.0, 0])
    excluded = 0
    for publication_id in sorted(by_publication):
        authors = by_publication[publication_id]
        linked = sorted(authors & members)
        if len(linked) < 2:
            continue
        if len(authors) > LARGE_COLLABORATION:
            excluded += 1
            continue
        weight = 1 / (len(authors) - 1)
        for pair in combinations(linked, 2):
            links[pair][0] += weight
            links[pair][1] += 1
    return dict(sorted(links.items())), excluded


def publication_counts(by_publication):
    counts = defaultdict(int)
    for authors in by_publication.values():
        for author_id in authors:
            counts[author_id] += 1
    return counts


def node_data(person, publications, is_source):
    name = str(person) or "(sans nom)"
    return {
        "data": {
            "id": str(person.pk),
            "label": name,
            # Next to the node on an exported image (#289).
            "shortLabel": person.last_name or name,
            "publications": publications,
            # The author of the graph stands out, like the publication of its graph.
            "role": "source" if is_source else "other",
            "url": reverse("author_detail", args=[person.pk]),
        }
    }


def edge_data(pair, weight, shared):
    first, second = pair
    return {
        "data": {
            "id": f"{first}-{second}",
            "source": str(first),
            "target": str(second),
            "weight": round(weight, 4),
            "shared": shared,
        }
    }
