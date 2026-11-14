from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.utils.text import slugify

from ..models import Publication
from ..services.corpus import tags
from ..services.display.graph import base_graph, corpus_graph, publication_graph
from .tag_context import requested_tag


def pub_graph(request, pk):
    pub = get_object_or_404(Publication, pk=pk)
    context = {"publication": pub, "graph": publication_graph(pub), "graph_kind": "publication"}
    return render(request, "references/publication_graph.html", context)


@login_required
def my_refs_graph(request):
    """The graph of the corpus, or of one of its tags with its subtags (#290)."""
    tag, tag_tree = requested_tag(request)
    context = {
        "graph": corpus_graph(request.user, tag),
        "graph_kind": "corpus",
        # « Projet › Groupe (3) »: the choices of the tag selector.
        "tag_choices": [
            (item["path"], f"{tags.label(item['path'])} ({item['count']})") for item in tag_tree
        ],
        "active_tag": tag,
        "active_tag_label": tags.label(tag),
        # In the name of the exported image: « Projet/Groupe » gives projet-groupe.
        "active_tag_slug": slugify(tag.replace("/", " ")),
    }
    return render(request, "references/user_references_graph.html", context)


def base_graph_view(request):
    """The whole base, for everyone, like the list of publications (#131)."""
    context = {"graph": base_graph(request.user), "graph_kind": "base"}
    return render(request, "references/base_graph.html", context)
