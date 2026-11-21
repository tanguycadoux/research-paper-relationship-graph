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
the authors. With the groups of probable duplicates (author_groups.py, #419), the
members of a group in the graph are one node: their publications are counted once, and
their links with another author add up.
"""

from collections import defaultdict
from itertools import combinations

from django.db.models import Count, Q
from django.urls import reverse

from ...models import Author, AuthorPublication, Publication
from .author_groups import gathered_publications, graph_groups

# Beyond this many authors, a publication links nobody (decision of #222).
LARGE_COLLABORATION = 50


def all_authors_graph(groups=(), grouped=True):
    """
    Every author of the base with at least one publication, and every coauthorship.
    groups, grouped: see coauthorship_graph.
    """
    slots = AuthorPublication.objects.all()
    authors = Author.objects.filter(pk__in=AuthorPublication.objects.values("author_id"))
    return coauthorship_graph(slots, authors, groups=groups, grouped=grouped)


def author_graph(author, groups=(), grouped=True):
    """
    The author, their coauthors (on publications of at most LARGE_COLLABORATION authors)
    and the links between all of them, through any of their publications. groups,
    grouped: see coauthorship_graph.
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
    return coauthorship_graph(slots, members, source_id=author.pk, groups=groups, grouped=grouped)


def publication_authors(slots):
    """{publication id: set of author ids}: each person once, even with several slots."""
    authors = defaultdict(set)
    for publication_id, author_id in slots.values_list("publication_id", "author_id").order_by():
        authors[publication_id].add(author_id)
    return authors


def coauthorship_graph(slots, authors, source_id=None, groups=(), grouped=True):
    """
    The Cytoscape elements of the authors and of their coauthorships through the
    publications of the slots, which must hold every publication of every author.
    groups: the probable duplicates (author_groups.probable_groups); those with at least
    two authors in the graph are counted ("groups"), and gathered into one node unless
    grouped is false.
    """
    by_publication = publication_authors(slots)
    people = list(authors.order_by("last_name", "first_name", "pk"))
    if source_id is not None:
        # The author of the graph first: at the centre of the starting spiral (network.js).
        people.sort(key=lambda person: person.pk != source_id)
    gathered = graph_groups(people, groups, source_id)
    group_count = sum(len(members) > 1 for members in gathered.values())
    if not grouped:
        gathered = {person.pk: [person] for person in people}
    counts = publication_counts(by_publication)
    by_node = gathered_publications(by_publication, gathered)
    links, excluded = coauthorships(by_node, set(gathered))
    node_counts = publication_counts(by_node)
    return {
        "nodes": [
            node_data(members, node_counts[pk], counts, pk == source_id)
            for pk, members in gathered.items()
        ],
        "edges": [edge_data(pair, weight, shared) for pair, (weight, shared) in links.items()],
        "excluded": excluded,
        "groups": group_count,
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


def node_data(members, publications, counts, is_source):
    """
    One author, or the probable duplicates gathered under the first of members (#419):
    publications counts each of their publications once; counts gives those of each
    variant.
    """
    person = members[0]
    name = str(person) or "(sans nom)"
    data = {
        "id": str(person.pk),
        "label": name,
        # Next to the node on an exported image (#289).
        "shortLabel": person.last_name or name,
        "publications": publications,
        # The author of the graph stands out, like the publication of its graph.
        "role": "source" if is_source else "other",
        "url": reverse("author_detail", args=[person.pk]),
    }
    if len(members) > 1:
        # Outlined on the graph, its variants listed on hover and on the card.
        data["grouped"] = True
        data["variants"] = [
            variant_data(member, counts[member.pk])
            for member in sorted(members, key=lambda m: (-counts[m.pk], str(m), m.pk))
        ]
    return {"data": data}


def variant_data(person, publications):
    return {
        "id": person.pk,
        "label": str(person) or "(sans nom)",
        "publications": publications,
        "url": reverse("author_detail", args=[person.pk]),
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
