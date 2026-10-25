"""
Contradictions between sources (MetadataConflict): the known value is kept and
the conflict is reported, to be decided on the « Conflits » page.
"""

from dataclasses import dataclass

from django.utils import timezone

from ..models import MetadataConflict
from .names import name_parts, same_words_up_to_initials

Kind = MetadataConflict.Kind
Status = MetadataConflict.Status
MAX_LISTED_NAMES = 15


def report_conflict(
    kind, *, field, current, proposed, source, publication=None, author=None, details=None
):
    """
    Report a conflict once: the same (object, field, proposed value) is never
    reported again, even after a decision, so that re-imports do not reopen it.
    """
    conflict, _ = MetadataConflict.objects.get_or_create(
        kind=kind,
        publication=publication,
        author=author,
        field=field,
        proposed_value=proposed,
        defaults={"current_value": current, "source": source, "details": details or {}},
    )
    return conflict


def close_obsolete(kind, *, publication=None, author=None):
    """The sources agree again: open conflicts of this kind no longer apply."""
    MetadataConflict.objects.filter(
        kind=kind, publication=publication, author=author, status=Status.OPEN
    ).delete()


def resolve(conflict, status, user):
    """Record a decision. An informative conflict can only be marked as seen."""
    allowed = {Status.SEEN} if conflict.is_informative else {Status.KEPT, Status.ACCEPTED}
    if status not in allowed:
        raise ValueError(f"Decision {status} is not possible for this conflict.")
    conflict.status = status
    conflict.resolved_by = user
    conflict.resolved_at = timezone.now()
    conflict.save(update_fields=["status", "resolved_by", "resolved_at"])
    if status == Status.ACCEPTED:
        apply_proposed_value(conflict)


def apply_proposed_value(conflict):
    """The proposed value replaces the known one."""
    if conflict.kind == Kind.ORCID:
        conflict.author.orcid = conflict.proposed_value
        conflict.author.save(update_fields=["orcid"])
    elif conflict.kind == Kind.ORCID_NAME:
        name = split_name(conflict.proposed_value)
        conflict.author.first_name, conflict.author.last_name = name.given, name.family
        conflict.author.save(update_fields=["first_name", "last_name"])


@dataclass(frozen=True)
class PersonName:
    given: str
    family: str

    def __str__(self):
        return f"{self.given} {self.family}".strip()


def split_name(value):
    """A name stored « Family, Given » in an ORCID_NAME conflict."""
    family, _, given = value.partition(", ")
    return PersonName(given, family)


@dataclass(frozen=True)
class NameComparison:
    current: PersonName
    proposed: PersonName
    # Same words, split differently between given and family name (#244).
    split_differently: bool


def compare_names(conflict):
    """The two names of an ORCID_NAME conflict, given name first."""
    current, proposed = split_name(conflict.current_value), split_name(conflict.proposed_value)
    return NameComparison(
        current,
        proposed,
        split_differently=same_words_up_to_initials(str(current), str(proposed))
        and name_parts(current.family) != name_parts(proposed.family),
    )


def names_summary(names):
    """'3 auteurs : A; B; C', truncated for very long author lists."""
    listed = "; ".join(names[:MAX_LISTED_NAMES])
    more = " ; …" if len(names) > MAX_LISTED_NAMES else ""
    return f"{len(names)} auteur{'s' if len(names) > 1 else ''} : {listed}{more}"
