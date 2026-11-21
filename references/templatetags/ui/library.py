"""The library of {% load ui %}, which every module of the package registers in."""

from django import template

register = template.Library()


def variant_classes(component, variants, variant):
    if variant not in variants:
        raise template.TemplateSyntaxError(
            f"{component} : variante inconnue {variant!r} (possibles : {', '.join(variants)})."
        )
    return variants[variant]
