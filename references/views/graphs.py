from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.cache import add_never_cache_headers, patch_vary_headers
from django.utils.http import urlencode
from django.utils.text import slugify

from ..models import GraphImage, Publication
from ..services.corpus import tags
from ..services.display import graph_images
from ..services.display.graph import base_graph, corpus_graph, publication_graph
from ..services.display.graph_levels import (
    Expansion,
    bibliography_request_url,
    missing_bibliographies,
)
from ..services.display.graph_variants import (
    LEVEL_VARIANTS,
    VARIANTS,
    graph_layout,
    kept_params,
    variant_links,
)
from .tag_context import requested_tag


def graph_context(request, graph, kind, variants=VARIANTS, **extra):
    """
    The graph, its kind, and its variants chosen in the URL (#195): timeline or network,
    and the level of the graphs that have one (#451).
    """
    return {
        "graph": graph,
        "graph_kind": kind,
        "graph_layout": graph_layout(request.GET),
        "graph_variants": variant_links(request.GET, variants),
        "graph_kept_params": kept_params(request.GET, variants),
        **extra,
    }


def levels_context(request, graph, **start):
    """
    What the panel says of the levels (#451): the bibliographies they lack, and for a
    logged-in user « Récupérer les bibliographies… » from the same start (#431).
    """
    return {
        "variants": LEVEL_VARIANTS,
        "graph_level": Expansion.of(request.GET).level,
        "graph_beyond": any(node["data"]["level"] == 2 for node in graph["nodes"]),
        "missing_bibliographies": missing_bibliographies(graph),
        "bibliography_request_url": request.user.is_authenticated
        and bibliography_request_url(**start),
    }


# The parts of the panel that change with the level or a publication developed (#451),
# rendered as on the page: their template, by the key of the JSON answer.
PANEL_PARTS = {
    "summary": "references/_citation_graph_summary.html",
    "legend": "references/_citation_graph_legend.html",
    "variants": "references/_graph_variants.html",
}


def wants_elements(request):
    """
    graph/expand.js asks for the elements of the graph, not the page (#451): same view,
    same query string, Accept: application/json.
    """
    return request.headers.get("Accept", "").startswith("application/json")


def graph_elements(request, context):
    """
    The graph for another expansion, without reloading the page (#451): its elements
    (each node with its level and toggle), its level, its counts, the bibliographies it
    lacks, and the parts of the panel rendered as on the page.
    """
    graph = context["graph"]
    response = JsonResponse(
        {
            "graph": graph,
            "level": context["graph_level"],
            "counts": {"publications": len(graph["nodes"]), "citations": len(graph["edges"])},
            "missing_bibliographies": context["missing_bibliographies"],
            "kept_params": context["graph_kept_params"],
            **{key: render_to_string(name, context, request) for key, name in PANEL_PARTS.items()},
        }
    )
    # Never kept by the browser: Back shows the page of the URL, not these elements.
    add_never_cache_headers(response)
    return response


def render_graph(request, template, context):
    """The page of a graph with levels, or its elements for graph/expand.js (#451)."""
    response = (
        graph_elements(request, context)
        if wants_elements(request)
        else render(request, template, context)
    )
    patch_vary_headers(response, ["Accept"])
    return response


def corpus_graph_choices(tag, current):
    """
    The two graphs of the corpus, or of a tag (#422): its publications (« Mon graphe »)
    and its authors, as (label, URL with the tag, is current); the tag is kept, not the
    variants of the other graph.
    """
    query = f"?{urlencode({'tag': tag})}" if tag else ""
    return [
        (label, reverse(name) + query, name == current)
        for label, name in [("Publications", "corpus_graph"), ("Auteurs", "corpus_authors_graph")]
    ]


def tag_context(request):
    """The tag asked in ?tag= (#290), and what the graph of a corpus says about it."""
    tag, tag_tree = requested_tag(request)
    return {
        # « Projet › Groupe (3) »: the choices of the tag selector.
        "tag_choices": [
            (item["path"], f"{tags.label(item['path'])} ({item['count']})") for item in tag_tree
        ],
        "active_tag": tag,
        "active_tag_label": tags.label(tag),
        # In the name of the exported image: « Projet/Groupe » gives projet-groupe.
        "active_tag_slug": slugify(tag.replace("/", " ")),
    }


def pub_graph(request, pk):
    pub = get_object_or_404(Publication, pk=pk)
    graph = publication_graph(pub, Expansion.of(request.GET), request.GET)
    context = graph_context(
        request,
        graph,
        "publication",
        publication=pub,
        **levels_context(request, graph, publication=pub),
    )
    return render_graph(request, "references/publication_graph.html", context)


@login_required
def my_refs_graph(request):
    """The graph of the corpus, or of one of its tags with its subtags (#290)."""
    tagging = tag_context(request)
    tag = tagging["active_tag"]
    graph = corpus_graph(request.user, tag, Expansion.of(request.GET), request.GET)
    context = graph_context(
        request,
        graph,
        "corpus",
        corpus_graphs=corpus_graph_choices(tag, "corpus_graph"),
        **tagging,
        **levels_context(request, graph, tag=tag),
    )
    return render_graph(request, "references/user_references_graph.html", context)


def base_graph_view(request):
    """
    The whole base, for everyone, like the list of publications (#131); beyond
    graph_images.LARGE_GRAPH publications, its full image, computed in the background
    (#328).
    """
    if graph_images.is_large(GraphImage.Kind.BASE):
        context = {"large_graph": graph_images.image_state(GraphImage.Kind.BASE)}
    else:
        context = graph_context(request, base_graph(request.user), "base")
    return render(request, "references/base_graph.html", context)
