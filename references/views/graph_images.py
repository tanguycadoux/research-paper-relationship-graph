"""The full images of the graphs too large for the page (#328)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect
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


def graph_image_svg(request, kind):
    """The image, for everyone like the graph pages; opened in the browser."""
    image = GraphImage.objects.filter(kind=known_kind(kind), status=GraphImage.Status.DONE).first()
    if image is None:
        raise Http404("Pas encore d'image de ce graphe.")
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
