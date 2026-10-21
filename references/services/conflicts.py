"""
Contradictions between sources (MetadataConflict): the known value is kept and
the conflict is reported, to be decided on the « Conflits » page.
"""

from django.utils import timezone

from ..models import MetadataConflict

Kind = MetadataConflict.Kind
Status = MetadataConflict.Status
MAX_LISTED_NAMES = 15


def report_conflict(kind, *, field, current, proposed, source, publication=None, author=None):
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
        defaults={"current_value": current, "source": source},
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


def names_summary(names):
    """'3 auteurs : A; B; C', truncated for very long author lists."""
    listed = "; ".join(names[:MAX_LISTED_NAMES])
    more = " ; …" if len(names) > MAX_LISTED_NAMES else ""
    return f"{len(names)} auteur{'s' if len(names) > 1 else ''} : {listed}{more}"
