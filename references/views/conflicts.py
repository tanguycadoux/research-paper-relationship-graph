from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..models import MetadataConflict
from ..services import conflicts
from ..services.orcid_merge import merge_same_orcid

RECENT_DECISIONS = 20


@login_required
def conflicts_view(request):
    related = ("publication", "author", "resolved_by")
    context = {
        "open_conflicts": MetadataConflict.objects.filter(
            status=conflicts.Status.OPEN
        ).select_related(*related),
        "recent_decisions": MetadataConflict.objects.exclude(status=conflicts.Status.OPEN)
        .select_related(*related)
        .order_by("-resolved_at")[:RECENT_DECISIONS],
    }
    return render(request, "references/conflicts.html", context)


@login_required
@require_POST
def resolve_conflict_view(request, pk):
    conflict = get_object_or_404(MetadataConflict, pk=pk, status=conflicts.Status.OPEN)
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
