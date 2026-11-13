from django.core.management.base import BaseCommand

from references.services.imports.enrichment import complete_existing_publications
from references.services.sources.http import patient_requests


class Command(BaseCommand):
    help = (
        "Rattache les affiliations (et la hiérarchie des organisations) des publications "
        "déjà en base, à partir des données OpenAlex stockées. Une publication sans auteur "
        "reprend ceux d'OpenAlex, et les conflits d'auteurs qui ne tiennent plus sont fermés."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fetch-missing",
            action="store_true",
            help="Interroger d'abord OpenAlex (par lots de 50) pour les publications avec DOI "
            "qui n'ont pas encore de réponse OpenAlex.",
        )
        parser.add_argument(
            "--refresh-ancestors",
            action="store_true",
            help="Redemander à OpenAlex (par lots de 50) les organisations ancêtres déjà "
            "connues, pour réparer leurs propres ancêtres.",
        )

    def handle(self, *args, **options):
        # A command can wait as long as OpenAlex asks: nobody is waiting for a page.
        with patient_requests():
            summary = complete_existing_publications(
                fetch_missing=options["fetch_missing"],
                refresh_ancestors=options["refresh_ancestors"],
            )
        if options["fetch_missing"]:
            self.stdout.write(f"Publications demandées à OpenAlex : {summary['fetched']}")
        self.stdout.write(f"Publications avec une réponse OpenAlex : {summary['with_openalex']}")
        self.stdout.write(
            f"Publications sans auteur complétées par OpenAlex : {summary['with_new_authors']}"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Publications dont les affiliations sont rattachées : {summary['attached']}"
            )
        )
