"""
Merge of several authors into one: candidate values for each field, sensible
defaults, and the merge itself.
"""

import re

from django.db import transaction

from ..models import AuthorMerge
from .author_distinctions import transfer_distinctions

MERGE_FIELDS = ("first_name", "last_name", "orcid")
NAME_SEPARATORS = re.compile(r"[\s\-]+")
INITIAL = re.compile(r"^\w\.?$")


def candidate_values(authors):
    """{field: distinct non-empty values of the authors}, in the order of the authors."""
    return {
        field: list(dict.fromkeys(getattr(a, field) for a in authors if getattr(a, field)))
        for field in MERGE_FIELDS
    }


def default_values(candidates):
    """The most complete names ('Ada' rather than 'A.'), and the ORCID if any."""
    return {
        "first_name": most_complete_name(candidates["first_name"]),
        "last_name": most_complete_name(candidates["last_name"]),
        "orcid": next(iter(candidates["orcid"]), ""),
    }


def most_complete_name(names):
    """Prefer names without initials, then not all in capitals, then the longest one."""
    return max(
        names, key=lambda name: (not has_initial(name), not name.isupper(), len(name)), default=""
    )


def has_initial(name):
    return any(INITIAL.match(part) for part in NAME_SEPARATORS.split(name) if part)


def has_orcid_conflict(candidates):
    """Two different ORCIDs usually mean two different people."""
    return len(candidates["orcid"]) > 1


@transaction.atomic
def merge_authors(kept, others, values, *, reason=AuthorMerge.Reason.MANUAL, user=None):
    """
    Give kept the chosen values and move the publications of the others to it. The
    merge is traced, and the merges of the others now belong to kept.
    """
    AuthorMerge.objects.create(
        kept=kept,
        absorbed=[{field: getattr(other, field) for field in MERGE_FIELDS} for other in others],
        reason=reason,
        merged_by=user,
    )
    AuthorMerge.objects.filter(kept__in=others).update(kept=kept)
    for field in MERGE_FIELDS:
        setattr(kept, field, values[field])
    kept.save()
    transfer_distinctions(kept, others)
    kept.merge_with(others)
