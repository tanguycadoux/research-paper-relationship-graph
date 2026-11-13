import html
import re

from django.db import migrations

# Copy of references.services.imports.titles.clean_title at the time of this migration
# (#263): entities decoded until none is left, then markup removed.
TAG_PATTERN = re.compile(r"</?[A-Za-z][\w:.-]*(?:\s[^<>]*)?/?>")
SPACES_PATTERN = re.compile(r"\s+")
MAX_UNESCAPES = 3


def clean_title(raw):
    text = raw
    for _ in range(MAX_UNESCAPES):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    return SPACES_PATTERN.sub(" ", TAG_PATTERN.sub("", text)).strip()


def clean_titles(apps, schema_editor):
    """Titles of every publication, cited only or not; a title corrected by hand is kept."""
    Publication = apps.get_model("references", "Publication")
    changed = []
    for pub in Publication.objects.exclude(title="").filter(title_edited=False).only("pk", "title"):
        title = clean_title(pub.title)
        if title != pub.title:
            pub.title = title
            changed.append(pub)
    Publication.objects.bulk_update(changed, ["title"])


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0028_incoming_citations"),
    ]

    operations = [
        migrations.RunPython(clean_titles, migrations.RunPython.noop),
    ]
