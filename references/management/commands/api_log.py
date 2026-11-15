from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from references.services.sources import api_log_summary as summary


class Command(BaseCommand):
    help = (
        "Résume le journal des appels aux sources externes (#395) : par source, par "
        "origine (page, demande de la file, commande), et les requêtes les plus lentes."
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
        self.slowest(result["slowest"][: options["top"]])

    def overview(self, found):
        cached = sum(1 for entry in found if entry.get("cache"))
        first, last = found[0]["at"], found[-1]["at"]
        self.stdout.write(
            f"{len(found)} requêtes du {first:%Y-%m-%d %H:%M} au {last:%Y-%m-%d %H:%M}, "
            f"dont {cached} servies par le cache.\n"
        )

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
