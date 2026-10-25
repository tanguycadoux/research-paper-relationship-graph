"""
ORCIDs missing from Crossref, completed from OpenAlex for the authors already
matched by position and published name. The canonical author receives the ORCID
when it has none; a different ORCID is never overwritten but reported as a
conflict. The published ORCID of the signature (Crossref data) is left untouched.
An ORCID already held by another author merges them (#158).
"""

from ..models import Author
from .conflicts import Kind, report_conflict
from .external_records import Source
from .orcid import normalize_orcid
from .orcid_merge import merge_same_orcid


def complete_orcids(slots, authorships):
    """Return the number of authors who received an ORCID."""
    # One instance per author: after a merge, an author can hold several slots.
    authors = {}
    completed = {}
    for slot, authorship in zip(slots, authorships, strict=True):
        author = authors.setdefault(slot.author_id, slot.author)
        orcid = normalize_orcid((authorship.get("author") or {}).get("orcid") or "")
        if orcid and complete_orcid(author, orcid):
            completed[author.pk] = author
    Author.objects.bulk_update(completed.values(), ["orcid"])
    for author in completed.values():
        merge_same_orcid(author, source=Source.OPENALEX)
    return len(completed)


def complete_orcid(author, orcid):
    """Give author the ORCID if it has none; report a conflict if it has another."""
    if not author.orcid:
        author.orcid = orcid
        return True
    if author.orcid != orcid:
        report_conflict(
            Kind.ORCID,
            author=author,
            field="orcid",
            current=author.orcid,
            proposed=orcid,
            source=Source.OPENALEX,
        )
    return False
