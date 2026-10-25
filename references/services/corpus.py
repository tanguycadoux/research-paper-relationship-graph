from ..models import UserPublication
from .importer import import_publication


def add_to_corpus(user, pub):
    """
    Add a publication to the corpus of a user and import it with its cited
    references. Return the publication imported (the published version of a
    preprint, maybe), or None if its metadata could not be retrieved.
    """
    UserPublication.objects.get_or_create(user=user, publication=pub)
    return import_publication(pub, with_references=True)
