"""
Resolution of published author names (given, family, ORCID) to canonical authors.

Rules, in order: same ORCID, then a previous resolution of the same published name
(which keeps manual merges), then the same canonical name, else a new author.
Lookups are grouped: a constant number of queries whatever the number of names.
"""

from ..models import Author, AuthorPublication


def resolve_authors(names):
    """Return the canonical Author of each (given, family, orcid), creating the missing ones."""
    known = KnownAuthors(names)
    new_authors = {}
    resolved = [known.find(name) or new_author(name, new_authors) for name in names]
    Author.objects.bulk_create(list(new_authors.values()))
    return resolved


def new_author(name, new_authors):
    """Create (unsaved) at most one author per ORCID, or per name without ORCID."""
    given, family, orcid = name
    key = ("orcid", orcid) if orcid else ("name", name)
    if key not in new_authors:
        new_authors[key] = Author(first_name=given, last_name=family, orcid=orcid)
    return new_authors[key]


class KnownAuthors:
    """Existing authors matching a set of published names, loaded in three queries."""

    def __init__(self, names):
        families = {family for _, family, _ in names}
        orcids = {orcid for _, _, orcid in names if orcid}
        self.by_orcid = first_by_key(
            Author.objects.filter(orcid__in=orcids).order_by("pk"), lambda a: a.orcid
        )
        self.by_published_name = first_by_key(
            AuthorPublication.objects.filter(published_family_name__in=families)
            .select_related("author")
            .order_by("pk"),
            lambda slot: (
                slot.published_given_name,
                slot.published_family_name,
                slot.published_orcid,
            ),
        )
        self.by_canonical_name = first_by_key(
            Author.objects.filter(last_name__in=families).order_by("pk"),
            lambda a: (a.first_name, a.last_name, a.orcid),
        )

    def find(self, name):
        orcid = name[2]
        if orcid and orcid in self.by_orcid:
            return self.by_orcid[orcid]
        if name in self.by_published_name:
            return self.by_published_name[name].author
        return self.by_canonical_name.get(name)


def first_by_key(objects, key):
    result = {}
    for obj in objects:
        result.setdefault(key(obj), obj)
    return result
