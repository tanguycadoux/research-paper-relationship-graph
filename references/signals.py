from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Publication
from .services.importer import import_publication


@receiver(post_save, sender=Publication)
def auto_import_on_create(sender, instance, created, **kwargs):
    """
    Import Crossref metadata when a publication is created with a DOI.
    """
    if created and instance.doi:
        import_publication(instance, parse_references=instance.parse_references)
