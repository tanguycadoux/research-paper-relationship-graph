import html
import re

from django.db import migrations

# Copy of references.services.titles.clean_title at the time of this migration.
TAG_PATTERN = re.compile(r"</?[A-Za-z][\w:.-]*(?:\s[^<>]*)?/?>")
SPACES_PATTERN = re.compile(r"\s+")


def clean_title(raw):
    text = html.unescape(TAG_PATTERN.sub("", raw))
    return SPACES_PATTERN.sub(" ", text).strip()


def clean_titles(apps, schema_editor):
    Publication = apps.get_model("references", "Publication")
    changed = []
    for pub in Publication.objects.exclude(title="").only("pk", "title"):
        title = clean_title(pub.title)
        if title != pub.title:
            pub.title = title
            changed.append(pub)
    Publication.objects.bulk_update(changed, ["title"])


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0014_remove_publication_parse_references"),
    ]

    operations = [
        migrations.RunPython(clean_titles, migrations.RunPython.noop),
    ]
