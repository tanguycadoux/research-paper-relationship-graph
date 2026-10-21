from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from ..models import Publication
from ..services.graph import corpus_graph, publication_graph


def pub_graph(request, pk):
    pub = get_object_or_404(Publication, pk=pk)
    context = {"publication": pub, "graph": publication_graph(pub)}
    return render(request, "references/publication_graph.html", context)


@login_required
def my_refs_graph(request):
    context = {"graph": corpus_graph(request.user)}
    return render(request, "references/user_references_graph.html", context)
