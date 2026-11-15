"""
The main navigation: {% load navigation %}{% main_navigation %}. The current link is
the one whose URL is the longest prefix of the page path: « Publications » on a
publication, « Combiner des auteurs » on a merge confirmation. Some links count what
waits for an action (#152): « Conflits, 2 en attente »; the references to identify have
their own link, « À identifier », which filters the corpus (#276). Below md, each group
is a menu (#207); from md, the groups follow each other in a sidebar.
"""

from urllib.parse import parse_qsl

from django import template
from django.urls import reverse

from ..services.display import pending

register = template.Library()

# (group title, reserved to logged-in users, [(label, URL name, icon[, query])])
NAVIGATION = [
    (
        "Mon corpus",
        True,
        [
            ("Publications", "corpus", "bookmarks"),
            # Its own link, so that the count is not read as a number of publications (#276).
            ("À identifier", "corpus", "playlist_play", "?to_identify=1"),
            ("Suggestions", "corpus_suggestions", "lightbulb"),
            ("Mon graphe", "corpus_graph", "hub"),
        ],
    ),
    (
        "Base commune",
        False,
        [
            ("Publications", "publication_list", "article"),
            ("Auteurs", "author_list", "group"),
            ("Graphe", "base_graph", "hub"),
        ],
    ),
    (
        "Corrections",
        True,
        [
            ("Combiner des auteurs", "author_merge_select", "merge"),
            ("Doublons probables", "author_duplicates", "difference"),
            ("Conflits", "conflict_list", "report"),
        ],
    ),
]
# Below sm, the menus are named shorter, so that the three fit in 390 px without
# scrolling (#331): « Corrections » was cut at the right edge, with its counter.
SHORT_TITLES = {"Mon corpus": "Corpus", "Base commune": "Base"}
# Counters of the private links, by URL: the count and what it is, for screen readers.
# Nothing is shown at zero.
COUNTERS = {
    "corpus?to_identify=1": (pending.references_to_identify, "en attente"),
    "conflict_list": (lambda user: pending.open_conflicts(), "en attente"),
    # Suggestions rather than tasks, but each waits for a look (#270).
    "author_duplicates": (lambda user: pending.probable_duplicates(), "à examiner"),
}
# relative: the text of a counter for screen readers stays inside the link, which may be
# in the scrolling strip of a small screen (#150).
LINK_BASE = (
    "relative flex items-center gap-2 whitespace-nowrap rounded-md px-2 py-1.5 text-sm no-underline"
)
# The button of a menu, tighter than a link: three of them fit in 390 px (#207).
MENU_BASE = (
    "relative flex cursor-pointer list-none items-center gap-1 whitespace-nowrap rounded-md "
    "px-1.5 py-1.5 text-sm [&::-webkit-details-marker]:hidden"
)
LINK_CURRENT = "bg-gray-100 font-semibold text-gray-900"
LINK_OTHER = "text-gray-700 hover:bg-gray-50 hover:text-gray-900"


def current_url(urls, path):
    """The longest URL that is the path or one of its parents ("/" only for itself)."""
    matches = [url for url in urls if path == url or (url != "/" and path.startswith(url))]
    return max(matches, key=len, default=None)


@register.inclusion_tag("references/_navigation.html", takes_context=True)
def main_navigation(context):
    user, request = context["user"], context["request"]
    authenticated = user.is_authenticated
    groups = [
        (title, [navigation_link(entry, user) for entry in links])
        for title, private, links in NAVIGATION
        if authenticated or not private
    ]
    urls = [url for _, links in groups for _, url, _, _ in links]
    # A link with a query is current when the page has its parameters (« À identifier »
    # on /corpus/?to_identify=1&sort=year); otherwise, the longest parent.
    current = next((url for url in urls if with_query(url, request)), None) or current_url(
        [url for url in urls if "?" not in url], request.path
    )
    here = current if current and "?" in current else request.path
    return {"groups": [navigation_group(title, links, current, here) for title, links in groups]}


def navigation_link(entry, user):
    """(label, URL, icon, counter) of an entry of NAVIGATION."""
    label, name, icon, *query = entry
    query = query[0] if query else ""
    return label, reverse(name) + query, icon, counter(name + query, user)


def with_query(url, request):
    path, _, query = url.partition("?")
    return (
        bool(query)
        and request.path == path
        and all(request.GET.get(key) == value for key, value in parse_qsl(query))
    )


def navigation_group(title, links, current, path):
    """
    A group with its links. On a small screen, a group is a menu (#207): it stands out
    when it holds the current page, and shows the total of its counters.
    """
    links = [
        {
            "label": label,
            "url": url,
            "icon": icon,
            "current": ("page" if url == path else "true") if url == current else "",
            "classes": f"{LINK_BASE} {LINK_CURRENT if url == current else LINK_OTHER}",
            "count": count,
        }
        for label, url, icon, count in links
    ]
    holds_current = any(link["current"] for link in links)
    return {
        "title": title,
        "short_title": SHORT_TITLES.get(title, title),
        "links": links,
        "current": holds_current,
        "classes": f"{MENU_BASE} {LINK_CURRENT if holds_current else LINK_OTHER}",
        "count": sum(link["count"][0] for link in links if link["count"]),
    }


def counter(name, user):
    """
    (count, what it is) for a link with a counter and something to count, else None.
    name: the URL name, followed by the query of the link if it has one.
    """
    if name not in COUNTERS or not user.is_authenticated:
        return None
    count_of, what = COUNTERS[name]
    count = count_of(user)
    return (count, what) if count else None
