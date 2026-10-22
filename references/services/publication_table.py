"""
What the table of publications shows beside each title, computed in the query
that lists them: first author, references to identify, missing metadata, references
not imported.
"""

from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Cast, Coalesce, Concat, Trim

from ..models import AuthorPublication, ExternalRecord, UserPublication
from .external_records import Source, with_metadata_status
from .identification import with_references_to_identify
from .metadata_formats import metadata_message


def for_publication_table(publications):
    return with_first_author(
        with_references_available(with_metadata_status(with_references_to_identify(publications)))
    )


def with_first_author(publications):
    """
    Annotate publications with first_author, the name in the first author slot, and
    author_count, their number of distinct authors: « Ada Lovelace et al. ».
    Subqueries, so that the counts of the other annotations are not multiplied.
    """
    slots = AuthorPublication.objects.filter(publication=OuterRef("pk"))
    first = (
        slots.order_by("order")
        .annotate(name=Trim(Concat("author__first_name", Value(" "), "author__last_name")))
        .values("name")[:1]
    )
    count = (
        slots.values("publication").annotate(count=Count("author", distinct=True)).values("count")
    )
    return publications.annotate(
        first_author=Subquery(first), author_count=Coalesce(Subquery(count), 0)
    )


def corpus_ids(user):
    """Ids of the publications of the user's corpus, for the add/remove buttons."""
    if not user.is_authenticated:
        return set()
    return set(UserPublication.objects.filter(user=user).values_list("publication_id", flat=True))


def with_references_available(publications):
    """
    Annotate publications with references_imported, the cited references stored,
    and references_available, the size of the bibliography in the stored Crossref
    answer (0 without one). The bibliography of a publication outside any corpus is
    not imported (#23): available but not imported.
    """
    crossref_count = (
        ExternalRecord.objects.filter(publication=OuterRef("pk"), source=Source.CROSSREF)
        .annotate(
            count=Cast(
                KeyTextTransform("reference-count", KeyTransform("message", "data")),
                IntegerField(),
            )
        )
        .values("count")[:1]
    )
    return publications.annotate(
        references_imported=Count("cited_references", distinct=True),
        references_available=Coalesce(Subquery(crossref_count), 0),
    )


def references_available(pub):
    """Size of the bibliography in the stored answer of the preferred source."""
    message = metadata_message(pub)
    return len(message.get("reference", [])) if message else 0
