from django.db.models import CharField, Count, OuterRef, Q, Subquery
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Coalesce
from django.urls import reverse

from ...models import CitedReference, ExternalRecord, Publication
from ..corpus.tags import context_publications
from ..sources.external_records import Source
from .publication_details import clean_text


def publication_graph(pub):
    """
    Graph of a publication, the publications it cites and those of the base that
    cite it (#186): a publication without identified references is not empty.
    """
    return citation_graph([pub.pk], with_citing=True)


def corpus_graph(user, tag=""):
    """
    Graph of the corpus of a user and the publications it cites; with a tag, of the
    publications with the tag or one of its descendants only (#290).
    """
    source_ids = list(context_publications(user, tag).values_list("pk", flat=True))
    return citation_graph(source_ids)


def base_graph(user):
    """
    Graph of the whole base (#131), publications without identified citations
    included: the corpus of a logged-in user stands out (source), the others are
    plain publications of the base (other).
    """
    corpus_ids = (
        set(user.userpublication_set.values_list("publication_id", flat=True))
        if user.is_authenticated
        else set()
    )
    edges = list(
        CitedReference.objects.filter(target__isnull=False)
        .values_list("source_id", "target_id")
        # Without the default ordering, whose position would make duplicates distinct.
        .order_by()
        .distinct()
    )
    return elements(
        Publication.objects.all(), edges, lambda pk: "source" if pk in corpus_ids else "other"
    )


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
        # Without the default ordering, whose position would make duplicates distinct.
        .order_by()
        .distinct()
    )
    node_ids = set(source_ids) | {pk for edge in edges for pk in edge}
    # Publications that cite a source without being one (#139: their own colour).
    citing_ids = {source for source, target in edges if target in source_ids} - set(source_ids)
    return elements(
        Publication.objects.filter(pk__in=node_ids),
        edges,
        lambda pk: role(pk, source_ids, citing_ids),
    )


def elements(publications, edges, role_of):
    """The nodes of the publications, with the role role_of gives each, and the edges."""
    publications = publications.annotate(
        cited_by=Count("citations"), venue=venue()
    ).with_author_slots()
    return {
        "nodes": [node_data(pub, role_of(pub.pk)) for pub in publications],
        "edges": [edge_data(source_id, target_id) for source_id, target_id in edges],
    }


def stored_value(source, *path):
    """A text value of the stored answer of a source, read by the database (#187)."""
    *keys, last = path
    value = "data"
    for key in keys:
        value = KeyTransform(key, value)
    records = ExternalRecord.objects.filter(publication=OuterRef("pk"), source=source)
    return Subquery(records.annotate(value=KeyTextTransform(last, value)).values("value")[:1])


def venue():
    """Journal or proceedings: Crossref, else DataCite. Read in the same query."""
    return Coalesce(
        stored_value(Source.CROSSREF, "message", "container-title", "0"),
        stored_value(Source.DATACITE, "data", "attributes", "container", "title"),
        output_field=CharField(),
    )


def role(pk, source_ids, citing_ids):
    """source: the publication or the corpus; citing: cites a source; cited: cited only."""
    if pk in source_ids:
        return "source"
    return "citing" if pk in citing_ids else "cited"


def node_data(pub, role):
    # Each person once, even with several slots after a merge.
    people = list(dict.fromkeys(slot.author for slot in pub.authorpublication_set.all()))
    authors = [str(person) for person in people]
    return {
        "data": {
            "id": str(pub.pk),
            "label": str(pub),
            "date": pub.publication_date.isoformat() if pub.publication_date else None,
            # « First author et al. » on the information card.
            "firstAuthor": authors[0] if authors else "",
            "authorCount": len(authors),
            # « Vaswani 2017 » next to the node on an exported image (#289).
            "shortLabel": short_label(pub, people[0] if people else None),
            "citedBy": pub.cited_by,
            "role": role,
            "venue": clean_text(pub.venue or ""),
            "url": reverse("publication_detail", args=[pub.pk]),
        }
    }


# Without an author, the start of the title stands for the publication, cut at a word.
SHORT_TITLE_LENGTH = 30


def short_label(pub, first_author):
    """The family name of the first author and the year; the start of the title without author."""
    if first_author is not None:
        name = first_author.last_name or str(first_author)
    else:
        name = short_title(str(pub))
    year = str(pub.publication_date.year) if pub.publication_date else ""
    return " ".join(part for part in (name, year) if part)


def short_title(title):
    if len(title) <= SHORT_TITLE_LENGTH:
        return title
    return title[:SHORT_TITLE_LENGTH].rsplit(" ", 1)[0].rstrip(" ,:;.-") + "…"


def edge_data(source_id, target_id):
    return {
        "data": {
            "id": f"{source_id}-{target_id}",
            "source": str(source_id),
            "target": str(target_id),
        }
    }
