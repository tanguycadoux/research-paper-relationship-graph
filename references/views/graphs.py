from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.text import slugify

from ..models import GraphImage, Publication
from ..services.corpus import tags
from ..services.display import graph_images
from ..services.display.graph import base_graph, corpus_graph, publication_graph
from ..services.display.graph_variants import graph_layout, kept_params, variant_links
from .tag_context import requested_tag


def graph_context(request, graph, kind, **extra):
    """The graph, its kind, and its variants chosen in the URL (#195): timeline or network."""
    return {
        "graph": graph,
        "graph_kind": kind,
        "graph_layout": graph_layout(request.GET),
        "graph_variants": variant_links(request.GET),
        "graph_kept_params": kept_params(request.GET),
        **extra,
    }


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
    context = graph_context(request, publication_graph(pub), "publication", publication=pub)
    return render(request, "references/publication_graph.html", context)


@login_required
def my_refs_graph(request):
    """The graph of the corpus, or of one of its tags with its subtags (#290)."""
    tagging = tag_context(request)
    tag = tagging["active_tag"]
    context = graph_context(
        request,
        corpus_graph(request.user, tag),
        "corpus",
        corpus_graphs=corpus_graph_choices(tag, "corpus_graph"),
        **tagging,
    )
    return render(request, "references/user_references_graph.html", context)


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
