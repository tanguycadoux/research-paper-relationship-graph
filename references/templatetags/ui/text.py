"""Text: the |pluralize_fr filter."""

from references.services.display import wording

from .library import register


@register.filter
def pluralize_fr(value, suffixes="s"):
    """
    {{ n|pluralize_fr }}, {{ n|pluralize_fr:"nt" }}, {{ n|pluralize_fr:"a,ont" }}: as
    Django's pluralize, which puts 0 in the plural, but 0 and 1 take the singular in
    French (#411). A list is agreed with its length.
    """
    number = len(value) if hasattr(value, "__len__") else value
    try:
        return wording.suffix(int(number), suffixes)
    except TypeError, ValueError:
        return ""
