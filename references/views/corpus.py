from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from ..forms import NoteForm
from ..models import Publication, Tag, UserPublication
from ..services.corpus import import_reports, tags
from ..services.corpus.entries import (
    add_identified,
    change_reading_status,
    find_or_create,
    queue_identified,
    queue_reading_status,
)
from ..services.display import filters, wording
from ..services.display.publication_table import for_publication_table
from ..services.display.sorting import CORPUS
from ..services.identifiers.arxiv import typed_doi
from ..services.imports import fetch_queue
from ..services.sources.doi_registration import is_unregistered_doi, unregistered_message
from .pagination import page_of
from .redirects import redirect_to_next


def requested_status(request):
    """The reading status of the button that added a publication: « à lire », or none."""
    status = request.POST.get("status", "")
    return status if status in UserPublication.ReadingStatus.values else ""


def add_and_report(request, pub, status=""):
    """
    Add pub to the corpus and say how it went. Return the publication added: the
    published version of a preprint, maybe (#227). With a worker, the retrieval is left
    to the queue (#378).
    """
    if fetch_queue.worker_alive():
        report_queued(request, pub, queue_identified(request.user, pub, status), status)
        return pub
    asked_doi = pub.doi
    imported = add_identified(request.user, pub, status)
    report_addition(request, imported or pub, imported, status)
    if imported and asked_doi and imported.preprint_doi == asked_doi:
        messages.info(
            request,
            f"La prépublication arXiv {asked_doi} a été remplacée par sa version publiée, "
            f"DOI {imported.doi}.",
        )
    return imported or pub


def report_queued(request, pub, fetch_request, status=""):
    added = f"« {pub} » a été ajouté à votre corpus"
    if status == UserPublication.ReadingStatus.TO_READ:
        added += ", à lire"
    if fetch_request is None:
        messages.success(request, f"{added}.")
    else:
        messages.success(request, f"{added} ; ses données sont en file de récupération.")


def report_addition(request, pub, imported, status=""):
    if imported and status == UserPublication.ReadingStatus.TO_READ:
        messages.success(
            request,
            f"« {pub} » a été ajouté à votre corpus, à lire : sa bibliographie sera importée "
            "quand vous changerez son statut.",
        )
    elif imported:
        messages.success(request, f"« {pub} » a été ajouté à votre corpus.")
    elif pub.doi:
        messages.warning(
            request,
            f"« {pub} » a été ajouté à votre corpus, mais ses données n'ont pas pu être "
            "récupérées (DOI inconnu de Crossref et de DataCite, ou service injoignable).",
        )
    else:
        messages.warning(
            request,
            f"« {pub} » a été ajouté à votre corpus, mais ses données n'ont pas pu être "
            "récupérées (ISBN inconnu de Crossref et d'Open Library, ou service injoignable).",
        )


@login_required
@require_POST
def add_to_user_refs(request, pk):
    pub = get_object_or_404(Publication, pk=pk)
    pub = add_and_report(request, pub, requested_status(request))
    return redirect_to_next(request, "publication_detail", pk=pub.pk)


@login_required
@require_POST
def add_publication_to_user_refs_by_identifier(request):
    """From the corpus page, or from a work citing a publication (#163), with next."""
    identifier = request.POST.get("identifier", "")
    doi = typed_doi(identifier)  # a DOI, or an arXiv identifier or link (#267)
    if doi and is_unregistered_doi(doi):
        messages.error(request, f"{unregistered_message(doi)} Rien n'a été ajouté.")
        return redirect_to_next(request, "corpus")
    pub = find_or_create(doi=doi, isbn=identifier, queued=fetch_queue.worker_alive())
    if pub is None:
        messages.error(
            request,
            "Veuillez entrer un DOI (de la forme 10.xxxx/…), un identifiant ou un lien "
            "arXiv (1706.03762, arxiv.org/abs/…) ou un ISBN valide (10 ou 13 chiffres, "
            "avec ou sans tirets).",
        )
        return redirect_to_next(request, "corpus")

    add_and_report(request, pub, requested_status(request))
    return redirect_to_next(request, "corpus")


