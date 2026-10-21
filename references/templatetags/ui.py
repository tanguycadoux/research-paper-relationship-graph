"""
Interface components: {% load ui %}, then

    {% button "Fusionner" %}
    {% button "Supprimer" variant="danger" icon="delete" %}
    {% button "Fermer" icon="close" icon_only=True type="button" %}
    {% button "Voir la fiche" url=… variant="secondary" %}   (a link: <a href>)
    {% badge "12 à identifier" variant="warning" %}
    {% alert "Import terminé." variant="success" %}
    {% card title="Informations" %}…{% endcard %}
    {% icon "delete" class="size-5" %}

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
# An icon-only button is a 2rem square.
BUTTON_BASE = (
    "inline-flex h-8 items-center justify-center gap-1.5 whitespace-nowrap rounded-md border "
    "text-sm font-medium no-underline cursor-pointer focus-visible:outline-2 "
    "focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
)
BUTTON_WITH_LABEL = "px-3"
BUTTON_WITH_ICON_AND_LABEL = "pl-[calc(0.375rem-1px)] pr-3"
BUTTON_ICON_ONLY = "w-8"
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
BADGE_BASE = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
BADGE_VARIANTS = {
    "primary": "bg-blue-100 text-blue-800",
    "secondary": "bg-gray-100 text-gray-800",
    "danger": "bg-red-100 text-red-800",
    "warning": "bg-amber-100 text-amber-900",
    "success": "bg-green-100 text-green-800",
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
CARD_FLUSH_CLASSES = "overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm"
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


BUTTON_ONLY_ATTRIBUTES = ("type", "formaction", "name", "value")


def button_shape(icon, icon_only):
    if icon_only:
        return BUTTON_ICON_ONLY
    return BUTTON_WITH_ICON_AND_LABEL if icon else BUTTON_WITH_LABEL


@register.inclusion_tag("components/button.html")
def button(label, url="", variant="primary", icon=None, icon_only=False, **attrs):
    """
    A button, or a link styled as a button when it has a url: <a> navigates,
    <button> acts. type (submit by default), formaction, name and value only
    make sense on a <button>.
    """
    if not label:
        raise template.TemplateSyntaxError("Un bouton a toujours un libellé.")
    if icon_only and not icon:
        raise template.TemplateSyntaxError("icon_only demande une icône.")
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
        "classes": " ".join(
            [
                BUTTON_BASE,
                button_shape(icon, icon_only),
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


@register.inclusion_tag("components/alert.html")
def message_alert(message):
    """A message of django.contrib.messages, shown as an alert of its level."""
    return alert(message, MESSAGE_VARIANTS.get(message.level_tag, "primary"))


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
