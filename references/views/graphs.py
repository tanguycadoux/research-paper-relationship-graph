from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from plotly.offline import plot

from ..models import Publication, UserPublication
from ..services.graph import build_pub_graph, build_user_refs_graph, plotly_graph_from_nx


def pub_graph(request, pk):
    pub = get_object_or_404(Publication, pk=pk)

    G = build_pub_graph(pub)
    fig = plotly_graph_from_nx(G, [pub.pk])
    plot_div = plot(
        fig,
        output_type="div",
        include_plotlyjs=True,
        config={"responsive": True, "displayModeBar": False},
    )

    return render(request, "references/publication_graph.html", {"plot_div": plot_div})


@login_required
def my_refs_graph(request):
    G = build_user_refs_graph(request.user)
    user_pub_ids = set(
        UserPublication.objects.filter(user=request.user).values_list("publication_id", flat=True)
    )

    fig = plotly_graph_from_nx(G, user_pub_ids)
    plot_div = plot(
        fig,
        output_type="div",
        include_plotlyjs=True,
        config={"responsive": True, "displayModeBar": False},
    )

    return render(request, "references/user_references_graph.html", {"plot_div": plot_div})
