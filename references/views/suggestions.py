from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ..services.corpus import tags
from ..services.discovery import importance, suggestions
from .pagination import page_of
from .tag_context import requested_tag


def minimum_links(request, current):
    """The links of « Citées par au moins 1 / 2 de ces articles »: tag and sort kept."""
    links = []
    for choice in suggestions.MIN_CITING_CHOICES:
        query = request.GET.copy()
        query.pop("page", None)
        query.pop("min", None)
        if choice != suggestions.MIN_CITING:
            query["min"] = choice
        url = f"?{query.urlencode()}" if query else request.path
        links.append({"value": choice, "url": url, "current": choice == current})
    return links


@login_required
def corpus_suggestions(request):
    tag, tag_tree = requested_tag(request)
    minimum = suggestions.min_citing(request.GET.get("min"))
    sort = suggestions.SUGGESTIONS.read(request.GET.get("sort"))
    rows, ranks = suggestions.sorted_suggestions(request.user, tag, minimum, sort)
    page = page_of(request, rows)
    publications = list(page.object_list)
    suggestions.describe(request.user, publications, tag, ranks)
    context = {
        "publications": publications,
        "page_obj": page,
        "tag_tree": tag_tree,
        "active_tag": tag,
        "active_tag_label": tags.label(tag),
        "min_citing": minimum,
        "minimum_links": minimum_links(request, minimum),
        "sorting": suggestions.SUGGESTIONS,
        "sort": sort,
        "importance_scope": importance.SCOPE,
        "context_count": suggestions.context_publications(request.user, tag).count(),
        "to_identify": suggestions.references_to_identify(request.user, tag),
    }
    return render(request, "references/suggestions.html", context)
