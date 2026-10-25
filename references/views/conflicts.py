from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..models import MetadataConflict
from ..services import conflicts, published_versions
from ..services.importer import import_publication
from ..services.orcid_merge import merge_same_orcid

RECENT_DECISIONS = 20


@login_required
def conflicts_view(request):
    related = ("publication", "author", "resolved_by")
    open_conflicts = list(
        MetadataConflict.objects.filter(status=conflicts.Status.OPEN).select_related(*related)
    )
    for conflict in open_conflicts:
        if conflict.kind == conflicts.Kind.ORCID_NAME:
            conflict.names = conflicts.compare_names(conflict)
    context = {
        "open_conflicts": open_conflicts,
        "recent_decisions": MetadataConflict.objects.exclude(status=conflicts.Status.OPEN)
        .select_related(*related)
        .order_by("-resolved_at")[:RECENT_DECISIONS],
    }
    return render(request, "references/conflicts.html", context)


@login_required
@require_POST
def resolve_conflict_view(request, pk):
    conflict = get_object_or_404(MetadataConflict, pk=pk, status=conflicts.Status.OPEN)
    decision = request.POST.get("decision")
    if conflict.kind == conflicts.Kind.PUBLISHED_VERSION and decision == conflicts.Status.ACCEPTED:
        return accept_published_version(request, conflict)
    try:
        conflicts.resolve(conflict, request.POST.get("decision"), request.user)
    except ValueError:
        messages.error(request, "Cette décision n'est pas possible pour ce conflit.")
    else:
        messages.success(request, f"Conflit tranché : {conflict.get_status_display().lower()}.")
        if conflict.kind == conflicts.Kind.ORCID and conflict.status == conflicts.Status.ACCEPTED:
            # The accepted ORCID may already be held by another author (#158).
            merge_same_orcid(conflict.author, user=request.user, source=conflict.source)
    return redirect("conflict_list")


def accept_published_version(request, conflict):
    """The preprint becomes its published version (#227), imported with its references."""
    arxiv_doi = conflict.current_value
    pub = published_versions.accept_published_version(conflict, request.user)
    if pub is None:
        messages.error(request, "Crossref n'a pas répondu : rien n'a changé, réessayez plus tard.")
        return redirect("conflict_list")
    pub = import_publication(pub, with_references=pub.parse_references) or pub
    messages.success(
        request, f"La prépublication {arxiv_doi} est remplacée par sa version publiée, « {pub} »."
    )
    return redirect("conflict_list")
