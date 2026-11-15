import subprocess
import sys

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Lance le serveur de développement avec la feuille de style Tailwind (tailwind "
        "runserver) et le worker de la file des récupérations (fetch_worker), dans un seul "
        "terminal. Les arguments sont passés à runserver : python manage.py dev 8001."
    )

    def add_arguments(self, parser):
        parser.add_argument("runserver_args", nargs="*")

    def handle(self, *args, **options):
        manage = [sys.executable, "manage.py"]
        commands = [
            [*manage, "tailwind", "runserver", *options["runserver_args"]],
            [*manage, "fetch_worker", "--reload"],
        ]
        processes = [subprocess.Popen(command, cwd=settings.BASE_DIR) for command in commands]
        try:
            # Either one stopping stops the other.
            while all(process.poll() is None for process in processes):
                try:
                    processes[0].wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
        except KeyboardInterrupt:
            pass
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            for process in processes:
                process.wait()
