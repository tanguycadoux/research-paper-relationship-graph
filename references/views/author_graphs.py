"""Coauthorship graphs (#222): of an author, from their page, and of all the authors."""

from django.shortcuts import get_object_or_404, render

from ..models import Author
from ..services.display.author_graph import LARGE_COLLABORATION, all_authors_graph, author_graph


def graph_context(graph, export_name, **extra):
    return {
        "graph": graph,
        # The name of the exported image (graph/export.js).
        "graph_export": export_name,
        "large_collaboration": LARGE_COLLABORATION,
        **extra,
    }


def author_graph_view(request, pk):
    author = get_object_or_404(Author, pk=pk)
    context = graph_context(author_graph(author), f"graphe-auteur-{author.pk}", author=author)
    return render(request, "references/author_graph.html", context)


def authors_graph_view(request):
    """Every author of the base, for everyone, like the list of authors."""
    context = graph_context(all_authors_graph(), "graphe-auteurs")
    return render(request, "references/authors_graph.html", context)
