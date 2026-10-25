from django.http import QueryDict
from django.shortcuts import render

from ..models import Publication
from ..services.publication_table import corpus_ids, for_publication_table
from ..services.search import filter_publications, parse, search_authors
from ..services.sorting import PUBLICATIONS
from .pagination import page_of

# Beyond, the query is too vague for a list of names: the page says how many match.
AUTHORS_SHOWN = 20


def list_filter(request, sort, sorting):
    """
    The filter of a list (#115): the search bar, read by the same parser. The form keeps
    the sort of the list; « Effacer » drops the filter only.
    """
    text = request.GET.get("q", "").strip()
    kept = QueryDict(mutable=True)
    if sort != sorting.default:
        kept["sort"] = sort.param
    return {
        "q": text,
        "query": parse(text),
        "sort_param": kept.get("sort", ""),
        "clear_url": f"?{kept.urlencode()}" if kept else request.path,
    }


def search(request):
    """Publications in pages, then the first matching authors (#153)."""
    text = request.GET.get("q", "").strip()
    query = parse(text)
    context = {"q": text, "query": query}
    if query:
        publications = for_publication_table(filter_publications(Publication.objects.all(), query))
        sort = PUBLICATIONS.read(request.GET.get("sort"))
        page = page_of(request, PUBLICATIONS.apply(publications, sort))
        authors = search_authors(query).order_by("last_name", "first_name", "pk")
        context |= {
            "publications": page.object_list,
            "page_obj": page,
            "sorting": PUBLICATIONS,
            "sort": sort,
            "authors": authors[:AUTHORS_SHOWN],
            "author_count": authors.count(),
            "user_pub_ids": corpus_ids(request.user),
        }
    return render(request, "references/search.html", context)
