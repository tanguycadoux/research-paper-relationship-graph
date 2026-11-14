from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ..services.corpus import tags
from ..services.discovery import suggestions
from .pagination import page_of
from .tag_context import requested_tag


@login_required
def corpus_suggestions(request):
    tag, tag_tree = requested_tag(request)
    page = page_of(request, suggestions.co_cited(request.user, tag))
    publications = list(page.object_list)
    suggestions.describe(request.user, publications, tag)
    context = {
        "publications": publications,
        "page_obj": page,
        "tag_tree": tag_tree,
        "active_tag": tag,
        "active_tag_label": tags.label(tag),
        "min_citing": suggestions.MIN_CITING,
        "context_count": suggestions.context_publications(request.user, tag).count(),
        "to_identify": suggestions.references_to_identify(request.user, tag),
    }
    return render(request, "references/suggestions.html", context)
