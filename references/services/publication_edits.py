"""
Corrections made with « Modifier » on a publication (#146): a corrected title or date
is kept when the sources are read again, and a new DOI or ISBN replaces what was
fetched for the old one.
"""

from django.db import transaction

from ..models import Author
from .books import import_book_metadata
from .importer import import_publication
from .parser import parse_publication

# Fields filled from the sources, and the flag that protects a manual correction.
SOURCE_FIELDS = {"title": "title_edited", "publication_date": "date_edited"}
IDENTIFIERS = {"doi", "isbn"}


def record_manual_edits(pub, changed_fields):
    """
    Mark the changed source fields as corrected by hand. An emptied field is not:
    the sources fill it again.
    """
    for field, flag in SOURCE_FIELDS.items():
        if field in changed_fields:
            setattr(pub, flag, bool(getattr(pub, field)))


def identifier_changed(changed_fields):
    return bool(IDENTIFIERS & set(changed_fields))


def restore_source_values(pub):
    """Forget the manual corrections and read the stored answer again (no request)."""
    pub.title_edited = pub.date_edited = False
    with transaction.atomic():
        pub.save(update_fields=["title_edited", "date_edited"])
        parse_publication(pub, parse_references=False)


def refetch_after_identifier_change(pub):
    """
    The DOI or ISBN now designates another work: drop what was fetched for the old
    one (answers of the sources, author slots, bibliography), then import the new
    one. Return False if no metadata could be retrieved.
    """
    with transaction.atomic():
        author_ids = list(pub.authors.values_list("pk", flat=True))
        pub.external_records.all().delete()
        pub.cited_references.all().delete()
        pub.authorpublication_set.all().delete()
        Author.objects.filter(pk__in=author_ids, publications__isnull=True).delete()
    if pub.doi:
        return import_publication(pub, with_references=pub.parse_references)
    if pub.isbn:
        return import_book_metadata(pub)
    return False
