"""
Probable duplicates gathered on the coauthorship graphs (#419): « B. P. Abbott »,
« B P Abbott » and « B Abbott » are drawn as one node, their publications and links
added up. The groups are those of the page of probable duplicates (same family name,
compatible given names, never two different ORCIDs nor a pair declared distinct).
Nothing is written in the base: the grouping is only how the graph is drawn, and the
page can show the base as it is.
"""

from ...models import Author
from ..corrections.author_distinctions import distinct_pairs
from ..corrections.author_duplicates import by_family_name, compatible_groups


def probable_groups():
    """
    The groups of author_duplicates.duplicate_groups, as lists of author pks, the most
    complete name first. Without the publication counts and the shared organizations,
    which only order and explain the groups on their page: two light queries, 80 ms
    instead of 600 on 9 500 authors, like duplicate_count.
    """
    authors = Author.objects.only("pk", "first_name", "last_name", "orcid")
    declared_distinct = distinct_pairs()
    return [
        [author.pk for author in group]
        for same_family in by_family_name(authors).values()
        for group in compatible_groups(same_family, declared_distinct)
        if len(group) > 1
    ]


def graph_groups(people, groups, source_id=None):
    """
    {representative pk: [people]}, in the order of the people: the members of a probable
    group present in the graph gathered under its most complete name (or the author of
    the graph, if it is one of them), first of its list; any other person alone.
    """
    present = {person.pk for person in people}
    representative = {}
    for group in groups:
        members = [pk for pk in group if pk in present]
        if len(members) > 1:
            first = source_id if source_id in members else members[0]
            representative.update(dict.fromkeys(members, first))
    gathered = {}
    for person in people:
        gathered.setdefault(representative.get(person.pk, person.pk), []).append(person)
    for pk, members in gathered.items():
        members.sort(key=lambda person, pk=pk: person.pk != pk)
    return gathered


def gathered_publications(by_publication, gathered):
    """
    {publication id: set of node ids}: each author replaced by the node that gathers
    them. Two variants of one person on the same publication count once.
    """
    node_of = {
        person.pk: pk for pk, members in gathered.items() if len(members) > 1 for person in members
    }
    if not node_of:
        return by_publication
    return {
        publication_id: {node_of.get(author_id, author_id) for author_id in authors}
        for publication_id, authors in by_publication.items()
    }
