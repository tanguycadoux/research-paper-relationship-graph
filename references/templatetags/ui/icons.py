"""
Icons and links to other sites: {% icon %}, {% external_link %}, and the mark of the
references to identify in the graphs, {% graph_warning_icon %}.
"""

import re

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from references.services.display.icons import UnknownIcon, icon_parts

from .library import register

EXTERNAL_LINK_ICON = "ml-0.5 inline-block size-[0.9em] align-[-0.1em]"


# The mark of a publication with references to identify in a citation graph (#452): the
# Material Symbols icon `warning`, amber (#282), over its own triangle filled with a light
# amber, so that it reads over any node. Colours written out: graph/style.js and
# graph/export.js draw it as an image, without the stylesheet.
WARNING_INK = "#b45309"  # amber-700
WARNING_FILL = "#fde68a"  # amber-200
WARNING_CLASSES = "mr-1 inline-block size-3.5 align-[-0.2em]"


@register.simple_tag
def graph_warning_icon():
    """The SVG of the mark, with its size for an image (width, height) and its colours."""
    view_box, inner = icon_parts("warning")
    path = re.search(r'\bd="([^"]+)"', inner).group(1)
    # The first outline of the icon: its outer triangle.
    triangle = path[: path.upper().index("Z") + 1]
    return format_html(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="{}" width="24" height="24" '
        'class="{}" aria-hidden="true" focusable="false" data-graph-warning-icon>'
        '<path d="{}" fill="{}"/><path d="{}" fill="{}"/></svg>',
        view_box,
        WARNING_CLASSES,
        triangle,
        WARNING_FILL,
        path,
        WARNING_INK,
    )


@register.simple_tag
def icon(name, **attrs):
    """A decorative icon, inline and sized like the text unless a class says otherwise."""
    try:
        view_box, inner = icon_parts(name)
    except UnknownIcon as error:
        raise template.TemplateSyntaxError(str(error)) from error
    return format_html(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="{}" class="{}" fill="currentColor" '
        'aria-hidden="true" focusable="false">{}</svg>',
        view_box,
        attrs.get("class", "inline-block size-[1.25em] shrink-0 align-[-0.25em]"),
        mark_safe(inner),  # read from our own static/icons/ files
    )


@register.simple_tag
def external_link(url, label, **attrs):
    """
    A link to another site: it opens a new tab, which an icon and a text for screen
    readers announce.
    """
    return format_html(
        '<a href="{}" target="_blank" rel="noopener noreferrer"{}>{}'
        '<span class="sr-only"> (nouvel onglet)</span>{}</a>',
        url,
        format_html(' class="{}"', attrs["class"]) if attrs.get("class") else "",
        label,
        icon("open_in_new", **{"class": EXTERNAL_LINK_ICON}),
    )
