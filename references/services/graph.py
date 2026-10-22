from django.db.models import Count, Prefetch
from django.urls import reverse

from ..models import AuthorPublication, CitedReference, Publication


def publication_graph(pub):
    """Graph of a publication and the publications it cites."""
    return citation_graph([pub.pk])


def corpus_graph(user):
    """Graph of the corpus of a user and the publications it cites."""
    source_ids = list(user.userpublication_set.values_list("publication_id", flat=True))
    return citation_graph(source_ids)


def citation_graph(source_ids):
    """
    Return the graph as Cytoscape.js elements: one node per publication, one edge
    per resolved citation from a source publication.
    """
    edges = list(
        CitedReference.objects.filter(source_id__in=source_ids, target__isnull=False)
        .values_list("source_id", "target_id")
        .distinct()
    )
    node_ids = set(source_ids) | {target_id for _, target_id in edges}
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
        "nodes": [node_data(pub, pub.pk in source_ids) for pub in publications],
        "edges": [edge_data(source_id, target_id) for source_id, target_id in edges],
    }


def node_data(pub, is_source):
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
            "isSource": is_source,
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
