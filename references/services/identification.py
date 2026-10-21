"""
Manual identification of a cited reference: the user tells which publication it is.
"""

import datetime

from django.db import transaction
from django.utils import timezone

from ..models import Publication
from .books import find_or_import_book
from .importer import import_publication


def identify_by_doi(ref, doi, user):
    """
    Link the reference to the publication of a DOI, creating and importing it if
    needed. Return (publication, metadata_available).
    """
    pub, _ = Publication.objects.get_or_create(doi=doi)
    imported = import_publication(pub)
    resolve(ref, pub, user)
    return pub, imported


def identify_by_isbn(ref, isbn, user):
    """
    Link the reference to the book of an ISBN (Crossref, then Open Library).
    Return (publication, metadata_available).
    """
    pub, imported = find_or_import_book(isbn)
    resolve(ref, pub, user)
    return pub, imported


def identify_without_identifier(ref, title, year, user):
    """Create a publication without identifier from the reference, and link it."""
    with transaction.atomic():
        pub = Publication.objects.create(title=title, publication_date=year_to_date(year))
        resolve(ref, pub, user)
    return pub


def resolve(ref, pub, user):
    ref.target = pub
    ref.resolved_manually = True
    ref.resolved_by = user
    ref.resolved_at = timezone.now()
    ref.save(update_fields=["target", "resolved_manually", "resolved_by", "resolved_at"])


def year_to_date(year):
    return datetime.date(year, 1, 1) if year else None


def suggested_title(ref):
    raw = ref.raw
    return raw.get("article-title") or raw.get("volume-title") or raw.get("series-title") or ""


def suggested_year(ref):
    year = str(ref.raw.get("year", ""))[:4]
    return int(year) if year.isdigit() else None
