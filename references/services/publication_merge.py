"""
Merge of a publication without identifier into another publication: "this
publication is in fact that one".
"""

import re

from django.db import transaction
from django.utils import timezone

from ..models import CitedReference, Publication, UserPublication
from .books import find_or_import_book
from .doi import is_valid_doi, normalize_doi
from .importer import import_publication
from .isbn import is_valid_isbn, normalize_isbn
from .publication_moves import move_corpus_entries

PUBLICATION_URL = re.compile(r"/publications/(\d+)/?")


def can_be_merged(pub):
    """Only a publication without DOI nor ISBN can be merged into another one."""
    return not pub.doi and not pub.isbn


def find_merge_target(text):
    """
    Return the publication designated by a DOI, an ISBN or the URL of a publication
    page; None if nothing matches. A DOI or an ISBN absent from the database is
    imported; an existing publication is used as is, without any request.
    """
    text = text.strip()
    doi = normalize_doi(text)
    if is_valid_doi(doi):
        return Publication.objects.with_doi(doi).first() or import_new_doi(doi)
    isbn = normalize_isbn(text)
    if is_valid_isbn(isbn):
        return Publication.objects.filter(isbn=isbn).first() or find_or_import_book(isbn)[0]
    match = PUBLICATION_URL.search(text)
    return Publication.objects.filter(pk=match.group(1)).first() if match else None


def import_new_doi(doi):
    pub = Publication.objects.create(doi=doi)
    return import_publication(pub) or pub


def merge_summary(duplicate):
    """What a merge moves (citations, corpus entries) and loses (own data)."""
    return {
        "citations": CitedReference.objects.filter(target=duplicate).count(),
        "corpus_entries": UserPublication.objects.filter(publication=duplicate).count(),
        "own_references": CitedReference.objects.filter(source=duplicate).count(),
        "authors": duplicate.authorpublication_set.count(),
    }


@transaction.atomic
def merge_publication(duplicate, into, user):
    """
    Move the citations and corpus entries of duplicate to into, then delete it.
    Moved citations are marked as manual identifications, kept on re-import.
    """
    if duplicate == into or not can_be_merged(duplicate):
        raise ValueError("Only a publication without identifier can be merged into another.")
    CitedReference.objects.filter(target=duplicate).update(
        target=into, resolved_manually=True, resolved_by=user, resolved_at=timezone.now()
    )
    move_corpus_entries(duplicate, into)
    duplicate.delete()
