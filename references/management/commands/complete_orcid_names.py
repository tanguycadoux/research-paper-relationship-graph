from django.core.management.base import BaseCommand

from references.models import Author
from references.services.http import patient_requests
from references.services.orcid_names import complete_names


class Command(BaseCommand):
    help = (
        "Complète les noms des auteurs depuis ORCID (recherche groupée, par lots de 50), "
        "pour les auteurs avec ORCID dont le nom n'a pas encore été demandé."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Redemander aussi les ORCID déjà demandés.",
        )

    def handle(self, *args, **options):
        authors = Author.objects.exclude(orcid="")
        # A command can wait as long as ORCID asks: nobody is waiting for a page.
        with patient_requests():
            completed = complete_names(authors, refresh=options["refresh"])
        self.stdout.write(self.style.SUCCESS(f"Noms complétés depuis ORCID : {completed}"))
