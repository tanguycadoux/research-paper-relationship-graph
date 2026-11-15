from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from ..services.corrections import typed_authors


@login_required
def author_suggestions(request):
    """
    Authors of the base for the text typed in the list of authors of « Sans identifiant »
    (#259): by name or ORCID, a few at most, without any call to an outside source.
    """
    return JsonResponse({"results": typed_authors.suggestions(request.GET.get("q", ""))})
