"""
The mechanics of the tables: {% pagination %}, {% column_header %} (sort and filter),
{% sort_links %}, {% filter_summary %}, {% row_title_classes %}.
"""

from .components import BUTTON_BASE, BUTTON_ICON, BUTTON_VARIANTS, BUTTON_WITH_ICON_AND_LABEL
from .glass import POPOVER_PANEL_CLASSES
from .library import register

# Links of the pagination: secondary buttons; the page shown, a primary one that is not a
# link. Previous and next keep their icon on the outer side. relative: the hidden « Page »
# stays inside its link.
PAGE_LINK_CLASSES = f"{BUTTON_BASE} relative min-w-8 px-2 {BUTTON_VARIANTS['secondary']}"
PAGE_CURRENT_CLASSES = (
    "relative inline-flex h-8 min-w-8 select-none items-center justify-center rounded-md border "
    "border-transparent bg-blue-700 px-2 text-sm font-medium text-white"
)
PAGE_PREVIOUS_CLASSES = f"{BUTTON_BASE} {BUTTON_WITH_ICON_AND_LABEL} {BUTTON_VARIANTS['secondary']}"
PAGE_NEXT_CLASSES = f"{BUTTON_BASE} pl-3 pr-[calc(0.375rem-1px)] {BUTTON_VARIANTS['secondary']}"


def page_url(request, number):
    """The current URL at another page, its other parameters (sort, filters) kept."""
    query = request.GET.copy()
    if number == 1:
        query.pop("page", None)
    else:
        query["page"] = number
    return f"?{query.urlencode()}" if query else request.path


@register.inclusion_tag("components/pagination.html", takes_context=True)
def pagination(context, page):
    """
    {% pagination page_obj %}: rows shown, previous and next, page numbers (from sm,
    first and last ones always, … between). Nothing on a single page.
    """
    request = context["request"]
    numbers = page.paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1)
    return {
        "page": page,
        "pages": [
            {
                "number": number,
                "current": number == page.number,
                "url": "" if number == page.paginator.ELLIPSIS else page_url(request, number),
            }
            for number in numbers
        ],
        "previous_url": page_url(request, page.number - 1) if page.has_previous() else "",
        "next_url": page_url(request, page.number + 1) if page.has_next() else "",
        "link_classes": PAGE_LINK_CLASSES,
        "current_classes": PAGE_CURRENT_CLASSES,
        "previous_classes": PAGE_PREVIOUS_CLASSES,
        "next_classes": PAGE_NEXT_CLASSES,
        "icon_classes": BUTTON_ICON,
    }


# A sortable column header: a link that looks like the header, its arrow beside it.
COLUMN_LINK_CLASSES = "inline-flex items-center gap-1 text-inherit hover:text-gray-900"
ARIA_SORT = {False: "ascending", True: "descending"}
# The funnel of a filterable column, blue while the filter is on.
FILTER_BUTTON_BASE = (
    "inline-flex size-6 shrink-0 cursor-pointer items-center justify-center rounded "
    "focus-visible:outline-2 focus-visible:outline-blue-700"
)
FILTER_BUTTON_OFF = f"{FILTER_BUTTON_BASE} text-gray-500 hover:bg-gray-100 hover:text-gray-700"
FILTER_BUTTON_ON = f"{FILTER_BUTTON_BASE} bg-blue-100 text-blue-800 hover:bg-blue-200"


def url_without(request, params):
    """The current URL without some parameters, back to the first page."""
    query = request.GET.copy()
    for param in (*params, "page"):
        query.pop(param, None)
    return f"?{query.urlencode()}" if query else request.path


