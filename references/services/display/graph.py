from django.db.models import CharField, Count, OuterRef, Q, Subquery
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Coalesce
from django.urls import reverse

from ...models import CitedReference, ExternalRecord, Publication, to_identify_q
from ..corpus.tags import context_publications
from ..sources.external_records import Source
from .graph_levels import Expansion, levels_of
from .publication_details import clean_text


def publication_graph(pub, expansion=None, query=None, user=None):
    """
    Graph of a publication, the publications it cites and those of the base that
    cite it (#186): a publication without identified references is not empty. Beyond,
    as far as expansion goes (#451); query: that of the page, for the links of the nodes;
    user: logged in, the references to identify are shown (#452).
    """
    return citation_graph([pub.pk], with_citing=True, expansion=expansion, query=query, user=user)


def corpus_graph(user, tag="", expansion=None, query=None):
    """
    Graph of the corpus of a user and the publications it cites; with a tag, of the
    publications with the tag or one of its descendants only (#290). Beyond, as far as
    expansion goes (#451).
    """
    source_ids = list(context_publications(user, tag).values_list("pk", flat=True))
    return citation_graph(source_ids, expansion=expansion, query=query, user=user)


def base_graph(user):
    """
    Graph of the whole base (#131), publications without identified citations
    included: the corpus of a logged-in user stands out (source), the others are
    plain publications of the base (base: a neutral grey, #477).
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
    graph = elements(
        Publication.objects.all(),
        edges,
        lambda pk: "source" if pk in corpus_ids else "base",
        user,
    )
    for node in graph["nodes"]:
        add_tooltip(node["data"])
    return graph


def links(pks, with_citing):
    """
    The resolved citations from the publications pks, and with_citing, of them: a set of
    (citing, cited).
    """
    condition = Q(source_id__in=pks)
    if with_citing:
        condition |= Q(target_id__in=pks)
    return set(
        CitedReference.objects.filter(condition, target__isnull=False)
        .values_list("source_id", "target_id")
        # Without the default ordering, whose position would make duplicates distinct.
        .order_by()
        .distinct()
    )


def citation_graph(source_ids, with_citing=False, expansion=None, query=None, user=None):
    """
    Return the graph as Cytoscape.js elements: one node per publication, one edge
    per resolved citation from a source publication, and with_citing, one per
    citation of a source publication by another one. Level 1 is the publications so
    linked; the expanded ones of level 1 (#451) bring their own citations, both ways.
    """
    expansion = expansion or Expansion()
    first = links(source_ids, with_citing)
    level_one = {pk for edge in first for pk in edge} - set(source_ids)
    expanded = expansion.expanded(level_one)
    edges = sorted(first | links(expanded, with_citing=True)) if expanded else sorted(first)
    node_ids = set(source_ids) | {pk for edge in edges for pk in edge}
    # Publications that cite a source without being one (#139: their own colour).
    citing_ids = {source for source, target in first if target in source_ids} - set(source_ids)
    levels = levels_of(source_ids, level_one)
    graph = elements(
        Publication.objects.filter(pk__in=node_ids),
        edges,
        lambda pk: role(pk, source_ids, citing_ids),
        user,
    )
    for node in graph["nodes"]:
        add_level(node["data"], levels.get(int(node["data"]["id"]), 2), expansion, expanded, query)
        add_tooltip(node["data"])
    return graph


def add_level(data, level, expansion, expanded, query):
    """
    The level of a node (#451); a node of level 1 also says whether its neighbours are
    shown, and the query string that develops or reduces it.
    """
    data["level"] = level
    if level == 1:
        pk = int(data["id"])
        data["expanded"] = pk in expanded
        if query is not None:
            data["toggle"] = expansion.toggle_query(query, pk, pk in expanded)


def add_tooltip(data):
    """
    A longer tooltip than the title when the node has more to say: its references to
    identify (#452). Its level, or its distance to the selected node, is added by the page
    (graph/hover.js, #477).
    """
    lines = [data["label"]]
    if data.get("toIdentify"):
        lines.append(to_identify_text(data["toIdentify"]))
    if len(lines) > 1:
        data["tooltip"] = "\n".join(lines)


def to_identify_text(count):
    return f"{count} référence{'s' if count > 1 else ''} à identifier"


def to_identify_annotations():
    """
    The number of references to identify of a publication and the position of the first
    one (#452): in the query of the nodes, without any query per node. Subqueries, so as
    not to multiply the citations counted beside.
    """
    references = CitedReference.objects.filter(to_identify_q(), source=OuterRef("pk")).order_by()
    return {
        "to_identify": Coalesce(
            Subquery(references.values("source").annotate(n=Count("pk")).values("n")), 0
        ),
        "first_to_identify": Subquery(references.order_by("position").values("position")[:1]),
    }


def add_to_identify(data, pub):
    """
    The references to identify of a publication (#452), whether it is in the corpus of the
    user or not (decided by the user): a reference to identify is a link the graph lacks.
    The link starts the identification in series at the first one (#242).
    """
    if getattr(pub, "to_identify", 0):
        data["toIdentify"] = pub.to_identify
        url = reverse("reference_identify", args=[pub.pk, pub.first_to_identify])
        data["identifyUrl"] = f"{url}?serie=1"


def elements(publications, edges, role_of, user=None):
    """
    The nodes of the publications, with the role role_of gives each, and the edges; for
    a logged-in user, who alone can identify them, the references to identify (#452).
    """
    publications = publications.annotate(cited_by=Count("citations"), venue=venue())
    if user is not None and user.is_authenticated:
        publications = publications.annotate(**to_identify_annotations())
    publications = publications.with_author_slots()
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
    node = {
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
    add_to_identify(node["data"], pub)
    return node


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
