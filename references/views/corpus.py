from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..models import Publication, Tag, UserPublication
from ..services import filters, tags
from ..services.corpus import (
    add_identified,
    change_reading_status,
    find_or_create,
    with_reading_status,
)
from ..services.publication_table import for_publication_table
from ..services.sorting import CORPUS
from .pagination import page_of


def requested_status(request):
    """The reading status of the button that added a publication: « à lire », or none."""
    status = request.POST.get("status", "")
    return status if status in UserPublication.ReadingStatus.values else ""


def add_and_report(request, pub, status=""):
    """
    Add pub to the corpus and say how it went. Return the publication added: the
    published version of a preprint, maybe (#227).
    """
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


def redirect_back(request, pk):
    """Go back to the page holding the button (the `next` field), or to the publication."""
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("publication_detail", pk=pk)


@login_required
@require_POST
def add_to_user_refs(request, pk):
    pub = get_object_or_404(Publication, pk=pk)
    pub = add_and_report(request, pub, requested_status(request))
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

    add_and_report(request, pub, requested_status(request))
    return redirect("corpus")


@login_required
@require_POST
def remove_from_user_refs(request, pk):
    pub = get_object_or_404(Publication, pk=pk)
    UserPublication.objects.filter(user=request.user, publication=pub).delete()
    tags.forget_unused_tags(request.user)
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
    imported = change_reading_status(entry, status)
    label = entry.get_reading_status_display().lower() if status else "aucun"
    report = f"Statut de lecture de « {entry.publication} » : {label}."
    if imported is None:
        messages.warning(
            request, f"{report} Sa bibliographie n'a pas pu être récupérée (service injoignable ?)."
        )
    elif imported:
        count = imported.cited_references.count()
        messages.success(
            request, f"{report} Sa bibliographie a été importée : {count} référence(s)."
        )
    else:
        messages.success(request, report)
    return redirect_back(request, imported.pk if imported else pk)


@login_required
def my_references(request):
    pubs = Publication.objects.filter(userpublication__user=request.user)
    sort = CORPUS.read(request.GET.get("sort"))
    corpus_filters = filters.corpus_filters(request.user)
    active_filters = corpus_filters.read(request.GET)
    listed = with_reading_status(pubs, request.user)
    shown = for_publication_table(corpus_filters.apply(listed, active_filters))
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
        "filters": corpus_filters,
        "active_filters": active_filters,
        "tag_tree": tags.tag_tree(request.user),
        "active_tag": active_filters.values.get("tag"),
        "reading_statuses": UserPublication.ReadingStatus.choices,
        "corpus_count": pubs.count(),
        "not_exportable": pubs.filter(doi="", isbn="").count(),
    }
    return render(request, "references/user_references.html", context)


@login_required
@require_POST
def tag_publication(request, pk):
    entry = get_object_or_404(UserPublication, user=request.user, publication_id=pk)
    try:
        tag = tags.tag_entry(entry, request.POST.get("name", ""))
    except tags.InvalidTag as error:
        messages.error(request, str(error))
    else:
        if tag is None:
            messages.error(request, "Écrivez le nom du tag, par exemple « Projet/Groupe/… ».")
        else:
            messages.success(request, f"Tag « {tag.label} » ajouté à « {entry.publication} ».")
    return redirect_back(request, pk)


@login_required
@require_POST
def untag_publication(request, pk, tag_pk):
    entry = get_object_or_404(UserPublication, user=request.user, publication_id=pk)
    tag = get_object_or_404(Tag, pk=tag_pk, user=request.user)
    tags.untag_entry(entry, tag)
    messages.success(request, f"Tag « {tag.label} » retiré de « {entry.publication} ».")
    return redirect_back(request, pk)
