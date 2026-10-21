from django.core.management.base import BaseCommand, CommandError

from references.services.icons import UnknownIcon, download_icon


class Command(BaseCommand):
    help = (
        "Télécharge des icônes Material Symbols (Outlined) dans static/icons/, pour "
        '{% icon "nom" %}. Les noms sont ceux de https://fonts.google.com/icons.'
    )

    def add_arguments(self, parser):
        parser.add_argument("names", nargs="+", help="Noms des icônes, par exemple delete edit")

    def handle(self, *args, **options):
        for name in options["names"]:
            try:
                path = download_icon(name)
            except UnknownIcon as error:
                raise CommandError(str(error)) from error
            self.stdout.write(self.style.SUCCESS(f"Icône ajoutée : {path.name}"))
