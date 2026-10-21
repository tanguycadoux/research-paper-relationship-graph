"""
Interface components: {% load ui %}, then

    {% button "Fusionner" %}
    {% button "Supprimer" variant="danger" icon="delete" %}
    {% button "Fermer" icon="close" icon_only=True type="button" %}
    {% button_link "Voir la fiche" url=… variant="secondary" %}
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

BUTTON_BASE = (
    "inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm "
    "font-medium no-underline cursor-pointer focus-visible:outline-2 "
    "focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
)
BUTTON_VARIANTS = {
    "primary": "bg-blue-700 text-white hover:bg-blue-800 focus-visible:outline-blue-700",
    "secondary": (
        "border border-gray-300 bg-white text-gray-900 hover:bg-gray-50 "
        "focus-visible:outline-gray-500"
    ),
    "danger": "bg-red-700 text-white hover:bg-red-800 focus-visible:outline-red-700",
    "warning": "bg-amber-400 text-gray-900 hover:bg-amber-500 focus-visible:outline-amber-500",
    "success": "bg-green-700 text-white hover:bg-green-800 focus-visible:outline-green-700",
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


def labelled_content(label, icon_name, icon_only):
    """Context shared by buttons and button links: an icon alone needs an accessible label."""
    if not label:
        raise template.TemplateSyntaxError("Un bouton a toujours un libellé.")
    if icon_only and not icon_name:
        raise template.TemplateSyntaxError("icon_only demande une icône.")
    return {"label": label, "icon": icon_name, "icon_only": icon_only}


@register.inclusion_tag("components/button.html")
def button(
    label, variant="primary", icon=None, icon_only=False, type="submit", formaction="", **attrs
):
    return {
        **labelled_content(label, icon, icon_only),
        "classes": f"{BUTTON_BASE} {variant_classes('button', BUTTON_VARIANTS, variant)}",
        "type": type,
        "formaction": formaction,
        "name": attrs.get("name", ""),
        "value": attrs.get("value", ""),
    }


@register.inclusion_tag("components/button_link.html")
def button_link(label, url, variant="primary", icon=None, icon_only=False):
    return {
        **labelled_content(label, icon, icon_only),
        "classes": f"{BUTTON_BASE} {variant_classes('button_link', BUTTON_VARIANTS, variant)}",
        "url": url,
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
def card(content, title="", level=2):
    """A card: {% card title="…" level=3 %}content{% endcard %}."""
    if level not in range(2, 7):
        raise template.TemplateSyntaxError(
            "card : level va de 2 à 6 (le h1 est le titre de la page)."
        )
    heading = format_html('<h{} class="{}">{}</h{}>', level, CARD_TITLE_CLASSES, title, level)
    return format_html(
        '<section class="{}">{}{}</section>', CARD_CLASSES, heading if title else "", content
    )
