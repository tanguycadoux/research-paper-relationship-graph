from django.contrib import messages

from ..services.corpus import tags


def requested_tag(request):
    """
    The tag of the user's corpus asked in ?tag= (subtags included), and the user's tag
    tree. A tag that no longer exists falls back to the whole corpus, with a message:
    the suggestions (#162) and the graph of a tag (#290) follow the same rule.
    """
    tag_tree = tags.tag_tree(request.user)
    tag = request.GET.get("tag", "")
    if tag and tag not in {item["path"] for item in tag_tree}:
        messages.warning(request, f"Le tag « {tags.label(tag)} » n'existe plus : tout le corpus.")
        tag = ""
    return tag, tag_tree
