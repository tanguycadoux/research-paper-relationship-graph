"""
What waits for an action: counted in the navigation (#152), without cache so that a
count is right just after the action.
"""

from ..models import CitedReference, MetadataConflict


def references_to_identify(user):
    """References of the user's corpus linked to no publication and not unidentifiable."""
    return CitedReference.objects.filter(
        source__userpublication__user=user, target__isnull=True, unidentifiable=False
    ).count()


def open_conflicts():
    return MetadataConflict.objects.filter(status=MetadataConflict.Status.OPEN).count()
