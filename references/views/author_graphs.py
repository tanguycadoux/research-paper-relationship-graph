"""
Coauthorship graphs (#222): of an author, from their page, of all the authors, and of
the authors of the user's corpus or of one of its tags (#422). The probable duplicates
are gathered into one node by default, without changing the base; ?doublons=separes
draws the base as it is (#419).
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from ..models import Author, GraphImage
from ..services.corrections import author_distinctions
from ..services.display import graph_images
from ..services.display.author_graph import (
    LARGE_COLLABORATION,
    all_authors_graph,
    author_graph,
    corpus_authors_graph,
)
from ..services.display.author_groups import probable_groups
from .graphs import corpus_graph_choices, tag_context
from .redirects import redirect_to_next

# In the query string: the probable duplicates drawn apart, as in the base (#419).
DUPLICATES_PARAM = "doublons"
SEPARATE = "separes"


def is_grouped(request):
    """The probable duplicates are gathered, unless the URL asks for the base as it is."""
    return request.GET.get(DUPLICATES_PARAM) != SEPARATE


def toggle_query(request):
    """The query string of the same graph with the other choice, other parameters kept."""
    query = request.GET.copy()
    if is_grouped(request):
        query[DUPLICATES_PARAM] = SEPARATE
    else:
        query.pop(DUPLICATES_PARAM, None)
    return query.urlencode()


def graph_context(request, graph, export_name, **extra):
    grouped = is_grouped(request)
    return {
        "graph": graph,
        # The name of the exported image (graph/export.js), which says when the
        # duplicates are apart.
        "graph_export": export_name if grouped else f"{export_name}-doublons-separes",
        "large_collaboration": LARGE_COLLABORATION,
        "duplicates_grouped": grouped,
        "duplicates_toggle": toggle_query(request),
        # Kept by the tag selector of the graph of a corpus (_graph_tag_form.html).
        "graph_kept_params": {} if grouped else {DUPLICATES_PARAM: SEPARATE},
        # After a number of publications: on the card, and in the legend.
        "publications_scope": "dans la base",
        **extra,
    }


def author_graph_view(request, pk):
    author = get_object_or_404(Author, pk=pk)
    graph = author_graph(author, groups=probable_groups(), grouped=is_grouped(request))
    context = graph_context(request, graph, f"graphe-auteur-{author.pk}", author=author)
    return render(request, "references/author_graph.html", context)


def authors_graph_view(request):
    """
    Every author of the base, for everyone, like the list of authors; beyond
    graph_images.LARGE_GRAPH of them, its full image, computed in the background (#328).
    """
    if graph_images.is_large(GraphImage.Kind.AUTHORS):
        context = {"large_graph": graph_images.image_state(GraphImage.Kind.AUTHORS)}
    else:
        graph = all_authors_graph(groups=probable_groups(), grouped=is_grouped(request))
        context = graph_context(request, graph, "graphe-auteurs")
    return render(request, "references/authors_graph.html", context)


@login_required
def corpus_authors_graph_view(request):
    """
    The authors of the publications of the corpus, or of a tag with its subtags (#422),
    as « Mon graphe » shows its publications: the publications it only cites are left out.
    """
    tagging = tag_context(request)
    tag = tagging["active_tag"]
    graph = corpus_authors_graph(
        request.user, tag, groups=probable_groups(), grouped=is_grouped(request)
    )
    # Like « Mon graphe »: graphe-auteurs-corpus-tag-projet-groupe.
    export_name = "graphe-auteurs-corpus"
    if tag:
        export_name += f"-tag-{tagging['active_tag_slug']}"
    context = graph_context(
        request,
        graph,
        export_name,
        corpus_graphs=corpus_graph_choices(tag, "corpus_authors_graph"),
        publications_scope="dans ce tag" if tag else "dans le corpus",
        **tagging,
    )
    return render(request, "references/corpus_authors_graph.html", context)


@login_required
@require_POST
def author_graph_distinct_view(request):
    """
    « Ce ne sont pas les mêmes » on a gathered node (#419): the checked authors are
    declared different people, as on the page of probable duplicates, then back to
    the graph.
    """
    pks = [pk for pk in request.POST.getlist("authors") if pk.isdigit()]
    authors = list(Author.objects.filter(pk__in=pks))
    if len(authors) < 2:
        messages.error(request, "Cochez au moins deux auteurs.")
    else:
        author_distinctions.declare_distinct(authors, request.user)
        names = ", ".join(str(author) for author in authors)
        messages.success(request, f"Ne seront plus regroupés : {names}.")
    return redirect_to_next(request, "authors_graph")
