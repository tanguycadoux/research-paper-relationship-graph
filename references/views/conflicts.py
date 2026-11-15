from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..models import FetchRequest, MetadataConflict
from ..services.corrections import conflicts
from ..services.imports import fetch_queue, published_versions
from ..services.imports.importer import import_publication
from ..services.imports.orcid_merge import merge_same_orcid
from .pagination import page_of

RECENT_DECISIONS = 20


# Each type of conflict once, with its explanation (#335): it was repeated under
# every conflict of its type.
GROUP_SIZE = 25


@login_required
def conflicts_view(request):
    """
    The open conflicts, one section per type, 25 at most in each; ?type= shows one
    type alone, in pages of 25.
    """
    related = ("publication", "author", "resolved_by")
    open_conflicts = MetadataConflict.objects.filter(status=conflicts.Status.OPEN)
    counts = dict(open_conflicts.values_list("kind").annotate(Count("pk")).order_by())
    kind = request.GET.get("type")
    alone = kind if kind in counts else None
    groups = []
    for value, label in conflicts.Kind.choices:
        if value not in counts or (alone and value != alone):
            continue
        listed = (
            open_conflicts.filter(kind=value).select_related(*related).order_by("detected_at", "pk")
        )
        page = page_of(request, listed, GROUP_SIZE) if alone else None
        items = list(page.object_list if page else listed[:GROUP_SIZE])
        for conflict in items:
            if conflict.kind == conflicts.Kind.ORCID_NAME:
                conflict.names = conflicts.compare_names(conflict)
        groups.append(
            {
                "kind": value,
                "label": label,
                "count": counts[value],
                "conflicts": items,
                "page": page,
            }
        )
    context = {
        "groups": groups,
        "open_count": sum(counts.values()),
        "alone": alone,
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
    if fetch_queue.worker_alive():
        fetch_queue.enqueue_action(
            FetchRequest.Action.PUBLISHED_VERSION,
            request.user,
            publication=conflict.publication,
            identifier=conflict.proposed_value,
        )
        messages.success(
            request,
            f"Remplacement de la prépublication {arxiv_doi} par sa version publiée en file "
            "de récupération.",
        )
        return redirect("conflict_list")
    pub = published_versions.accept_published_version(conflict, request.user)
    if pub is None:
        messages.error(request, "Crossref n'a pas répondu : rien n'a changé, réessayez plus tard.")
        return redirect("conflict_list")
    pub = import_publication(pub, with_references=pub.parse_references) or pub
    messages.success(
        request, f"La prépublication {arxiv_doi} est remplacée par sa version publiée, « {pub} »."
    )
    return redirect("conflict_list")
