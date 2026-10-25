"""What points to a publication, moved to another one before it is deleted (merges)."""

from ..models import UserPublication


def move_corpus_entries(duplicate, into):
    """Corpus entries of duplicate go to into, except for users who already have it."""
    users_of_target = UserPublication.objects.filter(publication=into).values("user_id")
    UserPublication.objects.filter(publication=duplicate).exclude(
        user_id__in=users_of_target
    ).update(publication=into)
