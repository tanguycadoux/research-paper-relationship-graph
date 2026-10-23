"""
The main navigation: {% load navigation %}{% main_navigation %}. The current link is
the one whose URL is the longest prefix of the page path: « Publications » on a
publication, « Combiner des auteurs » on a merge confirmation. Some links count what
waits for an action (#152): « Conflits, 2 en attente ».
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
        [("Mes références", "corpus", "bookmarks"), ("Mon graphe", "corpus_graph", "hub")],
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
    return {
        "groups": [
            (
                title,
                [
                    {
                        "label": label,
                        "url": url,
                        "icon": icon,
                        "current": ("page" if url == path else "true") if url == current else "",
                        "classes": f"{LINK_BASE} {LINK_CURRENT if url == current else LINK_OTHER}",
                        "count": count,
                    }
                    for label, url, icon, count in links
                ],
            )
            for title, links in groups
        ]
    }


def counter(name, user):
    """(count, what it is) for a link with a counter and something to count, else None."""
    if name not in COUNTERS or not user.is_authenticated:
        return None
    count_of, what = COUNTERS[name]
    count = count_of(user)
    return (count, what) if count else None
