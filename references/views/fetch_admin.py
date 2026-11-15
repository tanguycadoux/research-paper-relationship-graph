"""The administration of the queue of retrievals (#382), reserved to the staff."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..models import FetchRequest
from ..services.imports import fetch_admin


def staff_required(view):
    """A visitor is sent to the login page; a user who is not staff is refused (403)."""

    @login_required
    @wraps(view)
    def checked(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return checked


@staff_required
def fetch_queue_admin(request):
    context = {"queue": fetch_admin.overview(), "recent": fetch_admin.RECENT}
    return render(request, "references/fetch_queue_admin.html", context)


@staff_required
@require_POST
def fetch_request_retry(request, pk):
    fetch = get_object_or_404(FetchRequest, pk=pk)
    try:
        fetch_admin.retry(fetch)
    except fetch_admin.NotRetried as reason:
        messages.warning(request, str(reason))
    else:
        messages.success(request, f"Demande relancée : {fetch.identifier}, en fin de file.")
    return redirect("fetch_queue_admin")


@staff_required
@require_POST
def fetch_request_cancel(request, pk):
    fetch = get_object_or_404(FetchRequest, pk=pk)
    if fetch_admin.cancel(fetch, request.user):
        messages.success(
            request, f"Demande annulée : {fetch.identifier}. Elle reste parmi les échouées."
        )
    else:
        messages.warning(request, "Seule une demande en attente peut être annulée.")
    return redirect("fetch_queue_admin")
