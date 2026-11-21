"""Icons and links to other sites: {% icon %}, {% external_link %}."""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from references.services.display.icons import UnknownIcon, icon_parts

from .library import register

EXTERNAL_LINK_ICON = "ml-0.5 inline-block size-[0.9em] align-[-0.1em]"


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
