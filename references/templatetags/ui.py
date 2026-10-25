"""
Interface components: {% load ui %}, then

    {% button "Fusionner" %}
    {% button "Supprimer" variant="danger" icon="delete" %}
    {% button "Fermer" icon="close" icon_only=True type="button" %}
    {% button "Se déconnecter" icon="logout" compact=True %}   (icon only on a small screen)
    {% button "Voir la fiche" url=… variant="secondary" %}   (a link: <a href>)
    {% badge "12 à identifier" variant="warning" %}
    {% alert "Import terminé." variant="success" %}
    {% card title="Informations" %}…{% endcard %}
    {% icon "delete" class="size-5" %}
    {% external_link "https://doi.org/"|add:pub.doi pub.doi class="break-all" %}
    {% pagination page_obj %}   (below a list in pages, its URL parameters kept)
    {% column_header "Année" "year" %}   (a <th>, sortable when the view gives sorting)

The Tailwind classes of each variant are written in full here, once: Tailwind
finds them by scanning this file.
"""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from references.services.icons import UnknownIcon, icon_parts

register = template.Library()

# Every button is 2rem high, border included, with a 1.25rem icon: the space around
# the icon, (2rem - 2px - 1.25rem) / 2, is the same on its left as above and below.
# An icon-only button is a 2rem square. select-none: a tap or a double click on an
# interface element never selects its text (#210), here and on the badges.
BUTTON_BASE = (
    "inline-flex h-8 select-none items-center justify-center gap-1.5 whitespace-nowrap "
    "rounded-md border text-sm font-medium no-underline cursor-pointer focus-visible:outline-2 "
    "focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
)
BUTTON_WITH_LABEL = "px-3"
BUTTON_WITH_ICON_AND_LABEL = "pl-[calc(0.375rem-1px)] pr-3"
BUTTON_ICON_ONLY = "w-8"
# compact: a 2rem square on a small screen, icon and label from sm (#150). relative keeps
# the hidden label, absolutely positioned, inside the button.
BUTTON_COMPACT = "relative w-8 sm:w-auto sm:pl-[calc(0.375rem-1px)] sm:pr-3"
BUTTON_ICON = "size-5 shrink-0"
BUTTON_VARIANTS = {
    "primary": (
        "border-transparent bg-blue-700 text-white hover:bg-blue-800 focus-visible:outline-blue-700"
    ),
    "secondary": (
        "border-gray-300 bg-white text-gray-900 hover:bg-gray-50 focus-visible:outline-gray-500"
    ),
    "danger": (
        "border-transparent bg-red-700 text-white hover:bg-red-800 focus-visible:outline-red-700"
    ),
    "warning": (
        "border-transparent bg-amber-400 text-gray-900 hover:bg-amber-500 "
        "focus-visible:outline-amber-500"
    ),
    "success": (
        "border-transparent bg-green-700 text-white hover:bg-green-800 "
        "focus-visible:outline-green-700"
    ),
    # Discreet pair for actions that add or take away (a corpus entry, for instance)
    "success-light": (
        "border-green-300 bg-green-50 text-green-800 hover:bg-green-100 "
        "focus-visible:outline-green-600"
    ),
    "danger-light": (
        "border-red-200 bg-red-50 text-red-700 hover:bg-red-100 focus-visible:outline-red-600"
    ),
}
BADGE_BASE = (
    "inline-flex select-none items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
)
BADGE_VARIANTS = {
    "primary": "bg-blue-100 text-blue-800",
    "secondary": "bg-gray-100 text-gray-800",
    "danger": "bg-red-100 text-red-800",
    "warning": "bg-amber-100 text-amber-900",
    "success": "bg-green-100 text-green-800",
    # Nothing to see: a count of 0 aligned with the others, without drawing the eye.
    "muted": "bg-gray-50 text-gray-500",
}
ALERT_BASE = "flex items-start gap-2 rounded-md border p-3 text-sm"
ALERT_VARIANTS = {
    "primary": "border-blue-200 bg-blue-50 text-blue-900",
    "secondary": "border-gray-200 bg-gray-50 text-gray-900",
    "danger": "border-red-200 bg-red-50 text-red-900",
    "warning": "border-amber-200 bg-amber-50 text-amber-900",
    "success": "border-green-200 bg-green-50 text-green-900",
}
ALERT_ICONS = {
    "primary": "info",
    "secondary": "info",
    "danger": "error",
    "warning": "warning",
    "success": "check_circle",
}
EXTERNAL_LINK_ICON = "ml-0.5 inline-block size-[0.9em] align-[-0.1em]"
CARD_CLASSES = "rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
# relative: the texts for screen readers in a wide table (sr-only, absolutely positioned)
# scroll with it, instead of widening the page (#150).
CARD_FLUSH_CLASSES = "relative overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm"
CARD_TITLE_CLASSES = "mb-2 text-base font-semibold"


def variant_classes(component, variants, variant):
    if variant not in variants:
        raise template.TemplateSyntaxError(
            f"{component} : variante inconnue {variant!r} (possibles : {', '.join(variants)})."
        )
    return variants[variant]


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


BUTTON_ONLY_ATTRIBUTES = ("type", "formaction", "name", "value")