@login_required
@require_POST
def remove_from_user_refs(request, pk):
    pub = get_object_or_404(Publication, pk=pk)
    entry = UserPublication.objects.filter(user=request.user, publication=pub).first()
    lost = removal_losses(entry) if entry else ""
    UserPublication.objects.filter(user=request.user, publication=pub).delete()
    tags.forget_unused_tags(request.user)
    messages.success(request, f"« {pub} » a été retiré de votre corpus{lost}.")
    return redirect_to_next(request, "publication_detail", pk=pk)


def removal_losses(entry):
    """What the removal of an entry loses, for its message (#280): « , avec … »."""
    lost = []
    labels = [f"« {tag.label} »" for tag in entry.tags.all()]
    if labels:
        lost.append(f"{'ses tags' if len(labels) > 1 else 'son tag'} {', '.join(labels)}")
    if entry.reading_status:
        lost.append(f"son statut « {entry.get_reading_status_display()} »")
    if entry.note:
        lost.append("sa note")
    if not lost:
        return ""
    listed = ", ".join(lost[:-1]) + " et " if len(lost) > 1 else ""
    return f", avec {listed}{lost[-1]}"


@login_required
@require_POST
def set_reading_status(request, pk):
    entry = get_object_or_404(UserPublication, user=request.user, publication_id=pk)
    status = request.POST.get("status", "")
    if status and status not in UserPublication.ReadingStatus.values:
        messages.error(request, "Statut de lecture inconnu.")
        return redirect_to_next(request, "publication_detail", pk=pk)
    if fetch_queue.worker_alive():
        queued = queue_reading_status(entry, status)
        report = reading_status_report(entry, status)
        if queued:
            report += " Sa bibliographie est en file de récupération."
        messages.success(request, report)
        return redirect_to_next(request, "publication_detail", pk=pk)
    imported = change_reading_status(entry, status)
    report = reading_status_report(entry, status)
    if imported is None:
        messages.warning(
            request, f"{report} Sa bibliographie n'a pas pu être récupérée (service injoignable ?)."
        )
    elif imported:
        count = imported.cited_references.count()
        messages.success(
            request,
            f"{report} Sa bibliographie a été importée : {wording.count(count, 'référence')}.",
        )
    else:
        messages.success(request, report)
    return redirect_to_next(request, "publication_detail", pk=imported.pk if imported else pk)


@login_required
@require_POST
def set_note(request, pk):
    """Save the note of an entry of my corpus (#283); an empty note erases it."""
    entry = get_object_or_404(UserPublication, user=request.user, publication_id=pk)
    form = NoteForm(request.POST, instance=entry)
    if not form.is_valid():
        messages.error(request, " ".join(form.errors.get("note", [])))
    else:
        form.save()
        messages.success(request, "Note enregistrée." if entry.note else "Note effacée.")
    return redirect(reverse("publication_detail", args=[pk]) + "#note")


def reading_status_report(entry, status):
    label = entry.get_reading_status_display().lower() if status else "aucun"
    return f"Statut de lecture de « {entry.publication} » : {label}."


@login_required
def my_references(request):
    pubs = Publication.objects.filter(userpublication__user=request.user)
    sort = CORPUS.read(request.GET.get("sort"))
    selection = filters.filtered_corpus(request.user, request.GET)
    active_filters = selection.active
    shown = for_publication_table(selection.publications)
    page = page_of(request, CORPUS.apply(shown, sort))
    publications = list(page.object_list)
    tags_by_publication = tags.tags_by_publication(request.user, publications)
    for pub in publications:
        pub.my_tags = tags_by_publication[pub.pk]
    context = {
        "publications": publications,
        "page_obj": page,
        "sorting": CORPUS,
        "sort": sort,
        "filters": selection.filters,
        "active_filters": active_filters,
        "tag_tree": tags.tag_tree(request.user),
        "active_tag": active_filters.values.get("tag"),
        "reading_statuses": UserPublication.ReadingStatus.choices,
        "tag_max_length": tags.MAX_LENGTH,
        "bulk_tags": tags.suggested_paths(request.user),
        "corpus_count": pubs.count(),
        "latest_first": latest_first(request, sort),
        "import_report": import_reports.last(request.session),
        "exports": export_buttons(selection, page.paginator.count),
        "note_filter": note_filter(request, active_filters.values.get("note")),
    }
    return render(request, "references/user_references.html", context)


NOTE_PARAMS = ("note", "has_note", "page")


