"""The full images of the graphs too large for the page (#328)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import GraphImage
from ..services.display import graph_images

PAGES = {GraphImage.Kind.AUTHORS: "authors_graph", GraphImage.Kind.BASE: "base_graph"}


def known_kind(kind):
    if kind not in GraphImage.Kind.values:
        raise Http404("Pas de tel graphe.")
    return kind


@login_required
@require_POST
def generate_graph_image(request, kind):
    """Start computing the image in the background, and come back to the graph page."""
    kind = known_kind(kind)
    if graph_images.request_image(kind, request.user):
        messages.info(request, "Calcul de l'image lancé : la page se mettra à jour seule.")
    else:
        messages.info(request, "L'image est déjà en cours de calcul.")
    return redirect(PAGES[kind])


def graph_image_viewer(request, kind):
    """
    The page that browses the image (#453): zoom, minimap and the list of its nodes, the
    image and the list fetched by its script.
    """
    kind = known_kind(kind)
    image = done_image(kind, "svg")
    return render(
        request,
        "references/graph_image_viewer.html",
        {
            "image": image,
            "kind": kind,
            "graph_page": PAGES[kind],
            "noun": "auteurs" if kind == GraphImage.Kind.AUTHORS else "publications",
            "browsable": bool(image.node_list),
        },
    )


def graph_image_nodes(request, kind):
    """The nodes of the image and their edges (JSON), for the page that browses it."""
    image = done_image(known_kind(kind), "svg")
    return HttpResponse(image.node_list or "{}", content_type="application/json")


def done_image(kind, *deferred):
    image = (
        GraphImage.objects.filter(kind=kind, status=GraphImage.Status.DONE).defer(*deferred).first()
    )
    if image is None:
        raise Http404("Pas encore d'image de ce graphe.")
    return image


def graph_image_svg(request, kind):
    """The image, for everyone like the graph pages; opened in the browser."""
    image = done_image(known_kind(kind), "node_list")
    response = HttpResponse(image.svg, content_type="image/svg+xml; charset=utf-8")
    day = timezone.localtime(image.finished_at).date().isoformat()
    name = "graphe-auteurs" if kind == GraphImage.Kind.AUTHORS else "graphe-base"
    response["Content-Disposition"] = f'inline; filename="{name}-{day}.svg"'
    # Drawn by the server, but it holds names from the sources: no script, ever.
    response["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    return response


def graph_image_status(request, kind):
    """The state of the computation, which the graph page asks while it lasts."""
    state = graph_images.image_state(known_kind(kind))
    return JsonResponse({"pending": state["pending"]})
