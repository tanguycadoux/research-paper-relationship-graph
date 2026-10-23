from django.core.management.base import BaseCommand

from references.services.orcid_merge import merge_all_same_orcid


class Command(BaseCommand):
    help = (
        "Fusionne les auteurs déjà en base qui portent le même ORCID. Ceux déclarés "
        "distincts ne sont pas fusionnés : le cas est signalé dans « Conflits »."
    )

    def handle(self, *args, **options):
        summary = merge_all_same_orcid()
        self.stdout.write(self.style.SUCCESS(f"ORCID fusionnés : {summary['merged']}"))
        if summary["conflicts"]:
            self.stdout.write(
                self.style.WARNING(
                    f"ORCID portés par des auteurs déclarés distincts : {summary['conflicts']}"
                )
            )
