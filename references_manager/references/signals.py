from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Publication
from .services.importer import import_publication


@receiver(post_save, sender=Publication)
def auto_import_on_create(sender, instance, created, **kwargs):
    """
    Lorsque qu’une Publication est créée et qu’elle possède un DOI,
    on déclenche automatiquement le pipeline d'import.
    """
    if created and instance.doi:
        if instance.reference_level == 0:
            import_publication(instance, parse_references=True)
        else:
            import_publication(instance, parse_references=False)
