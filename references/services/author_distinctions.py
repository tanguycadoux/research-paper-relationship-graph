"""
Authors declared to be different people (AuthorDistinction): such a pair is never
suggested as duplicates. Decisions are shared by all users, like other corrections.
"""

from itertools import combinations

from django.db.models import Q

from ..models import AuthorDistinction


def ordered_pair(first_pk, second_pk):
    return (first_pk, second_pk) if first_pk < second_pk else (second_pk, first_pk)


def declare_distinct(authors, user):
    """Declare every pair of the given authors as different people."""
    pairs = {ordered_pair(a.pk, b.pk) for a, b in combinations(authors, 2)}
    AuthorDistinction.objects.bulk_create(
        [AuthorDistinction(first_id=a, second_id=b, declared_by=user) for a, b in pairs],
        ignore_conflicts=True,
    )


def distinct_pairs():
    """All declared pairs, as ordered (pk, pk) tuples."""
    return set(AuthorDistinction.objects.values_list("first_id", "second_id"))


def transfer_distinctions(kept, others):
    """
    Before merging others into kept: a distinction declared with one of them now
    applies to kept. A distinction between merged authors disappears.
    """
    other_pks = {author.pk for author in others}
    involved = AuthorDistinction.objects.filter(Q(first__in=other_pks) | Q(second__in=other_pks))
    transferred = []
    for distinction in involved:
        first, second = (
            kept.pk if pk in other_pks else pk
            for pk in (distinction.first_id, distinction.second_id)
        )
        if first != second:
            first, second = ordered_pair(first, second)
            transferred.append(
                AuthorDistinction(
                    first_id=first, second_id=second, declared_by_id=distinction.declared_by_id
                )
            )
    involved.delete()
    AuthorDistinction.objects.bulk_create(transferred, ignore_conflicts=True)
