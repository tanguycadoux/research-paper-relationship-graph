"""
Books identified by ISBN: metadata from Crossref when it knows the ISBN (academic
books with a DOI), otherwise from Open Library.
"""

from django.db import transaction

from ...models import CitedReference, Publication
from ..corrections.publication_moves import move_corpus_entries
from ..identifiers.doi import normalize_doi
from ..sources.crossref_api import fetch_crossref_by_isbn
from ..sources.external_records import Source, has_metadata, store_record
from ..sources.openlibrary_api import fetch_openlibrary_book
from .parser import parse_publication


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
    pub.save()
    store_record(pub, Source.CROSSREF, work)
    parse_publication(pub, parse_references=False)
    return pub


def import_queued_book(pub):
    """
    find_or_import_book for a publication created with its ISBN alone, whose metadata
    was left to the queue (#378). If Crossref gives the DOI of another publication, that
    one takes its place: citations and corpus entries move to it. Return the publication
    that holds the book, or None if neither Crossref nor Open Library knows it.
    """
    if has_metadata(pub):
        return pub
    work = fetch_crossref_by_isbn(pub.isbn)
    if work is None:
        return pub if import_from_openlibrary(pub) else None
    doi = normalize_doi(work["message"].get("DOI", ""))
    holder = doi and Publication.objects.filter(doi=doi).exclude(pk=pub.pk).first()
    if holder:
        replace_placeholder(pub, holder)
    return store_crossref_book(pub.isbn, work)


@transaction.atomic
def replace_placeholder(placeholder, holder):
    CitedReference.objects.filter(target=placeholder).update(target=holder)
    move_corpus_entries(placeholder, holder)
    placeholder.delete()


def import_book_metadata(pub):
    """
    Fetch the metadata of an existing publication from its ISBN: Crossref first, then
    Open Library. Return False if neither knows it.
    """
    work = fetch_crossref_by_isbn(pub.isbn)
    if work is None:
        return import_from_openlibrary(pub)
    doi = normalize_doi(work["message"].get("DOI", ""))
    with transaction.atomic():
        # The DOI is taken only if no other publication holds it (else: a duplicate,
        # to merge by hand).
        if doi and not pub.doi and not Publication.objects.filter(doi=doi).exists():
            pub.doi = doi
            pub.save()
        store_record(pub, Source.CROSSREF, work)
        parse_publication(pub, parse_references=False)
    return True


def import_from_openlibrary(pub):
    doc = fetch_openlibrary_book(pub.isbn)
    if doc is None:
        return False
    with transaction.atomic():
        store_record(pub, Source.OPENLIBRARY, doc)
        parse_publication(pub, parse_references=False)
    return True
