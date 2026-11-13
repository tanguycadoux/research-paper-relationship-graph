from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from ..models import Publication
from ..services.display.graph import base_graph, corpus_graph, publication_graph
from ..services.display.graph_variants import graph_layout, variant_links


def graph_context(request, graph, kind, **extra):
    """The graph, its kind, and the variants of its layout chosen in the URL (#288)."""
    return {
        "graph": graph,
        "graph_kind": kind,
        "graph_layout": graph_layout(request.GET),
        "graph_variants": variant_links(request.GET, graph),
        **extra,
    }


def pub_graph(request, pk):
    pub = get_object_or_404(Publication, pk=pk)
    context = graph_context(request, publication_graph(pub), "publication", publication=pub)
    return render(request, "references/publication_graph.html", context)


@login_required
def my_refs_graph(request):
    context = graph_context(request, corpus_graph(request.user), "corpus")
    return render(request, "references/user_references_graph.html", context)


def base_graph_view(request):
    """The whole base, for everyone, like the list of publications (#131)."""
    context = graph_context(request, base_graph(request.user), "base")
    return render(request, "references/base_graph.html", context)
