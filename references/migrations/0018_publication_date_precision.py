from django.db import migrations, models

# Copy of the date reading of references.services.metadata_formats at the time of
# this migration: number of date parts given by the preferred source.
PRIORITY = ["crossref", "datacite", "openlibrary"]
PRECISIONS = {1: "year", 2: "month", 3: "day"}


def crossref_parts(data):
    date_parts = data.get("message", {}).get("issued", {}).get("date-parts", [])
    return date_parts[0] if date_parts else []


def datacite_parts(data):
    attributes = data.get("data", {}).get("attributes", {})
    for date in attributes.get("dates", []):
        parts = str(date.get("date", "")).split("-")
        if date.get("dateType") == "Issued" and all(p.isdigit() for p in parts):
            return parts[:3]
    return [attributes["publicationYear"]] if attributes.get("publicationYear") else []


def openlibrary_parts(data):
    return [data["first_publish_year"]] if data.get("first_publish_year") else []


PARTS = {"crossref": crossref_parts, "datacite": datacite_parts, "openlibrary": openlibrary_parts}


def precision(pub, records):
    """Precision given by the preferred source; a year-only identification otherwise."""
    for source in PRIORITY:
        if source in records:
            parts = PARTS[source](records[source])
            return PRECISIONS[min(len(parts), 3)] if parts else "day"
    # Created from a cited reference identified with a year only (identification.py).
    first_of_year = (pub.publication_date.month, pub.publication_date.day) == (1, 1)
    return "year" if first_of_year else "day"


def fill_precisions(apps, schema_editor):
    Publication = apps.get_model("references", "Publication")
    ExternalRecord = apps.get_model("references", "ExternalRecord")
    publications = Publication.objects.filter(publication_date__isnull=False, date_edited=False)
    records = {}
    for record in ExternalRecord.objects.filter(
        publication__in=publications, data__isnull=False
    ).only("publication_id", "source", "data"):
        records.setdefault(record.publication_id, {})[record.source] = record.data
    changed = []
    for pub in publications.only("pk", "publication_date"):
        pub.publication_date_precision = precision(pub, records.get(pub.pk, {}))
        if pub.publication_date_precision != "day":
            changed.append(pub)
    Publication.objects.bulk_update(changed, ["publication_date_precision"])


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0017_publication_manual_edits"),
    ]

    operations = [
        migrations.AddField(
            model_name="publication",
            name="publication_date_precision",
            field=models.CharField(
                choices=[("year", "année"), ("month", "mois"), ("day", "jour")],
                default="day",
                max_length=5,
            ),
        ),
        migrations.RunPython(fill_precisions, migrations.RunPython.noop),
    ]