def button_shape(icon, icon_only, compact):
    if icon_only:
        return BUTTON_ICON_ONLY
    if compact:
        return BUTTON_COMPACT
    return BUTTON_WITH_ICON_AND_LABEL if icon else BUTTON_WITH_LABEL


@register.inclusion_tag("components/button.html")
def button(label, url="", variant="primary", icon=None, icon_only=False, compact=False, **attrs):
    """
    A button, or a link styled as a button when it has a url: <a> navigates,
    <button> acts. type (submit by default), formaction, name and value only
    make sense on a <button>. compact: only the icon on a small screen, the label
    still read by screen readers.
    """
    if not label:
        raise template.TemplateSyntaxError("Un bouton a toujours un libellé.")
    if icon_only and not icon:
        raise template.TemplateSyntaxError("icon_only demande une icône.")
    if compact and not icon:
        raise template.TemplateSyntaxError("compact demande une icône.")
    unknown = attrs.keys() - set(BUTTON_ONLY_ATTRIBUTES)
    if unknown:
        raise template.TemplateSyntaxError(
            f"button : paramètre inconnu {', '.join(sorted(unknown))}."
        )
    if url and attrs:
        raise template.TemplateSyntaxError(
            f"button : {', '.join(sorted(attrs))} sans effet sur un lien (url={url!r})."
        )
    return {
        "label": label,
        "url": url,
        "icon": icon,
        "icon_only": icon_only,
        "compact": compact,
        "classes": " ".join(
            [
                BUTTON_BASE,
                button_shape(icon, icon_only, compact),
                variant_classes("button", BUTTON_VARIANTS, variant),
            ]
        ),
        "icon_classes": BUTTON_ICON,
        "type": attrs.get("type", "submit"),
        "formaction": attrs.get("formaction", ""),
        "name": attrs.get("name", ""),
        "value": attrs.get("value", ""),
    }


@register.inclusion_tag("components/badge.html")
def badge(label, variant="secondary", icon=None):
    return {
        "label": label,
        "icon": icon,
        "classes": f"{BADGE_BASE} {variant_classes('badge', BADGE_VARIANTS, variant)}",
    }


@register.inclusion_tag("components/alert.html")
def alert(message, variant="primary"):
    return {
        "message": message,
        "icon": ALERT_ICONS[variant] if variant in ALERT_ICONS else None,
        "classes": f"{ALERT_BASE} {variant_classes('alert', ALERT_VARIANTS, variant)}",
        # An error interrupts screen readers; the other messages wait their turn.
        "role": "alert" if variant == "danger" else "status",
    }


# Levels of django.contrib.messages, as alert variants.
MESSAGE_VARIANTS = {
    "debug": "secondary",
    "info": "primary",
    "success": "success",
    "warning": "warning",
    "error": "danger",
}


@register.simple_block_tag
def card(content, title="", level=2, flush=False):
    """
    A card: {% card title="…" level=3 %}content{% endcard %}, a <section> under its
    heading (a <div> without title). With flush=True, no inner padding and a
    horizontal scroll: the frame of a table.
    """
    if level not in range(2, 7):
        raise template.TemplateSyntaxError(
            "card : level va de 2 à 6 (le h1 est le titre de la page)."
        )
    classes = CARD_FLUSH_CLASSES if flush else CARD_CLASSES
    title_classes = f"{CARD_TITLE_CLASSES} px-4 pt-3" if flush else CARD_TITLE_CLASSES
    heading = format_html('<h{} class="{}">{}</h{}>', level, title_classes, title, level)
    if not title:
        return format_html('<div class="{}">{}</div>', classes, content)
    return format_html('<section class="{}">{}{}</section>', classes, heading, content)


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


@register.inclusion_tag("components/column_header.html", takes_context=True)
def column_header(context, label, column, classes=""):
    """
    A column header, {% column_header "Année" "year" %}: with sorting and sort in the
    context (services/sorting.py), a link that sorts by the column, or reverses it, back
    to the first page, the other parameters kept (#115).
    """
    sorting, sort = context.get("sorting"), context.get("sort")
    header = {"label": label, "classes": classes, "url": ""}
    if not sorting or column not in sorting.columns:
        return header
    query = context["request"].GET.copy()
    query.pop("page", None)
    query["sort"] = sorting.next_sort(sort, column).param
    sorted_here = sort.column == column
    return header | {
        "url": f"?{query.urlencode()}",
        "aria_sort": ARIA_SORT[sort.descending] if sorted_here else "",
        "arrow": ("arrow_downward" if sort.descending else "arrow_upward") if sorted_here else "",
        "link_classes": COLUMN_LINK_CLASSES,
    }


TOAST_CLASSES = "pointer-events-auto shadow-lg"
# Successes and information fade out (static/js/toasts.js); warnings and errors stay.
AUTOHIDE_VARIANTS = {"primary", "secondary", "success"}


@register.inclusion_tag("components/toast.html")
def message_toast(message):
    """A message of django.contrib.messages, shown as a notification (toast)."""
    variant = MESSAGE_VARIANTS.get(message.level_tag, "primary")
    context = alert(message, variant)
    return {
        **context,
        "classes": f"{context['classes']} {TOAST_CLASSES}",
        "autohide": variant in AUTOHIDE_VARIANTS,
    }
