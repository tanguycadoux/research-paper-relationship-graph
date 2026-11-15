"""The bar of bulk actions of « Mon corpus » (#287): one form, one view, one action per button."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from ..models import UserPublication
from ..services.corpus import bulk, tags
from ..services.display.wording import count
from .corpus import back_or_corpus


@login_required
@require_POST
def bulk_action(request):
    action = ACTIONS.get(request.POST.get("action", ""))
    if action is None:
        messages.error(request, "Action inconnue.")
        return back_or_corpus(request)
    try:
        entries = bulk.checked_entries(request.user, request.POST.getlist("publication"))
    except bulk.InvalidSelection as error:
        messages.error(request, str(error))
        return back_or_corpus(request)
    action(request, entries)
    return back_or_corpus(request)


def tag_checked(request, entries):
    try:
        result = bulk.tag_entries(entries, request.POST.get("name", ""))
    except tags.InvalidTag as error:
        messages.error(request, str(error))
        return
    report = f"{count(result.tagged, 'publication taguée')} « {result.label} »."
    if result.covered:
        already = count(result.covered, "autre a", "autres ont")
        report += f" {already} déjà un tag plus précis : rien n'y est ajouté."
    messages.success(request, report)


def set_status_of_checked(request, entries):
    status = request.POST.get("status", "")
    if status and status not in UserPublication.ReadingStatus.values:
        messages.error(request, "Statut de lecture inconnu.")
        return
    result = bulk.set_status(entries, status)
    label = UserPublication.ReadingStatus(status).label.lower() if status else "aucun"
    report = f"Statut de lecture de {count(result.changed, 'publication')} : {label}."
    if result.queued:
        report += f" Bibliographies en file de récupération : {result.queued}."
    if result.imported:
        report += f" Bibliographies importées : {result.imported}."
    if result.failed:
        failed = count(
            result.failed,
            "bibliographie n'a pas pu être récupérée",
            "bibliographies n'ont pas pu être récupérées",
        )
        messages.warning(request, f"{report} {failed} (service injoignable ?).")
        return
    messages.success(request, report)


def remove_checked(request, entries):
    removed = bulk.remove_entries(request.user, entries)
    messages.success(request, f"{count(removed, 'publication retirée')} de votre corpus.")


ACTIONS = {"tag": tag_checked, "status": set_status_of_checked, "remove": remove_checked}
