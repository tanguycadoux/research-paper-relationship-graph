from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ..services import suggestions, tags
from .pagination import page_of


@login_required
def corpus_suggestions(request):
    tag_tree = tags.tag_tree(request.user)
    tag = request.GET.get("tag", "")
    if tag and tag not in {item["path"] for item in tag_tree}:
        messages.warning(request, f"Le tag « {tags.label(tag)} » n'existe plus : tout le corpus.")
        tag = ""
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
