from django.db.models import OuterRef, Subquery

from ..models import Publication, UserPublication
from .books import find_or_import_book
from .doi import is_valid_doi, normalize_doi
from .external_records import has_metadata
from .importer import import_publication
from .isbn import is_valid_isbn, normalize_isbn

TO_READ = UserPublication.ReadingStatus.TO_READ


def add_to_corpus(user, pub, status=""):
    """
    Add a publication to the corpus of a user, with a reading status, and import it
    with its cited references; « à lire », only its own metadata (#234). Return the
    publication imported (the published version of a preprint, maybe), or None if
    its metadata could not be retrieved.
    """
    entry = add_entry(user, pub, status)
    return import_publication(pub, with_references=entry.reading_status != TO_READ)


def add_entry(user, pub, status):
    """The entry of pub in the corpus of user; the status is only given to a new one."""
    return UserPublication.objects.get_or_create(
        user=user, publication=pub, defaults={"reading_status": status}
    )[0]


def add_book(user, pub, status=""):
    """A book without DOI is never sent to the DOI sources: only its stored data is used."""
    if has_metadata(pub):
        return add_to_corpus(user, pub, status)
    add_entry(user, pub, status)
    return None


def add_identified(user, pub, status=""):
    """Add a publication found by find_or_create; return as add_to_corpus."""
    return add_to_corpus(user, pub, status) if pub.doi else add_book(user, pub, status)


def change_reading_status(entry, status):
    """
    Change the reading status of a corpus entry. Leaving « à lire » imports the
    cited references, left aside until then (#234): return the publication imported,
    or None if its metadata could not be retrieved; False when nothing was imported
    (a book without DOI has no bibliography in the sources).
    """
    leaves_to_read = entry.reading_status == TO_READ and status != TO_READ
    entry.reading_status = status
    entry.save(update_fields=["reading_status"])
    if not leaves_to_read or not entry.publication.doi:
        return False
    return import_publication(entry.publication, with_references=True)


def find_or_create(doi="", isbn=""):
    """
    The publication of a raw DOI, else of a raw ISBN (looked up in Crossref, then
    Open Library); None without a valid identifier.
    """
    doi = normalize_doi(str(doi or ""))
    if is_valid_doi(doi):
        return Publication.objects.get_or_create_doi(doi)
    isbn = normalize_isbn(str(isbn or ""))
    if is_valid_isbn(isbn):
        return Publication.objects.filter(isbn=isbn).first() or find_or_import_book(isbn)[0]
    return None


def with_reading_status(publications, user):
    """
    Annotate publications with reading_status, the one the user chose ("" without),
    from a subquery: filtering on userpublication__ again would join the entries of
    every user.
    """
    entries = UserPublication.objects.filter(user=user, publication=OuterRef("pk"))
    return publications.annotate(reading_status=Subquery(entries.values("reading_status")[:1]))
