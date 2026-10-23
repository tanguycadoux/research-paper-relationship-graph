"""
The main navigation: {% load navigation %}{% main_navigation %}. The current link is
the one whose URL is the longest prefix of the page path: « Publications » on a
publication, « Combiner des auteurs » on a merge confirmation.
"""

from django import template
from django.urls import reverse

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
LINK_BASE = "flex items-center gap-2 whitespace-nowrap rounded-md px-2 py-1.5 text-sm no-underline"
LINK_CURRENT = "bg-gray-100 font-semibold text-gray-900"
LINK_OTHER = "text-gray-700 hover:bg-gray-50 hover:text-gray-900"


def current_url(urls, path):
    """The longest URL that is the path or one of its parents ("/" only for itself)."""
    matches = [url for url in urls if path == url or (url != "/" and path.startswith(url))]
    return max(matches, key=len, default=None)


@register.inclusion_tag("references/_navigation.html", takes_context=True)
def main_navigation(context):
    authenticated = context["user"].is_authenticated
    groups = [
        (title, [(label, reverse(name), icon) for label, name, icon in links])
        for title, private, links in NAVIGATION
        if authenticated or not private
    ]
    path = context["request"].path
    current = current_url([url for _, links in groups for _, url, _ in links], path)
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
                    }
                    for label, url, icon in links
                ],
            )
            for title, links in groups
        ]
    }
