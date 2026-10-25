"""
Manual identification of a cited reference: the user tells which publication it is.
"""

import datetime

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from ..models import Publication
from .books import find_or_import_book
from .external_records import has_metadata
from .importer import import_publication


def with_references_to_identify(publications):
    """
    Annotate publications with to_identify, their number of cited references linked
    to no publication and not declared unidentifiable: one query for the whole list.
    """
    return publications.annotate(
        to_identify=Count(
            "cited_references",
            filter=Q(
                cited_references__target__isnull=True,
                cited_references__unidentifiable=False,
            ),
        )
    )


def is_to_identify(ref):
    return ref.target_id is None and not ref.unidentifiable


def identify_by_doi(ref, doi, user):
    """
    Link the reference to the publication of a DOI, creating and importing it if
    needed. Return (publication, metadata_available).
    """
    pub = Publication.objects.get_or_create_doi(doi)
    imported = import_publication(pub)
    pub = imported or pub
    resolve(ref, pub, user)
    return pub, bool(imported)


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
        pub = Publication.objects.create(
            title=title,
            publication_date=year_to_date(year),
            publication_date_precision=Publication.DatePrecision.YEAR,
        )
        resolve(ref, pub, user)
    return pub


def resolve(ref, pub, user):
    record_decision(ref, pub, user, unidentifiable=False)


def declare_unidentifiable(ref, user):
    """The reference matches no importable publication: unlink it, keep the decision."""
    record_decision(ref, None, user, unidentifiable=True)


def cancel_unidentifiable(ref):
    """Back to a reference to identify, as given by the sources."""
    ref.unidentifiable = False
    ref.resolved_manually = False
    ref.resolved_by = None
    ref.resolved_at = None
    ref.save(update_fields=DECISION_FIELDS)


DECISION_FIELDS = ["target", "unidentifiable", "resolved_manually", "resolved_by", "resolved_at"]


def record_decision(ref, pub, user, unidentifiable):
    previous = ref.target
    ref.target = pub
    ref.unidentifiable = unidentifiable
    ref.resolved_manually = True
    ref.resolved_by = user
    ref.resolved_at = timezone.now()
    ref.save(update_fields=DECISION_FIELDS)
    if previous is not None and previous != pub:
        delete_if_orphan(previous)


def delete_if_orphan(pub):
    """
    Delete a publication left behind by a new identification, when nobody uses it:
    cited by no reference, in no corpus, and without any metadata.
    """
    used = pub.citations.exists() or pub.userpublication_set.exists() or has_metadata(pub)
    if not used:
        pub.delete()


def year_to_date(year):
    return datetime.date(year, 1, 1) if year else None


def suggested_title(ref):
    raw = ref.raw
    return raw.get("article-title") or raw.get("volume-title") or raw.get("series-title") or ""


def suggested_year(ref):
    year = str(ref.raw.get("year", ""))[:4]
    return int(year) if year.isdigit() else None
