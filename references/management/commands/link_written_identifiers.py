from django.core.management.base import BaseCommand

from references.services.imports.written_identifiers import link_references, references_to_link
from references.services.sources.http import patient_requests


class Command(BaseCommand):
    help = (
        "Relie les références à identifier qui écrivent un code JACoW ou un identifiant "
        "arXiv, dans les bibliographies déjà importées, une fois que DataCite confirme le "
        "DOI et le titre (une requête DataCite par lot de DOI inconnus de la base)."
    )

    def handle(self, *args, **options):
        # A command can wait as long as DataCite asks: nobody is waiting for a page.
        with patient_requests():
            report = link_references(references_to_link())
        self.stdout.write(f"Références qui écrivent un identifiant : {report.found}")
        self.stdout.write(
            self.style.SUCCESS(f"Références reliées à leur publication : {report.linked}")
        )
        self.stdout.write(
            f"Prépublications remplacées par leur version publiée : {report.replaced}"
        )
