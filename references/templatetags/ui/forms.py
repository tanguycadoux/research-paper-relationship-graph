"""Form fields: {% field %}, {% form_errors %}."""

from .library import register


@register.inclusion_tag("components/form_errors.html")
def form_errors(form):
    """{% form_errors form %}: the errors of the whole form, as alerts, above its fields."""
    return {"form": form}


@register.inclusion_tag("components/field.html")
def field(bound_field, rows=None):
    """
    {% field form.title %} (#337): the label without a colon, the input, its help in small
    print under it, its errors under it in red; the input points to both
    (aria-describedby) and says when it is invalid. rows: the height of a textarea.
    """
    field_id = bound_field.id_for_label or bound_field.html_name
    described = []
    if bound_field.help_text:
        described.append(f"{field_id}-help")
    if bound_field.errors:
        described.append(f"{field_id}-errors")
    attrs = {}
    if described:
        attrs["aria-describedby"] = " ".join(described)
    if bound_field.errors:
        attrs["aria-invalid"] = "true"
    if rows:
        attrs["rows"] = rows
    return {
        "field": bound_field,
        "widget": bound_field.as_widget(attrs=attrs),
        "field_id": field_id,
    }
