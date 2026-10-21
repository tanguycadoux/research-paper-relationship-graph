"""
Books identified by ISBN: metadata from Crossref when it knows the ISBN (academic
books with a DOI), otherwise from Open Library.
"""

from django.db import transaction
from django.utils import timezone

from ..models import Publication
from .crossref_api import fetch_crossref_by_isbn
from .doi import normalize_doi
from .openlibrary_api import fetch_openlibrary_book
from .parser import parse_openlibrary, parse_publication


def find_or_import_book(isbn):
    """
    Return (publication, metadata_available) for a normalized ISBN. Stored metadata
    is never fetched again; otherwise Crossref is asked first, then Open Library.
    """
    pub = Publication.objects.filter(isbn=isbn).first()
    if pub and has_metadata(pub):
        return pub, True
    work = fetch_crossref_by_isbn(isbn)
    if work:
        return store_crossref_book(isbn, work), True
    pub = pub or Publication.objects.create(isbn=isbn)
    return pub, import_from_openlibrary(pub)


def has_metadata(pub):
    return pub.crossref_json is not None or pub.openlibrary_json is not None


@transaction.atomic
def store_crossref_book(isbn, work):
    """Store a book found in Crossref, on the publication of its DOI if it exists."""
    doi = normalize_doi(work["message"].get("DOI", ""))
    pub = (
        (doi and Publication.objects.filter(doi=doi).first())
        or Publication.objects.filter(isbn=isbn).first()
        or Publication(isbn=isbn)
    )
    pub.doi = pub.doi or doi
    pub.isbn = pub.isbn or isbn
    pub.crossref_json = work
    pub.crossref_fetched_at = timezone.now()
    pub.save()
    parse_publication(pub, parse_references=False)
    return pub


def import_from_openlibrary(pub):
    doc = fetch_openlibrary_book(pub.isbn)
    if doc is None:
        return False
    with transaction.atomic():
        pub.openlibrary_json = doc
        pub.openlibrary_fetched_at = timezone.now()
        pub.save(update_fields=["openlibrary_json", "openlibrary_fetched_at"])
        parse_openlibrary(pub)
    return True
