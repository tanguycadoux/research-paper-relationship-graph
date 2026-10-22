from django.db.models import Count, Prefetch, Q
from django.urls import reverse

from ..models import AuthorPublication, CitedReference, Publication


def publication_graph(pub):
    """
    Graph of a publication, the publications it cites and those of the base that
    cite it (#186): a publication without identified references is not empty.
    """
    return citation_graph([pub.pk], with_citing=True)


def corpus_graph(user):
    """Graph of the corpus of a user and the publications it cites."""
    source_ids = list(user.userpublication_set.values_list("publication_id", flat=True))
    return citation_graph(source_ids)


def citation_graph(source_ids, with_citing=False):
    """
    Return the graph as Cytoscape.js elements: one node per publication, one edge
    per resolved citation from a source publication, and with_citing, one per
    citation of a source publication by another one.
    """
    links = Q(source_id__in=source_ids)
    if with_citing:
        links |= Q(target_id__in=source_ids)
    edges = list(
        CitedReference.objects.filter(links, target__isnull=False)
        .values_list("source_id", "target_id")
        .distinct()
    )
    node_ids = set(source_ids) | {pk for edge in edges for pk in edge}
    # Publications that cite a source without being one (#139: their own colour).
    citing_ids = {source for source, target in edges if target in source_ids} - set(source_ids)
    publications = (
        Publication.objects.filter(pk__in=node_ids)
        .annotate(cited_by=Count("citations"))
        .prefetch_related(
            Prefetch(
                "authorpublication_set",
                queryset=AuthorPublication.objects.select_related("author").order_by("order"),
            )
        )
    )
    return {
        "nodes": [node_data(pub, role(pub.pk, source_ids, citing_ids)) for pub in publications],
        "edges": [edge_data(source_id, target_id) for source_id, target_id in edges],
    }


def role(pk, source_ids, citing_ids):
    """source: the publication or the corpus; citing: cites a source; cited: cited only."""
    if pk in source_ids:
        return "source"
    return "citing" if pk in citing_ids else "cited"


def node_data(pub, role):
    # Each person once, even with several slots after a merge.
    authors = list(dict.fromkeys(str(slot.author) for slot in pub.authorpublication_set.all()))
    return {
        "data": {
            "id": str(pub.pk),
            "label": str(pub),
            "date": pub.publication_date.isoformat() if pub.publication_date else None,
            "doi": pub.doi,
            "isbn": pub.isbn,
            # « First author et al. » on the information card.
            "firstAuthor": authors[0] if authors else "",
            "authorCount": len(authors),
            "citedBy": pub.cited_by,
            "role": role,
            "url": reverse("publication_detail", args=[pub.pk]),
        }
    }


def edge_data(source_id, target_id):
    return {
        "data": {
            "id": f"{source_id}-{target_id}",
            "source": str(source_id),
            "target": str(target_id),
        }
    }
