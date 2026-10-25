from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from ..models import Publication, UserPublication
from ..services.corpus import add_to_corpus
from ..services.doi import is_valid_doi, normalize_doi
from ..services.publication_table import for_publication_table
from ..services.search import filter_publications
from ..services.sorting import PUBLICATIONS
from .pagination import page_of
from .search import list_filter


def report_addition(request, pub, imported):
    if imported:
        messages.success(request, f"« {pub} » a été ajouté à votre corpus.")
    else:
        messages.warning(
            request,
            f"« {pub} » a été ajouté à votre corpus, mais ses données n'ont pas pu être "
            "récupérées (DOI inconnu de Crossref et de DataCite, ou service injoignable).",
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
    report_addition(request, pub, add_to_corpus(request.user, pub))
    return redirect_back(request, pk)


@login_required
@require_POST
def add_publication_to_user_refs_by_doi(request):
    normalized_doi = normalize_doi(request.POST.get("doi", ""))

    if not is_valid_doi(normalized_doi):
        messages.error(request, "Veuillez entrer un DOI valide (de la forme 10.xxxx/…).")
        return redirect("corpus")

    pub, _ = Publication.objects.get_or_create(doi=normalized_doi)
    report_addition(request, pub, add_to_corpus(request.user, pub))
    return redirect("corpus")


@login_required
@require_POST
def remove_from_user_refs(request, pk):
    pub = get_object_or_404(Publication, pk=pk)
    UserPublication.objects.filter(user=request.user, publication=pub).delete()
    messages.success(request, f"« {pub} » a été retiré de votre corpus.")
    return redirect_back(request, pk)


@login_required
def my_references(request):
    pubs = Publication.objects.filter(userpublication__user=request.user)
    sort = PUBLICATIONS.read(request.GET.get("sort"))
    current_filter = list_filter(request, sort, PUBLICATIONS)
    shown = for_publication_table(filter_publications(pubs, current_filter["query"]))
    page = page_of(request, PUBLICATIONS.apply(shown, sort))
    context = {
        "publications": page.object_list,
        "page_obj": page,
        "sorting": PUBLICATIONS,
        "sort": sort,
        "filter": current_filter,
        "corpus_count": pubs.count(),
        "not_exportable": pubs.filter(doi="", isbn="").count(),
    }
    return render(request, "references/user_references.html", context)
