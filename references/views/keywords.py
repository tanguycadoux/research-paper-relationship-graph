"""The map of the keywords of « Mon corpus », or of a tag (#418)."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.text import slugify

from ..services.corpus import tags
from ..services.display import keyword_graph
from .tag_context import requested_tag


def kind_links(query, current):
    """« Mots-clés » or « Thèmes », as the variants of a graph (_graph_variants.html)."""
    options = []
    for field, terms in keyword_graph.KINDS.items():
        params = query.copy()
        params["kind"] = field
        options.append(
            {"label": terms.label, "query": params.urlencode(), "current": terms is current}
        )
    return [{"label": "Termes", "options": options}]


def kept_params(terms, minimum):
    """
    What the forms of the page keep (the tag, the threshold): the choices made. A
    threshold only when one was asked: the default depends on the corpus or the tag (#468).
    """
    kept = {}
    if terms is not keyword_graph.KEYWORDS:
        kept["kind"] = terms.field
    if minimum is not None:
        kept["min"] = minimum
    return kept


@login_required
def corpus_keywords(request):
    tag, tag_tree = requested_tag(request)
    terms = keyword_graph.requested_kind(request.GET)
    requested = keyword_graph.requested_minimum(request.GET)
    graph = keyword_graph.keyword_graph(request.user, tag, terms, requested)
    kept = kept_params(terms, requested and graph["minimum"])
    context = {
        "graph": graph,
        "terms": terms,
        "minimum": graph["minimum"],
        "most_terms": keyword_graph.MOST_TERMS,
        "graph_variants": kind_links(request.GET, terms),
        "variants_label": "Mots-clés ou thèmes",
        # The tag form keeps the kind and the threshold, the threshold form the kind.
        "graph_kept_params": kept,
        "threshold_kept_params": {key: value for key, value in kept.items() if key != "min"},
        "tag_choices": [
            (item["path"], f"{tags.label(item['path'])} ({item['count']})") for item in tag_tree
        ],
        "active_tag": tag,
        "active_tag_label": tags.label(tag),
        "graph_export": export_name(terms, tag),
    }
    return render(request, "references/corpus_keywords.html", context)


def export_name(terms, tag):
    """graphe-mots-cles, graphe-themes-tag-projet-groupe…"""
    name = f"graphe-{slugify(terms.plural)}"
    return f"{name}-tag-{slugify(tag.replace('/', ' '))}" if tag else name
