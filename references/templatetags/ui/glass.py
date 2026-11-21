"""
What floats over the content, in frosted glass: popovers, notifications (toasts),
{% glass_classes %}.
"""

from .components import alert
from .library import register

# Frosted glass (#202): what floats over the content (a tooltip, a floating panel) lets it
# show through, blurred, under a light border and a soft shadow. Size, spacing and text are
# left to the element.
GLASS_CLASSES = (
    "rounded-lg border border-white/70 bg-white/60 shadow-lg shadow-gray-900/10 "
    "ring-1 ring-gray-900/5 backdrop-blur-md backdrop-saturate-150"
)


# A panel opened by a button, a popover: in the top layer, a scrolling card cannot cut it;
# a click outside closes it, and opening another one closes it too. Under its button where
# anchor positioning exists (flipped near the right edge), in the middle of the screen
# elsewhere. The header styles (select-none…) are undone, for the filters of the columns.
# A popover floats over the content: frosted glass (#333).
POPOVER_PANEL_CLASSES = (
    f"{GLASS_CLASSES} w-64 p-3 text-left text-sm font-normal text-gray-900 select-text "
    "supports-[position-area:bottom]:inset-auto supports-[position-area:bottom]:m-1 "
    "[position-area:bottom_span-right] [position-try-fallbacks:flip-inline]"
)


# Levels of django.contrib.messages, as alert variants.
MESSAGE_VARIANTS = {
    "debug": "secondary",
    "info": "primary",
    "success": "success",
    "warning": "warning",
    "error": "danger",
}


# A toast floats over the content too: the tint of its variant, translucent, on frosted
# glass (#333). Opaque enough for its text to stay legible over a dark content.
TOAST_BASE = "flex items-start gap-2 rounded-lg border p-3 text-sm"
TOAST_VARIANTS = {
    "primary": "border-blue-200/80 bg-blue-50/80 text-blue-900",
    "secondary": "border-white/70 bg-white/75 text-gray-900",
    "danger": "border-red-200/80 bg-red-50/85 text-red-900",
    "warning": "border-amber-200/80 bg-amber-50/85 text-amber-900",
    "success": "border-green-200/80 bg-green-50/80 text-green-900",
}
TOAST_CLASSES = (
    "pointer-events-auto shadow-lg shadow-gray-900/10 ring-1 ring-gray-900/5 "
    "backdrop-blur-md backdrop-saturate-150"
)
# Successes and information fade out (static/js/toasts.js); warnings and errors stay.
AUTOHIDE_VARIANTS = {"primary", "secondary", "success"}


@register.inclusion_tag("components/toast.html")
def message_toast(message):
    """A message of django.contrib.messages, shown as a notification (toast)."""
    variant = MESSAGE_VARIANTS.get(message.level_tag, "primary")
    context = alert(message, variant)
    return {
        **context,
        "classes": f"{TOAST_BASE} {TOAST_VARIANTS[variant]} {TOAST_CLASSES}",
        "autohide": variant in AUTOHIDE_VARIANTS,
    }


@register.simple_tag
def toast_classes(variant="primary"):
    """{% toast_classes %}: a toast that is not a message (the progress of the queue, #379)."""
    return f"{TOAST_BASE} {TOAST_VARIANTS[variant]} {TOAST_CLASSES}"


@register.simple_tag
def popover_panel_classes():
    """{% popover_panel_classes %}: the classes of a panel opened by a button (popover)."""
    return POPOVER_PANEL_CLASSES


@register.simple_tag
def glass_classes():
    """{% glass_classes %}: the frosted glass of what floats over the content."""
    return GLASS_CLASSES
