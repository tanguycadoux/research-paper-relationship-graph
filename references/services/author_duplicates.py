"""
Suggestion of probable duplicate authors: same family name, compatible given
names ('A.' / 'Ada', 'J.-L.' / 'Jean Luc'), never two different ORCIDs.
"""

import re
import unicodedata
from collections import defaultdict

from django.db.models import Count

from ..models import Author
from .author_distinctions import distinct_pairs, ordered_pair

NAME_PARTS = re.compile(r"[^\w]+")


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
            families[normalized(author.last_name)].append(author)
    return families


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
    if first.orcid and second.orcid and first.orcid != second.orcid:
        return False
    return compatible_given_names(first.first_name, second.first_name)


def compatible_given_names(first, second):
    """Word by word: equal, or an initial matching the first letter of the other."""
    pairs = zip(name_parts(first), name_parts(second), strict=False)
    return all(a == b or (min(len(a), len(b)) == 1 and a[0] == b[0]) for a, b in pairs)


def name_parts(name):
    return [part for part in NAME_PARTS.split(normalized(name)) if part]


def normalized(text):
    """Lower case, without accents."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def group_priority(group):
    """Exactly one ORCID first (the most useful merges), then the largest groups."""
    orcids = {author.orcid for author in group if author.orcid}
    return (len(orcids) != 1, -len(group), normalized(group[0].last_name))
