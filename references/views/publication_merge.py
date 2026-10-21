from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from ..forms import MergePublicationForm
from ..models import Publication
from ..services import publication_merge


@login_required
def merge_publication(request, pk):
    duplicate = get_object_or_404(Publication, pk=pk)
    if not publication_merge.can_be_merged(duplicate):
        messages.error(request, "Seule une publication sans DOI ni ISBN peut être fusionnée.")
        return redirect("publication_detail", pk=pk)

    form = MergePublicationForm(request.POST or None)
    target = find_valid_target(form, duplicate) if request.method == "POST" else None
    if target and form.cleaned_data["confirm"]:
        publication_merge.merge_publication(duplicate, target, request.user)
        messages.success(request, f"« {duplicate} » a été fusionnée dans « {target} ».")
        return redirect("publication_detail", pk=target.pk)

    context = {
        "duplicate": duplicate,
        "form": form,
        "target": target,
        "summary": publication_merge.merge_summary(duplicate),
    }
    return render(request, "references/publication_merge.html", context)


def find_valid_target(form, duplicate):
    """Return the merge target designated in the form, or None with a form error."""
    if not form.is_valid():
        return None
    target = publication_merge.find_merge_target(form.cleaned_data["target"])
    if target is None:
        form.add_error("target", "Aucune publication trouvée pour ce DOI, cet ISBN ou ce lien.")
    elif target == duplicate:
        form.add_error("target", "Une publication ne peut pas être fusionnée avec elle-même.")
    else:
        return target
    return None
