"""
Automatic merge of the authors who hold the same ORCID (#158): an ORCID designates
one person, so they are certain duplicates. The oldest author is kept, with the
most complete names, as in a manual merge. Authors declared to be different people
are never merged: the shared ORCID is reported as a conflict instead.
"""

from itertools import combinations

from django.db.models import Count

from ..models import Author, AuthorMerge
from .author_distinctions import distinct_pairs, ordered_pair
from .author_merge import candidate_values, default_values, merge_authors
from .conflicts import Kind, report_conflict


def merge_same_orcid(author, *, user=None, source=""):
    """
    Merge the other holders of the ORCID of author into the oldest one. Return the
    author that remains: author itself when there is nothing to merge.
    """
    if not author.orcid:
        return author
    holders = list(Author.objects.filter(orcid=author.orcid).order_by("pk"))
    if len(holders) < 2:
        return author
    if declared_distinct(holders):
        report_shared_orcid(author, holders, source)
        return author
    kept, others = holders[0], holders[1:]
    values = {**default_values(candidate_values(holders)), "orcid": author.orcid}
    merge_authors(kept, others, values, reason=AuthorMerge.Reason.ORCID, user=user)
    return kept


def merge_all_same_orcid():
    """
    Merge the holders of every ORCID held more than once (authors already in the
    base). Return {"merged": ORCIDs merged, "conflicts": ORCIDs left shared}.
    """
    orcids = list(shared_orcids(Author.objects.exclude(orcid="")))
    for orcid in orcids:
        merge_same_orcid(Author.objects.filter(orcid=orcid).order_by("pk").first())
    still_shared = shared_orcids(Author.objects.filter(orcid__in=orcids)).count()
    return {"merged": len(orcids) - still_shared, "conflicts": still_shared}


def shared_orcids(authors):
    """ORCIDs held by more than one of the authors."""
    return (
        authors.values("orcid")
        .annotate(holders=Count("pk"))
        .filter(holders__gt=1)
        .values_list("orcid", flat=True)
    )


def declared_distinct(authors):
    pairs = distinct_pairs()
    return any(ordered_pair(a.pk, b.pk) in pairs for a, b in combinations(authors, 2))


def report_shared_orcid(author, holders, source):
    others = "; ".join(str(holder) for holder in holders if holder.pk != author.pk)
    report_conflict(
        Kind.SHARED_ORCID,
        author=author,
        field="orcid",
        current=author.orcid,
        proposed=others,
        source=source,
    )
