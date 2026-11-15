from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from references.services.display.wording import count
from references.services.sources import api_log_summary as summary


class Command(BaseCommand):
    help = (
        "Résume le journal des appels aux sources externes (#395) : par source, par "
        "origine (page, demande de la file, commande), les demandes de la file par action, et "
        "les requêtes les plus lentes."
    )

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=float, help="Seulement les N dernières heures.")
        parser.add_argument(
            "--file", default=settings.API_LOG_PATH, help="Journal à lire (API_LOG_PATH)."
        )
        parser.add_argument("--top", type=int, default=15, help="Lignes par tableau (15).")

    def handle(self, *args, **options):
        if not options["file"]:
            raise CommandError("Le journal est coupé (API_LOG_PATH vide).")
        since = timezone.now() - timedelta(hours=options["hours"]) if options["hours"] else None
        found = summary.entries(summary.journal_files(options["file"]), since)
        if not found:
            self.stdout.write("Aucune requête dans le journal.")
            return
        result = summary.summarize(found)
        self.overview(found)
        self.table("Par source", result["by_service"], options["top"])
        self.table("Par origine", result["by_origin"], options["top"])
        self.queue(result["by_action"])
        self.slowest(result["slowest"][: options["top"]])

    def overview(self, found):
        api = [entry for entry in found if summary.is_api(entry)]
        cached = sum(1 for entry in api if entry.get("cache"))
        done = len(found) - len(api)
        first, last = found[0]["at"], found[-1]["at"]
        queue = count(done, "demande de la file traitée", "demandes de la file traitées")
        self.stdout.write(
            f"{count(len(api), 'requête')} du {first:%Y-%m-%d %H:%M} au {last:%Y-%m-%d %H:%M}, "
            f"dont {cached} servie{'s' if cached > 1 else ''} par le cache ; {queue}.\n"
        )

    def queue(self, by_action):
        if not by_action:
            return
        self.stdout.write(self.style.MIGRATE_HEADING("Demandes de la file"))
        self.stdout.write(
            f"  {'':44} {'demandes':>8} {'échecs':>6} {'attente':>8} {'durée':>8} "
            f"{'appels/demande':>14}"
        )
        for action, line in sorted(by_action.items(), key=lambda item: -item[1].requests):
            self.stdout.write(
                f"  {action[:44]:44} {line.requests:>8} {line.failed:>6} "
                f"{line.median_wait():>6}ms {line.median():>6}ms {line.per_request():>14}"
            )
        self.stdout.write("")

    def table(self, title, stats, top):
        self.stdout.write(self.style.MIGRATE_HEADING(title))
        self.stdout.write(
            f"  {'':44} {'requêtes':>8} {'cache':>6} {'404':>5} {'erreurs':>7} "
            f"{'médiane':>8} {'p95':>7} {'total':>8}"
        )
        ranked = sorted(stats.items(), key=lambda item: item[1].seconds(), reverse=True)
        for name, line in ranked[:top]:
            self.stdout.write(
                f"  {name[:44]:44} {line.requests:>8} {line.cached:>6} {line.unknown:>5} "
                f"{line.errors:>7} {line.median():>6}ms {line.p95():>5}ms {line.seconds():>7}s"
            )
        self.stdout.write("")

    def slowest(self, entries):
        self.stdout.write(self.style.MIGRATE_HEADING("Les plus lentes"))
        for entry in entries:
            self.stdout.write(
                f"  {entry['ms']:>6}ms  {entry.get('status')}  {entry['service']:10} "
                f"{entry['subject'][:50]:50}  {summary.origin(entry)}"
            )
