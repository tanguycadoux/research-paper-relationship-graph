"""
Stored answers of external sources (ExternalRecord): a source is never asked
again about a publication it already answered for, unless a refresh is forced.
"""

from django.utils import timezone

from ..models import ExternalRecord

Source = ExternalRecord.Source


def store_record(pub, source, data):
    """Store the answer of a source; data None means the source does not know pub."""
    ExternalRecord.objects.update_or_create(
        publication=pub, source=source, defaults={"data": data, "fetched_at": timezone.now()}
    )


def has_metadata(pub):
    return pub.external_records.filter(data__isnull=False).exists()


def records_by_source(pub):
    """{source: data} of the sources that know the publication."""
    return dict(pub.external_records.filter(data__isnull=False).values_list("source", "data"))
