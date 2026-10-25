from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..models import Publication, UserPublication
from ..services import filters
from ..services.corpus import add_identified, find_or_create, with_reading_status
from ..services.publication_table import for_publication_table
from ..services.sorting import CORPUS
from .pagination import page_of


def add_and_report(request, pub):
    """
    Add pub to the corpus and say how it went. Return the publication added: the
    published version of a preprint, maybe (#227).
    """
    asked_doi = pub.doi
    imported = add_identified(request.user, pub)
    report_addition(request, imported or pub, imported)
    if imported and asked_doi and imported.preprint_doi == asked_doi:
        messages.info(
            request,
            f"La prépublication arXiv {asked_doi} a été remplacée par sa version publiée, "
            f"DOI {imported.doi}.",
        )
    return imported or pub


def report_addition(request, pub, imported):
    if imported:
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


def redirect_back(request, pk):
    """Go back to the page holding the button (the `next` field), or to the publication."""
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("publication_detail", pk=pk)


@login_required
@require_POST
def add_to_user_refs(request, pk):
    pub = add_and_report(request, get_object_or_404(Publication, pk=pk))
    return redirect_back(request, pub.pk)


@login_required
@require_POST
def add_publication_to_user_refs_by_identifier(request):
    identifier = request.POST.get("identifier", "")
    pub = find_or_create(doi=identifier, isbn=identifier)
    if pub is None:
        messages.error(
            request,
            "Veuillez entrer un DOI (de la forme 10.xxxx/…) ou un ISBN valide "
            "(10 ou 13 chiffres, avec ou sans tirets).",
        )
        return redirect("corpus")

    add_and_report(request, pub)
    return redirect("corpus")


@login_required
@require_POST
def remove_from_user_refs(request, pk):
    pub = get_object_or_404(Publication, pk=pk)
    UserPublication.objects.filter(user=request.user, publication=pub).delete()
    messages.success(request, f"« {pub} » a été retiré de votre corpus.")
    return redirect_back(request, pk)


@login_required
@require_POST
def set_reading_status(request, pk):
    entry = get_object_or_404(UserPublication, user=request.user, publication_id=pk)
    status = request.POST.get("status", "")
    if status and status not in UserPublication.ReadingStatus.values:
        messages.error(request, "Statut de lecture inconnu.")
        return redirect_back(request, pk)
    entry.reading_status = status
    entry.save(update_fields=["reading_status"])
    label = entry.get_reading_status_display().lower() if status else "aucun"
    messages.success(request, f"Statut de lecture de « {entry.publication} » : {label}.")
    return redirect_back(request, pk)


@login_required
def my_references(request):
    pubs = Publication.objects.filter(userpublication__user=request.user)
    sort = CORPUS.read(request.GET.get("sort"))
    active_filters = filters.CORPUS.read(request.GET)
    listed = with_reading_status(pubs, request.user)
    shown = for_publication_table(filters.CORPUS.apply(listed, active_filters))
    page = page_of(request, CORPUS.apply(shown, sort))
    context = {
        "publications": page.object_list,
        "page_obj": page,
        "sorting": CORPUS,
        "sort": sort,
        "filters": filters.CORPUS,
        "active_filters": active_filters,
        "reading_statuses": UserPublication.ReadingStatus.choices,
        "corpus_count": pubs.count(),
        "not_exportable": pubs.filter(doi="", isbn="").count(),
    }
    return render(request, "references/user_references.html", context)
