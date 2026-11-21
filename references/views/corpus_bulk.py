"""
The bars of bulk actions (#287): one form, one view, one action per button. In « Mon
corpus », every publication checked must be in it; on a publication, its references
and « Cité par » (#408) mix publications in and out of the corpus: those out of it are
added by « Ajouter à mon corpus », and left aside by the other actions.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from ..models import Publication, UserPublication
from ..services.corpus import bulk, tags
from ..services.display.wording import count, suffix
from .redirects import redirect_to_next


@login_required
@require_POST
def bulk_action(request):
    """The bar of « Mon corpus »: all or nothing."""
    run_action(request, request.POST.getlist("publication"), partial=False)
    return redirect_to_next(request, "corpus")


@login_required
@require_POST
def publication_bulk_action(request, pk):
    """
    The bars of a publication's references and « Cité par » (#408), back to the list
    (the `next` field, else the publication). Only the publications these lists show
    can be checked: the others are dropped.
    """
    pub = get_object_or_404(Publication, pk=pk)
    checked = bulk.checked_ids(request.POST.getlist("publication")) & bulk.listed_on(pub)
    if request.POST.get("action") == "add":
        add_checked(request, checked)
    else:
        run_action(request, checked, partial=True)
    return redirect_to_next(request, "publication_detail", pk=pk)


def run_action(request, values, *, partial):
    action = ACTIONS.get(request.POST.get("action", ""))
    if action is None:
        messages.error(request, "Action inconnue.")
        return
    try:
        selection = bulk.checked_entries(request.user, values, partial=partial)
    except bulk.InvalidSelection as error:
        messages.error(request, str(error))
        return
    if action(request, selection.entries) and selection.left_aside:
        aside = count(
            selection.left_aside,
            "publication cochée n'est pas dans votre corpus : elle a été laissée",
            "publications cochées ne sont pas dans votre corpus : elles ont été laissées",
        )
        messages.info(request, f"{aside} de côté.")


def add_checked(request, checked):
    status = request.POST.get("status", "")
    if status and status not in UserPublication.ReadingStatus.values:
        messages.error(request, "Statut de lecture inconnu.")
        return
    try:
        publications = bulk.checked_publications(checked)
        result = bulk.add_publications(
            request.user, publications, status, request.POST.get("name", "")
        )
    except (bulk.InvalidSelection, tags.InvalidTag) as error:
        messages.error(request, str(error))
        return
    report = addition_report(result, status)
    if result.failed:
        failed = count(
            result.failed,
            "publication n'a pas pu être récupérée",
            "publications n'ont pas pu être récupérées",
        )
        messages.warning(
            request,
            f"{report} {failed} (identifiant inconnu des sources, ou service injoignable).",
        )
        return
    messages.success(request, report)


def addition_report(result, status):
    """
    One sentence (#411), the queue having its own toast: « 2 publications ajoutées, à
    lire, taguées « Essai ». », « 1 publication ajoutée ; 2 autres y étaient déjà ;
    3 publications taguées « Essai ». »
    """
    added = result.added
    clauses = [count(added, "publication ajoutée") if added else "Aucune publication ajoutée"]
    if added and status:
        clauses[0] += f", {status_words(status, added)}"
    if result.already:
        clauses.append(already_there(result.already, added))
    tagging = result.tagging
    if tagging and tagging.tagged == added and not result.already:
        clauses[0] += f", taguée{suffix(added)} « {tagging.label} »"
    elif tagging:
        clauses.append(f"{count(tagging.tagged, 'publication taguée')} « {tagging.label} »")
    if tagging and tagging.covered:
        covered = count(tagging.covered, "autre avait", "autres avaient")
        clauses.append(f"{covered} déjà un tag plus précis")
    return " ; ".join(clauses) + "."


def already_there(already, added):
    """« 2 autres y étaient déjà »; after « Aucune publication ajoutée », « elle y était déjà »."""
    if added:
        return f"{count(already, 'autre y était', 'autres y étaient')} déjà"
    return "elle y était déjà" if already == 1 else f"les {already} y étaient déjà"


def status_words(status, number):
    """« à lire », « en cours », « lue » or « lues »: the status, agreed with publications."""
    if status == UserPublication.ReadingStatus.READ:
        return f"lue{suffix(number)}"
    return UserPublication.ReadingStatus(status).label.lower()


def tagging_report(result):
    """« 5 publications taguées « Projet › Groupe ». 1 autre a déjà un tag plus précis… »"""
    report = f"{count(result.tagged, 'publication taguée')} « {result.label} »."
    if result.covered:
        already = count(result.covered, "autre a", "autres ont")
        report += f" {already} déjà un tag plus précis : rien n'y est ajouté."
    return report


def tag_checked(request, entries):
    try:
        result = bulk.tag_entries(entries, request.POST.get("name", ""))
    except tags.InvalidTag as error:
        messages.error(request, str(error))
        return False
    messages.success(request, tagging_report(result))
    return True


def set_status_of_checked(request, entries):
    status = request.POST.get("status", "")
    if status and status not in UserPublication.ReadingStatus.values:
        messages.error(request, "Statut de lecture inconnu.")
        return False
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
    else:
        messages.success(request, report)
    return True


def remove_checked(request, entries):
    result = bulk.remove_entries(request.user, entries)
    removed = count(result.removed, "publication retirée")
    messages.success(request, f"{removed} de votre corpus{losses(result)}.")
    return True


def losses(result):
    """What a bulk removal lost (#408): « , avec 2 tags, 1 statut de lecture et 1 note »."""
    lost = [
        count(number, singular, plural)
        for number, singular, plural in (
            (result.tags, "tag", "tags"),
            (result.statuses, "statut de lecture", "statuts de lecture"),
            (result.notes, "note", "notes"),
        )
        if number
    ]
    if not lost:
        return ""
    listed = ", ".join(lost[:-1]) + " et " if len(lost) > 1 else ""
    return f", avec {listed}{lost[-1]}"


ACTIONS = {"tag": tag_checked, "status": set_status_of_checked, "remove": remove_checked}
