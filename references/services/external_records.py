"""
Stored answers of external sources (ExternalRecord): a source is never asked
again about a publication it already answered for, unless a refresh is forced.
"""

from django.db.models import Case, CharField, Exists, OuterRef, Q, Value, When
from django.utils import timezone

from ..models import ExternalRecord

Source = ExternalRecord.Source


def store_record(pub, source, data):
    """Store the answer of a source; data None means the source does not know pub."""
    ExternalRecord.objects.update_or_create(
        publication=pub, source=source, defaults={"data": data, "fetched_at": timezone.now()}
    )


def has_record(pub, source):
    """True if the source already answered about pub (even 'unknown')."""
    return pub.external_records.filter(source=source).exists()


def has_metadata(pub):
    return pub.external_records.filter(data__isnull=False).exists()


def records_by_source(pub):
    """{source: data} of the sources that know the publication."""
    return dict(pub.external_records.filter(data__isnull=False).values_list("source", "data"))


# Metadata status of a publication with a DOI or an ISBN: never asked yet (a source
# was unreachable during the import, for instance), or unknown to every source asked.
METADATA_MISSING = "missing"
METADATA_UNKNOWN = "unknown"


def metadata_status(pub):
    """METADATA_MISSING, METADATA_UNKNOWN, or "" (known, or nothing to look up)."""
    if not (pub.doi or pub.isbn) or has_metadata(pub):
        return ""
    return METADATA_UNKNOWN if pub.external_records.exists() else METADATA_MISSING


def with_metadata_status(publications):
    """Annotate publications with metadata_status, in the same query."""
    records = ExternalRecord.objects.filter(publication=OuterRef("pk"))
    return publications.annotate(
        metadata_status=Case(
            When(Q(doi="") & Q(isbn=""), then=Value("")),
            When(Exists(records.filter(data__isnull=False)), then=Value("")),
            When(Exists(records), then=Value(METADATA_UNKNOWN)),
            default=Value(METADATA_MISSING),
            output_field=CharField(),
        )
    )
