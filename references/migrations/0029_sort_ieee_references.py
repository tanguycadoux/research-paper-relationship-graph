import re

from django.db import migrations

# Copy of references.services.imports.parser.NUMBERED_KEY at the time of this migration.
NUMBERED_KEY = re.compile(r"ref(\d+)")


def numbered_order(refs):
    """
    The references sorted by the number of their key, when every key is "ref<n>" with
    distinct numbers (#258); None otherwise, or when they already are in that order.
    """
    matches = [NUMBERED_KEY.fullmatch(ref.key or "") for ref in refs]
    if not all(matches):
        return None
    numbers = [int(match.group(1)) for match in matches]
    if len(set(numbers)) < len(numbers) or numbers == sorted(numbers):
        return None
    return [ref for _, ref in sorted(zip(numbers, refs, strict=True), key=lambda pair: pair[0])]


def sort_ieee_references(apps, schema_editor):
    """
    Renumber the bibliographies imported in the order IEEE deposits them. Manual
    decisions are stored on the reference itself, so they follow it. In two steps:
    the positions must stay unique for a source (unique_reference_position).
    """
    CitedReference = apps.get_model("references", "CitedReference")
    by_source = {}
    for ref in CitedReference.objects.order_by("source_id", "position").only(
        "pk", "source_id", "position", "key"
    ):
        by_source.setdefault(ref.source_id, []).append(ref)
    for refs in by_source.values():
        ordered = numbered_order(refs)
        if ordered is None:
            continue
        shift = max(ref.position for ref in refs) + 1
        for ref in refs:
            ref.position += shift
        CitedReference.objects.bulk_update(refs, ["position"])
        for position, ref in enumerate(ordered):
            ref.position = position
        CitedReference.objects.bulk_update(ordered, ["position"])


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0028_incoming_citations"),
    ]

    operations = [
        migrations.RunPython(sort_ieee_references, migrations.RunPython.noop),
    ]
