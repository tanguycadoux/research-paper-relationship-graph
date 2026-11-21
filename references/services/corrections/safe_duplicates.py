"""
Safe groups of probable duplicates (#374), merged together after one confirmation.
The criterion is strict, since two authors with the same name can be namesakes: the
same names up to punctuation, case and accents ('B. P. Abbott' / 'B P Abbott'), no
two ORCIDs, no pair declared different people, no two of them on the same
publication, and every author tied to the others by a shared coauthor or a shared
top-level organization.
"""

from collections import defaultdict
from itertools import combinations

from django.db import transaction

from ...models import Author, AuthorPublication
from ..identifiers.names import name_parts
from ..imports.orcid_merge import merge_same_orcid
from .author_distinctions import distinct_pairs, ordered_pair
from .author_duplicates import top_level_organizations
from .author_merge import candidate_values, default_values, merge_authors


def safe_groups(groups):
    """
    The safe groups among groups (those of duplicate_groups), in the same order. Each
    one gets its key (the pks of its authors), the values the merge will give it
    (merged_values) and whether a coauthor ties its authors (shared_coauthor).
    """
    declared = distinct_pairs()
    candidates = [g for g in groups if same_names(g) and not contradicted(g, declared)]
    pks = {author.pk for group in candidates for author in group}
    ties = Ties(top_level_organizations(pks), signatures(pks))
    safe = [group for group in candidates if ties.join(group)]
    for group in safe:
        group.key = group_key(group)
        group.merged_values = default_values(candidate_values(sorted(group, key=by_pk)))
        group.shared_coauthor = any(ties.coauthor(a, b) for a, b in combinations(group, 2))
    return safe


def group_key(group):
    """'3,8': the pks of the authors, what the confirmation sends back."""
    return ",".join(str(pk) for pk in sorted(author.pk for author in group))


def same_names(group):
    """Given and family names equal word by word, once normalized."""
    names = {(tuple(name_parts(a.first_name)), tuple(name_parts(a.last_name))) for a in group}
    return len(names) == 1


def contradicted(group, declared):
    """Two different ORCIDs, or a pair declared different people."""
    orcids = {author.orcid for author in group if author.orcid}
    pairs = {ordered_pair(a.pk, b.pk) for a, b in combinations(group, 2)}
    return len(orcids) > 1 or bool(pairs & declared)


def signatures(author_pks):
    """
    ({author pk: its publications}, {publication: the pks of its signers}), in two
    queries. Signers rather than each author's coauthors: the union for a few hundred
    authors of large collaborations held 2 million pks.
    """
    slots = AuthorPublication.objects.filter(author_id__in=author_pks)
    publications = defaultdict(set)
    for author_id, publication_id in slots.values_list("author_id", "publication_id"):
        publications[author_id].add(publication_id)
    signers = defaultdict(set)
    rows = AuthorPublication.objects.filter(publication_id__in=slots.values("publication_id"))
    for publication_id, author_id in rows.values_list("publication_id", "author_id"):
        signers[publication_id].add(author_id)
    return publications, signers


class Ties:
    """What ties two authors of a group: a shared coauthor or top-level organization."""

    def __init__(self, organizations, signatures):
        self.organizations = organizations
        self.publications, self.signers = signatures

    def same_publication(self, first, second):
        return not self.publications[first.pk].isdisjoint(self.publications[second.pk])

    def coauthor(self, first, second):
        """
        A signer of a publication of each: neither of them, unless they sign the same
        publication, which join excludes first.
        """
        return any(
            not self.signers[mine].isdisjoint(self.signers[theirs])
            for mine in self.publications[first.pk]
            for theirs in self.publications[second.pk]
        )

    def tied(self, first, second):
        return self.coauthor(first, second) or bool(
            self.organizations[first.pk] & self.organizations[second.pk]
        )

    def join(self, group):
        """
        No two authors of the group sign the same publication (two people, or an
        author list to look at by hand), and the ties reach all of them: an author
        tied to none of the others is never merged.
        """
        if any(self.same_publication(a, b) for a, b in combinations(group, 2)):
            return False
        reached, frontier = {group[0].pk}, [group[0]]
        while frontier:
            author = frontier.pop()
            for other in group:
                if other.pk not in reached and self.tied(author, other):
                    reached.add(other.pk)
                    frontier.append(other)
        return len(reached) == len(group)


def by_pk(author):
    return author.pk


@transaction.atomic
def merge_safe_groups(groups, user):
    """
    Merge each group into its oldest author, as the confirmation of one group does:
    the most complete names, the trace (AuthorMerge), then the other holders of the
    ORCID. All or nothing. Return the groups merged: a group whose author has gone
    meanwhile, merged with the holders of an ORCID, is left aside.
    """
    merged = []
    for group in groups:
        authors = list(Author.objects.filter(pk__in=[a.pk for a in group]).order_by("pk"))
        if len(authors) < len(group):
            continue
        kept = authors[0]
        merge_authors(kept, authors[1:], default_values(candidate_values(authors)), user=user)
        merge_same_orcid(kept, user=user)
        merged.append(group)
    return merged
