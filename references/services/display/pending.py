"""
What waits for an action: counted in the navigation (#152), without cache so that a
count is right just after the action; the probable duplicates, costly, are cached
under a key that changes with the authors.
"""

from django.core.cache import cache
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Length

from ...models import Author, AuthorDistinction, CitedReference, MetadataConflict
from ..corrections import author_duplicates


def references_to_identify(user):
    """References of the user's corpus linked to no publication and not unidentifiable."""
    return CitedReference.objects.filter(
        source__userpublication__user=user, target__isnull=True, unidentifiable=False
    ).count()


def open_conflicts():
    return MetadataConflict.objects.filter(status=MetadataConflict.Status.OPEN).count()


def probable_duplicates():
    """
    Groups of probable duplicate authors, for everyone: the base is common (#270).
    Counted again only when the authors change: the key of the cache is a summary of
    them (how many, the last one, the length of their names, their ORCIDs, the pairs
    declared distinct), read in two light queries; counting takes 80 ms on 9 500
    authors, on every page of the navigation otherwise.
    """
    summary = Author.objects.aggregate(
        count=Count("pk"),
        last=Max("pk"),
        names=Sum(Length("first_name") + Length("last_name")),
        orcids=Count("pk", filter=~Q(orcid="")),
    )
    key = "probable-duplicates:{count}:{last}:{names}:{orcids}:{distinct}".format(
        **summary, distinct=AuthorDistinction.objects.count()
    )
    return cache.get_or_set(key, author_duplicates.duplicate_count, DUPLICATES_CACHE_SECONDS)


# The key changes with the authors: the time only bounds what is kept.
DUPLICATES_CACHE_SECONDS = 24 * 3600
