from django.core.management.base import BaseCommand

from references.models import Publication
from references.services.importer import import_publication
from references.services.preprints import ARXIV_PREFIX, datacite_data, declared_version


class Command(BaseCommand):
    help = (
        "Remplace les prépublications arXiv déjà en base par la version publiée que "
        "déclarent leurs auteurs (#227) : un appel à Crossref par prépublication concernée, "
        "aucun à DataCite (sa réponse est déjà stockée)."
    )

    def handle(self, *args, **options):
        replaced = 0
        for pub in Publication.objects.filter(doi__startswith=ARXIV_PREFIX):
            if declared_version(datacite_data(pub)) is None:
                continue
            arxiv_doi = pub.doi
            result = import_publication(pub, with_references=pub.parse_references)
            if result and result.doi != arxiv_doi:
                replaced += 1
                self.stdout.write(f"{arxiv_doi} → {result.doi} « {result} »")
        self.stdout.write(self.style.SUCCESS(f"Prépublications remplacées : {replaced}"))