def column_filter(request, filters, active, column):
    """The filter panel of a column, or None if the column has no filter."""
    if not filters or column not in filters.columns:
        return None
    label, column_filter = filters.columns[column]
    value = active.values.get(column) if active else None
    kept = [
        (name, item)
        for name, items in request.GET.lists()
        if name not in (*column_filter.params, "page")
        for item in items
    ]
    return {
        "id": f"filter-{column}",
        "kind": column_filter.kind,
        "label": label,
        "params": column_filter.params,
        "data": {param: request.GET.get(param, "") for param in column_filter.params},
        "raw": request.GET.get(column_filter.params[0], ""),
        "choices": [
            (key, choice[0]) for key, choice in getattr(column_filter, "choices", {}).items()
        ],
        "active": value is not None,
        "kept": kept,
        "remove_url": url_without(request, column_filter.params),
        "button_classes": FILTER_BUTTON_ON if value is not None else FILTER_BUTTON_OFF,
        "panel_classes": POPOVER_PANEL_CLASSES,
    }


@register.inclusion_tag("components/column_header.html", takes_context=True)
def column_header(context, label, column, classes=""):
    """
    A column header, {% column_header "Année" "year" %} (#115). With sorting and sort in
    the context (services/display/sorting.py), a link that sorts by the column, or reverses it;
    with filters and active_filters (services/display/filters.py), a funnel that opens its filter.
    Both go back to the first page and keep the other parameters.
    """
    request = context["request"]
    sorting, sort = context.get("sorting"), context.get("sort")
    header = {
        "label": label,
        "classes": classes,
        "url": "",
        "filter": column_filter(
            request, context.get("filters"), context.get("active_filters"), column
        ),
    }
    if not sorting or column not in sorting.columns:
        return header
    query = request.GET.copy()
    query.pop("page", None)
    query["sort"] = sorting.next_sort(sort, column).param
    sorted_here = sort.column == column
    return header | {
        "url": f"?{query.urlencode()}",
        "aria_sort": ARIA_SORT[sort.descending] if sorted_here else "",
        "arrow": ("arrow_downward" if sort.descending else "arrow_upward") if sorted_here else "",
        "link_classes": COLUMN_LINK_CLASSES,
    }


@register.inclusion_tag("components/sort_links.html", takes_context=True)
def sort_links(context, columns):
    """
    {% sort_links "title:Titre,year:Année" %} above a table, below sm only (#334): the
    columns it hides there can still sort it. Each link sorts by its column, or reverses
    the sort; nothing without sorting in the context.
    """
    request, sorting, sort = context["request"], context.get("sorting"), context.get("sort")
    if not sorting:
        return {"links": []}
    links = []
    for item in columns.split(","):
        column, label = item.split(":", 1)
        if column not in sorting.columns:
            continue
        query = request.GET.copy()
        query.pop("page", None)
        query["sort"] = sorting.next_sort(sort, column).param
        current = sort.column == column
        links.append(
            {
                "label": label,
                "url": f"?{query.urlencode()}",
                "current": current,
                "arrow": ("arrow_downward" if sort.descending else "arrow_upward")
                if current
                else "",
            }
        )
    return {"links": links}


@register.inclusion_tag("components/filter_summary.html", takes_context=True)
def filter_summary(context):
    """
    {% filter_summary %} above a filtered table: each active filter, which a click
    removes, and the errors of the filters. Nothing without a filter.
    """
    request, filters = context["request"], context.get("filters")
    active = context.get("active_filters")
    if not filters or not active:
        # A wrong year alone is no filter, but still an error to show.
        return {"active": [], "errors": active.errors if active is not None else []}
    all_params = [param for _, f in filters.columns.values() for param in f.params]
    items = []
    for column, value in active.values.items():
        label, column_filter = filters.columns[column]
        items.append(
            {
                "text": f"{label} {column_filter.describe(value)}",
                "remove_url": url_without(request, column_filter.params),
            }
        )
    return {
        "active": items,
        "errors": active.errors,
        "clear_url": url_without(request, all_params),
    }


# The title of a row in a table: the colour of the text, blue on hover. Blue links are
# kept for the actions and the secondary links: a dense table was a wall of blue (#282).
ROW_TITLE_CLASSES = "text-gray-900 hover:text-blue-700"


@register.simple_tag
def row_title_classes():
    """{% row_title_classes %}: the classes of the link that names a row of a table."""
    return ROW_TITLE_CLASSES
