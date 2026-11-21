"""
« Récupérer les bibliographies… » (#431): from a publication, the corpus or a tag, the
page of confirmation with the estimate of each depth, the request, its progress and
« Arrêter »; the page of the requests of the user.
"""

from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..models import BibliographyRequest, Publication
from ..services.corpus import tags
from ..services.imports import bibliography_levels, bibliography_requests, fetch_queue
from ..services.imports.bibliography_requests import Scope, Start


def requested_start(request):
    """The Start of ?publication= or ?tag= (in the query or the form); the corpus by default."""
    params = request.POST if request.method == "POST" else request.GET
    pk = params.get("publication", "")
    if pk.isdigit():
        return Start(Scope.PUBLICATION, publication=get_object_or_404(Publication, pk=int(pk)))
    tag = params.get("tag", "")
    if tag and tag in tags.known_paths(request.user):
        return Start(Scope.TAG, tag=tag)
    return Start(Scope.CORPUS)


def start_url(start):
    """The page of confirmation of start."""
    url = reverse("bibliography_request")
    if start.scope == Scope.PUBLICATION:
        return f"{url}?publication={start.publication.pk}"
    if start.scope == Scope.TAG:
        return f"{url}?{urlencode({'tag': start.tag})}"
    return url


def back_url(start):
    """The page the action was asked from."""
    if start.scope == Scope.PUBLICATION:
        return reverse("publication_detail", args=[start.publication.pk])
    url = reverse("corpus")
    return f"{url}?{urlencode({'tag': start.tag})}" if start.scope == Scope.TAG else url


def requested_depth(params):
    depth = params.get("depth", "")
    return int(depth) if depth.isdigit() and int(depth) in bibliography_levels.DEPTHS else None


@login_required
def bibliography_request(request):
    """The estimate and the choice of the depth; the POST asks for the bibliographies."""
    start = requested_start(request)
    if request.method == "POST":
        return ask(request, start)
    running = bibliography_requests.running(request.user, start)
    context = {
        "start": start,
        "start_label": start.label(),
        "back_url": back_url(start),
        "running": running and bibliography_requests.describe(running),
        "estimate": bibliography_levels.estimate(start.publication_pks(request.user)),
        "depth": requested_depth(request.GET) or bibliography_levels.DEPTHS[0],
        "worker_alive": fetch_queue.worker_alive(),
    }
    return render(request, "references/bibliography_request.html", context)


def ask(request, start):
    depth = requested_depth(request.POST)
    if depth is None:
        messages.error(request, "Choisissez le niveau 2 ou le niveau 3.")
        return redirect(start_url(start))
    asked = bibliography_requests.ask(request.user, start, depth)
    messages.success(request, bibliography_requests.asked_text(asked))
    return redirect(start_url(start))


@login_required
@require_POST
def stop_bibliography_request(request, pk):
    """« Arrêter »: the imports still waiting leave the queue."""
    asked = get_object_or_404(BibliographyRequest, pk=pk, user=request.user)
    if bibliography_requests.stop(asked, request.user):
        messages.success(request, bibliography_requests.progress_text(asked))
    else:
        messages.info(request, "Cette demande était déjà terminée.")
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        target = reverse("bibliography_request_list")
    return redirect(target)


@login_required
def bibliography_request_list(request):
    """The requests of the user, the running ones first, with « Arrêter »."""
    asked = BibliographyRequest.objects.filter(user=request.user).order_by("-requested_at")
    rows = [bibliography_requests.describe(item) for item in asked[:50]]
    return render(request, "references/bibliography_requests.html", {"rows": rows})
