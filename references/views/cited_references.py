from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from ..forms import IdentifyReferenceForm
from ..models import CitedReference
from ..services import identification


@login_required
def identify_reference(request, pk, position):
    ref = get_object_or_404(CitedReference, source_id=pk, position=position)
    form = IdentifyReferenceForm(request.POST or None, initial=initial_values(ref))
    if request.method == "POST" and form.is_valid():
        apply_identification(request, ref, form.cleaned_data)
        return redirect("publication_detail", pk=pk)
    return render(request, "references/identify_reference.html", {"ref": ref, "form": form})


def initial_values(ref):
    return {
        "doi": ref.doi,
        "isbn": ref.raw.get("ISBN", ""),
        "title": identification.suggested_title(ref),
        "year": identification.suggested_year(ref),
    }


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
