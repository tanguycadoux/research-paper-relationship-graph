from django.db import migrations

FIELDS = {
    "crossref": ("crossref_json", "crossref_fetched_at"),
    "openlibrary": ("openlibrary_json", "openlibrary_fetched_at"),
}


def copy_to_records(apps, schema_editor):
    Publication = apps.get_model("references", "Publication")
    ExternalRecord = apps.get_model("references", "ExternalRecord")
    records = [
        ExternalRecord(
            publication=pub,
            source=source,
            data=getattr(pub, data_field),
            fetched_at=getattr(pub, date_field),
        )
        for pub in Publication.objects.all()
        for source, (data_field, date_field) in FIELDS.items()
        if getattr(pub, date_field) is not None
    ]
    ExternalRecord.objects.bulk_create(records)


def copy_back(apps, schema_editor):
    Publication = apps.get_model("references", "Publication")
    for record in apps.get_model("references", "ExternalRecord").objects.all():
        data_field, date_field = FIELDS[record.source]
        Publication.objects.filter(pk=record.publication_id).update(
            **{data_field: record.data, date_field: record.fetched_at}
        )


class Migration(migrations.Migration):
    dependencies = [("references", "0005_externalrecord")]

    operations = [migrations.RunPython(copy_to_records, copy_back)]
