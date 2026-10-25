"""
The main navigation: {% load navigation %}{% main_navigation %}. The current link is
the one whose URL is the longest prefix of the page path: « Publications » on a
publication, « Combiner des auteurs » on a merge confirmation. Some links count what
waits for an action (#152): « Conflits, 2 en attente ». Below md, each group is a menu
(#207); from md, the groups follow each other in a sidebar.
"""

from django import template
from django.urls import reverse

from ..services import pending

register = template.Library()

# (group title, reserved to logged-in users, [(label, URL name, icon)])
NAVIGATION = [
    (
        "Mon corpus",
        True,
        [
            ("Mes références", "corpus", "bookmarks"),
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
# Counters of the private links, by URL name: the count and what it is, for screen
# readers. Nothing is shown at zero.
COUNTERS = {
    "corpus": (pending.references_to_identify, "à identifier"),
    "conflict_list": (lambda user: pending.open_conflicts(), "en attente"),
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
    user = context["user"]
    authenticated = user.is_authenticated
    groups = [
        (title, [(label, reverse(name), icon, counter(name, user)) for label, name, icon in links])
        for title, private, links in NAVIGATION
        if authenticated or not private
    ]
    path = context["request"].path
    current = current_url([url for _, links in groups for _, url, _, _ in links], path)
    return {"groups": [navigation_group(title, links, current, path) for title, links in groups]}


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
        "links": links,
        "current": holds_current,
        "classes": f"{MENU_BASE} {LINK_CURRENT if holds_current else LINK_OTHER}",
        "count": sum(link["count"][0] for link in links if link["count"]),
    }


def counter(name, user):
    """(count, what it is) for a link with a counter and something to count, else None."""
    if name not in COUNTERS or not user.is_authenticated:
        return None
    count_of, what = COUNTERS[name]
    count = count_of(user)
    return (count, what) if count else None
