"""
Lists in pages of PAGE_SIZE rows (#154): the annotations of the table of
publications are computed for one page only, and the HTML stays light.
"""

from django.core.paginator import Paginator

PAGE_SIZE = 50


def page_of(request, queryset, page_size=PAGE_SIZE):
    """
    The page asked by ?page=: the first one if it is not a number, the last one if it is
    past the end. A link kept after a removal from the corpus still lands on a page.
    """
    return Paginator(queryset, page_size).get_page(request.GET.get("page"))


class PageMixin:
    """A ListView in pages, as forgiving as page_of."""

    paginate_by = PAGE_SIZE

    def paginate_queryset(self, queryset, page_size):
        page = page_of(self.request, queryset, page_size)
        return page.paginator, page, page.object_list, page.has_other_pages()
