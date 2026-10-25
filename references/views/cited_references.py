from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..forms import IdentifyReferenceForm
from ..models import CitedReference, Publication
from ..services import candidates, identification
from ..services.doi import is_valid_doi, normalize_doi
from ..services.doi_registration import is_unregistered_doi, unregistered_message
from ..services.external_records import Source
from ..services.metadata_formats import bibliography_source


@login_required
def identify_reference(request, pk, position):
    ref = get_object_or_404(CitedReference, source_id=pk, position=position)
    form = IdentifyReferenceForm(request.POST or None, initial=initial_values(ref))
    if request.method == "POST" and form.is_valid() and not refuse_unregistered_doi(form):
        apply_identification(request, ref, form.cleaned_data)
        return after_decision(request, ref)
    found, search_failed = candidates.candidates_for(ref)
    context = {
        "ref": ref,
        "form": form,
        "reference_title": reference_title(ref),
        "candidates": found,
        "search_failed": search_failed,
    }
    if in_series(request):
        context["series"] = series_progress(ref)
    return render(request, "references/identify_reference.html", context)


@login_required
@require_POST
def choose_candidate(request, pk, position):
    """« C'est celle-ci » on a candidate: a publication of the base, or a DOI to import."""
    ref = get_object_or_404(CitedReference, source_id=pk, position=position)
    if request.POST.get("publication"):
        pub = get_object_or_404(Publication, pk=request.POST["publication"])
        identification.resolve(ref, pub, request.user)
        imported = True
    else:
        doi = normalize_doi(request.POST.get("doi", ""))
        if not is_valid_doi(doi):
            messages.error(request, "Candidat invalide.")
            return redirect(identify_url(ref, in_series(request)))
        pub, imported = identification.identify_by_doi(ref, doi, request.user)
    report_identification(request, ref, pub, imported)
    return after_decision(request, ref)


@login_required
@require_POST
def search_candidates_again(request, pk, position):
    ref = get_object_or_404(CitedReference, source_id=pk, position=position)
    candidates.forget_candidates(ref)
    return redirect(identify_url(ref, in_series(request)))


@login_required
@require_POST
def toggle_unidentifiable(request, pk, position):
    """Declare the reference unidentifiable, or cancel that declaration."""
    ref = get_object_or_404(CitedReference, source_id=pk, position=position)
    if ref.unidentifiable:
        identification.cancel_unidentifiable(ref)
        messages.success(request, f"Référence n° {position + 1} de nouveau à identifier.")
    else:
        identification.declare_unidentifiable(ref, request.user)
        messages.success(request, f"Référence n° {position + 1} déclarée non identifiable.")
    return after_decision(request, ref)


@login_required
def skip_reference(request, pk, position):
    """« Passer » in a series: on to the next reference, this one stays to identify."""
    ref = get_object_or_404(CitedReference, source_id=pk, position=position)
    return next_in_series(request, ref)


# Series (#242): the references of a publication left to identify, one after the
# other, without going back to the publication. The URL carries ?serie=1, and the
# forms of the page a hidden field « serie ».

SERIES_PARAMETER = "serie"


def in_series(request):
    return "1" in (request.GET.get(SERIES_PARAMETER), request.POST.get(SERIES_PARAMETER))


def identify_url(ref, series=False):
    url = reverse("reference_identify", args=[ref.source_id, ref.position])
    return f"{url}?{SERIES_PARAMETER}=1" if series else url


def after_decision(request, ref):
    """Back to the publication, or on to the next reference to identify in a series."""
    if in_series(request):
        return next_in_series(request, ref)
    return redirect("publication_detail", pk=ref.source_id)


def next_in_series(request, ref):
    following = identification.next_to_identify(ref)
    if following is not None:
        return redirect(identify_url(following, series=True))
    left = identification.to_identify_in(ref.source).count()
    if left:
        messages.info(
            request,
            f"Fin de la série : {left} référence{pluralize(left)} "
            f"reste{pluralize(left, 'nt')} à identifier.",
        )
    else:
        messages.info(request, "Fin de la série : toutes les références sont traitées.")
    return redirect("publication_detail", pk=ref.source_id)


def series_progress(ref):
    """How many references are left to identify in the publication, and after ref."""
    left = identification.to_identify_in(ref.source)
    return {"left": left.count(), "after": left.filter(position__gt=ref.position).count()}


SOURCE_NAMES = {Source.ARXIV: "les sources LaTeX d'arXiv"}


def reference_title(ref):
    """« Telle que donnée par » the source of the bibliography of the citing publication."""
    source = bibliography_source(ref.source)
    if source is None:
        return "Telle que citée"
    return f"Telle que donnée par {SOURCE_NAMES.get(source, Source(source).label)}"


def initial_values(ref):
    return {
        "doi": ref.doi,
        "isbn": ref.raw.get("ISBN", ""),
        "title": candidates.cited_title(ref),
        "year": candidates.cited_year(ref),
    }


def refuse_unregistered_doi(form):
    """Put an error on the DOI field if doi.org does not know it (#240); return True then."""
    data = form.cleaned_data
    if data["method"] != IdentifyReferenceForm.METHOD_DOI:
        return False
    if not is_unregistered_doi(data["doi"]):
        return False
    message = unregistered_message(data["doi"])
    form.add_error("doi", message + " Sans DOI, identifiez-la « Sans identifiant ».")
    return True


def apply_identification(request, ref, data):
    method = data["method"]
    if method == IdentifyReferenceForm.METHOD_DOI:
        pub, imported = identification.identify_by_doi(ref, data["doi"], request.user)
    elif method == IdentifyReferenceForm.METHOD_ISBN:
        pub, imported = identification.identify_by_isbn(ref, data["isbn"], request.user)
    else:
        pub = identification.identify_without_identifier(
            ref, data["title"], data["year"], request.user
        )
        imported = True
    report_identification(request, ref, pub, imported)


def report_identification(request, ref, pub, imported):
    if imported:
        messages.success(request, f"Référence n° {ref.position + 1} identifiée : « {pub} ».")
    else:
        messages.warning(
            request,
            f"Référence n° {ref.position + 1} reliée à « {pub} », mais ses données n'ont pas "
            "pu être récupérées (identifiant inconnu ou service injoignable).",
        )
