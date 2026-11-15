from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from ..forms import TitleSearchForm
from ..services.discovery import title_search
from ..services.display.publication_table import corpus_ids


@login_required
def title_search_view(request):
    """
    Find a publication from its title and add it (#309). A GET form: the results have an
    address, and the page comes back to them after an addition.
    """
    form = TitleSearchForm(request.GET or None)
    context = {"form": form}
    if form.is_valid():
        query = title_search.TitleQuery(**form.cleaned_data)
        candidates, failed = title_search.search(query)
        context.update(
            searched=True,
            candidates=candidates,
            failed=failed,
            user_pub_ids=corpus_ids(request.user),
        )
    return render(request, "references/title_search.html", context)
