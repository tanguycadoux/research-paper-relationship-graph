"""The base components: {% button %}, {% badge %}, {% alert %}, {% card %}."""

from django import template
from django.utils.html import format_html

from .library import register, variant_classes

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
    # Same family, for a row action that waits for the user (« Identifier », #384).
    "warning-light": (
        "border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 "
        "focus-visible:outline-amber-600"
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


CARD_CLASSES = "rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
# relative: the texts for screen readers in a wide table (sr-only, absolutely positioned)
# scroll with it, instead of widening the page (#150).
CARD_FLUSH_CLASSES = "relative overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm"
CARD_TITLE_CLASSES = "mb-2 text-base font-semibold"


BUTTON_ONLY_ATTRIBUTES = ("type", "formaction", "name", "value", "popovertarget", "disabled")


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
    make sense on a <button>, as popovertarget (the id of the popover it opens) and
    disabled.
    compact: only the icon on a small screen, the label still read by screen readers.
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
        "popovertarget": attrs.get("popovertarget", ""),
        # A control that is useless for now stays in place, disabled (CONTRIBUTING).
        "disabled": bool(attrs.get("disabled")),
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
