from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

CONFIRMATION = "oui"


class Command(BaseCommand):
    help = (
        "Développement : efface toutes les données de l'application (publications, "
        "auteurs, organisations, références, corpus, tags, conflits…) et ne garde que les "
        "comptes utilisateurs. Refusé hors DEBUG."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-input",
            "--noinput",
            action="store_false",
            dest="interactive",
            help="Ne pas demander de confirmation.",
        )

    def handle(self, *args, interactive, **options):
        if not settings.DEBUG:
            raise CommandError("Commande de développement : refusée quand DEBUG est désactivé.")
        models = list(apps.get_app_config("references").get_models())
        counts = {model.__name__: model.objects.count() for model in models}
        if not any(counts.values()):
            self.stdout.write("Aucune donnée à effacer.")
            return
        for name, count in counts.items():
            if count:
                self.stdout.write(f"  {name} : {count}")
        if interactive and input(f"Tout effacer ? Tapez « {CONFIRMATION} » : ") != CONFIRMATION:
            self.stdout.write("Abandon : rien n'a été effacé.")
            return
        with transaction.atomic():
            for model in models:
                model.objects.all().delete()
        self.stdout.write(self.style.SUCCESS("Données effacées ; les comptes sont gardés."))
