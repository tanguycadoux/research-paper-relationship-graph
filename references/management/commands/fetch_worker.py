import atexit
import threading
import time
from contextlib import contextmanager

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import autoreload

from references.services.imports import bibliography_requests, fetch_queue
from references.services.sources.http import patient_requests

# Well under fetch_queue.WORKER_TIMEOUT: a long import must not look like a dead worker.
HEARTBEAT_SECONDS = 10


class Command(BaseCommand):
    help = (
        "Traite la file des récupérations (#378) : ajouts et imports de fichier, une demande "
        "à la fois, en respectant le débit des sources. Sans ce worker, les pages font le "
        "travail elles-mêmes."
    )

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Vider la file puis s'arrêter.")
        parser.add_argument(
            "--interval",
            type=float,
            default=2,
            help="Secondes d'attente quand la file est vide (2 par défaut).",
        )
        parser.add_argument(
            "--reload",
            action="store_true",
            help="Redémarrer quand le code change, comme runserver (python manage.py dev).",
        )

    def handle(self, *args, **options):
        if options["reload"]:
            autoreload.run_with_reloader(self.run, **options)
        else:
            self.run(**options)

    def run(self, **options):
        recovered = fetch_queue.recover_interrupted()
        if recovered:
            self.stdout.write(f"{recovered} demande(s) interrompue(s) remise(s) en file.")
        with patient_requests(), heartbeat(enabled=not options["once"]):
            self.work(options["once"], options["interval"])

    def work(self, once, interval):
        fetch_queue.signal_alive()
        while True:
            # The levels whose imports are over form the next ones (#431).
            bibliography_requests.advance_all()
            request = fetch_queue.claim_next()
            if request is not None:
                done = fetch_queue.process_claimed(request)
                what = f"{len(done)} imports" if len(done) > 1 else request.identifier
                self.stdout.write(f"{request.get_action_display()} {what}")
            elif once:
                return
            else:
                time.sleep(interval)


@contextmanager
def heartbeat(enabled=True):
    """Signal the worker alive from a thread, also while a long import runs."""
    if not enabled:
        yield
        return
    # With --reload, the worker runs in a thread that Ctrl+C does not unwind: say it
    # stopped when the process exits.
    atexit.register(fetch_queue.signal_stopped)
    stop = threading.Event()
    thread = threading.Thread(target=beat, args=(stop,), daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join()
        fetch_queue.signal_stopped()


def beat(stop):
    try:
        while not stop.is_set():
            fetch_queue.signal_alive()
            stop.wait(HEARTBEAT_SECONDS)
    finally:
        connection.close()
