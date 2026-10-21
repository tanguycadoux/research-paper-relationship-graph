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
        "title": identification.suggested_title(ref),
        "year": identification.suggested_year(ref),
    }


def apply_identification(request, ref, data):
    if data["method"] == IdentifyReferenceForm.METHOD_DOI:
        pub, imported = identification.identify_by_doi(ref, data["doi"], request.user)
        if not imported:
            messages.warning(
                request,
                f"Référence reliée au DOI {pub.doi}, mais ses données n'ont pas pu être "
                "récupérées sur Crossref.",
            )
            return
    else:
        pub = identification.identify_without_identifier(
            ref, data["title"], data["year"], request.user
        )
    messages.success(request, f"Référence n° {ref.position + 1} identifiée : « {pub} ».")
