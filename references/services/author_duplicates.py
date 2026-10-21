"""
Suggestion of probable duplicate authors: same family name, compatible given
names ('A.' / 'Ada', 'J.-L.' / 'Jean Luc'), never two different ORCIDs.
"""

from collections import defaultdict

from django.db.models import Count

from ..models import Author
from .author_distinctions import distinct_pairs, ordered_pair
from .names import name_parts, normalized


def duplicate_groups():
    """Groups of at least two probable duplicates, the most likely first."""
    authors = Author.objects.annotate(publication_count=Count("publications", distinct=True))
    declared_distinct = distinct_pairs()
    groups = [
        group
        for same_family in by_family_name(authors).values()
        for group in compatible_groups(same_family, declared_distinct)
        if len(group) > 1
    ]
    return sorted(groups, key=group_priority)


def by_family_name(authors):
    families = defaultdict(list)
    for author in authors:
        if author.last_name and author.first_name:
            families[family_key(author.last_name)].append(author)
    return families


def family_key(last_name):
    """'Correia-Machado' and 'Correia Machado' share the same key."""
    return " ".join(name_parts(last_name))


def compatible_groups(authors, declared_distinct=frozenset()):
    """
    Put each author in the first group whose members are all compatible with it.
    Authors with an ORCID and complete names come first, so that groups form
    around them.
    """
    groups = []
    for author in sorted(authors, key=lambda a: (not a.orcid, -len(a.first_name), a.pk)):
        group = next(
            (g for g in groups if all(compatible(author, m, declared_distinct) for m in g)), None
        )
        if group is None:
            groups.append([author])
        else:
            group.append(author)
    return groups


def compatible(first, second, declared_distinct=frozenset()):
    if ordered_pair(first.pk, second.pk) in declared_distinct:
        return False
    if first.orcid and second.orcid:
        # The same ORCID is the same person, whatever the spelling of the names.
        return first.orcid == second.orcid
    return compatible_given_names(first.first_name, second.first_name)


def compatible_given_names(first, second):
    """Word by word: equal, or an initial matching the first letter of the other."""
    pairs = zip(name_parts(first), name_parts(second), strict=False)
    return all(a == b or (min(len(a), len(b)) == 1 and a[0] == b[0]) for a, b in pairs)


def group_priority(group):
    """Exactly one ORCID first (the most useful merges), then the largest groups."""
    orcids = {author.orcid for author in group if author.orcid}
    return (len(orcids) != 1, -len(group), normalized(group[0].last_name))