def note_filter(request, value):
    """
    The field that searches my notes (#443): its text, the other parameters it keeps,
    and the links « avec une note » / « sans note », each with whether it is on.
    """
    kept = [
        (name, item)
        for name, items in request.GET.lists()
        if name not in NOTE_PARAMS
        for item in items
    ]
    return {
        "text": value if isinstance(value, str) else "",
        "kept": kept,
        "choices": [
            (label, f"?{urlencode([*kept, ('has_note', flag)])}", value is on)
            for label, flag, on in (("Avec une note", "1", True), ("Sans note", "0", False))
        ],
    }


def export_buttons(selection, shown):
    """
    The export buttons of « Mon corpus » (#285): the whole corpus without a filter, else
    the publications shown, on every page, which their label says.
    """
    filtered = bool(selection.active)
    scope = export_scope(shown) if filtered else ""
    query = f"?{selection.query}" if filtered else ""
    return {
        "filtered": filtered,
        "empty": filtered and not shown,
        "json_label": f"JSON{scope}" if filtered else "JSON (réimportable)",
        "bibtex_label": f"BibTeX{scope}",
        "json_url": reverse("corpus_export_json") + query,
        "bibtex_url": reverse("corpus_export_bibtex") + query,
        "not_exportable": selection.publications.filter(doi="", isbn="").count(),
    }


def export_scope(shown):
    """« des 12 publications affichées », after JSON or BibTeX."""
    if not shown:
        return " : aucune publication affichée"
    if shown == 1:
        return " de la publication affichée"
    return f" des {shown} publications affichées"


def latest_first(request, sort):
    """
    The sort by date of addition, which has no column (#281): whether it is on, and the
    URL that turns it on (or back to the default sort), with the other parameters.
    """
    query = request.GET.copy()
    query.pop("page", None)
    on = sort.column == "added"
    if on:
        query.pop("sort", None)
    else:
        query["sort"] = "-added"
    return {"on": on, "url": f"?{query.urlencode()}"}


@login_required
@require_POST
def tag_publication(request, pk):
    entry = get_object_or_404(UserPublication, user=request.user, publication_id=pk)
    try:
        tagging = tags.tag_entry(entry, request.POST.get("name", ""))
    except tags.InvalidTag as error:
        messages.error(request, str(error))
    else:
        report_tagging(request, entry, tagging)
    return redirect_to_next(request, "publication_detail", pk=pk)


def report_tagging(request, entry, tagging):
    if tagging.covered_by:
        messages.info(
            request,
            f"« {entry.publication} » a déjà le tag « {tagging.covered_by.label} », plus précis : "
            "rien n'est ajouté.",
        )
    elif tagging.tag is None:
        messages.error(request, "Écrivez le nom du tag, par exemple « Projet/Groupe/… ».")
    else:
        report = f"Tag « {tagging.tag.label} » ajouté à « {entry.publication} »."
        if tagging.replaced:
            replaced = ", ".join(f"« {tag.label} »" for tag in tagging.replaced)
            report += f" Il remplace {replaced}, moins précis."
        messages.success(request, report)


@login_required
@require_POST
def untag_publication(request, pk, tag_pk):
    entry = get_object_or_404(UserPublication, user=request.user, publication_id=pk)
    tag = get_object_or_404(Tag, pk=tag_pk, user=request.user)
    tags.untag_entry(entry, tag)
    messages.success(request, f"Tag « {tag.label} » retiré de « {entry.publication} ».")
    return redirect_to_next(request, "publication_detail", pk=pk)


@login_required
def manage_tags(request):
    return render(request, "references/tags.html", {"tag_tree": tags.tag_tree(request.user)})


@login_required
@require_POST
def rename_tag(request):
    path = request.POST.get("path", "")
    try:
        count = tags.rename_path(request.user, path, request.POST.get("name", ""))
    except tags.InvalidTag as error:
        messages.error(request, str(error))
    else:
        concerned = wording.count(count, "publication concernée")
        messages.success(request, f"Tag « {tags.label(path)} » renommé : {concerned}.")
    return redirect("tag_list")


@login_required
@require_POST
def delete_tag(request):
    path = request.POST.get("path", "")
    try:
        count = tags.delete_path(request.user, path)
    except tags.InvalidTag as error:
        messages.error(request, str(error))
    else:
        publications = wording.count(count, "publication")
        messages.success(
            request,
            f"Tag « {tags.label(path)} » supprimé : retiré de {publications}, "
            "qui restent dans votre corpus.",
        )
    return redirect("tag_list")
