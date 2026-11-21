import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from ..models import UserPublication
from ..services.corpus import import_reports
from ..services.corpus.bibliography_files import file_entries
from ..services.corpus.corpus_transfer import (
    InvalidExport,
    corpus_bibtex,
    export_corpus,
    import_corpus,
    import_entries,
)
from ..services.display.filters import filtered_corpus
from ..services.display.wording import count
from ..services.imports import fetch_queue

MAX_IMPORT_SIZE = 1024 * 1024


def attachment(response, extension, selection):
    filename = f"{export_name(selection)}-{timezone.localdate().isoformat()}.{extension}"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def export_name(selection):
    """« corpus », « corpus-projet-a-groupe-a » for a tag alone, else « corpus-selection »."""
    values = selection.active.values
    if not values:
        return "corpus"
    if values.keys() == {"tag"}:
        return f"corpus-{slugify(values['tag'].replace('/', ' ')) or 'tag'}"
    return "corpus-selection"


def selected(request):
    """
    The publications the filters of « Mon corpus » show, as its export buttons pass them
    (#285): the whole corpus without a filter.
    """
    return filtered_corpus(request.user, request.GET)


def chosen(selection):
    return selection.publications if selection.active else None


@login_required
def export_json(request):
    selection = selected(request)
    data = export_corpus(request.user, chosen(selection))
    response = JsonResponse(data, json_dumps_params={"ensure_ascii": False, "indent": 2})
    return attachment(response, "json", selection)


@login_required
def export_bibtex(request):
    selection = selected(request)
    response = HttpResponse(
        corpus_bibtex(request.user, chosen(selection)),
        content_type="text/x-bibtex; charset=utf-8",
    )
    return attachment(response, "bib", selection)


@login_required
@require_POST
def import_file(request):
    """Import an export of this application (JSON), or a BibTeX or RIS file (#165)."""
    upload = request.FILES.get("file")
    if upload is None:
        messages.error(request, "Choisissez un fichier (.json, .bib ou .ris).")
        return redirect("corpus")
    if upload.size > MAX_IMPORT_SIZE:
        messages.error(
            request, "Le fichier dépasse 1 Mo : importez votre corpus en plusieurs fois."
        )
        return redirect("corpus")
    text = decoded(upload.read())
    # « à lire »: the bibliographies are left aside, the import is much faster (#234).
    default_status = UserPublication.ReadingStatus.TO_READ if request.POST.get("to_read") else ""
    queued = fetch_queue.worker_alive()
    if text.lstrip().startswith(("{", "[")):
        try:
            report = import_corpus(request.user, json.loads(text), default_status, queued=queued)
        except json.JSONDecodeError:
            messages.error(request, "Le fichier n'est pas un JSON valide.")
            return redirect("corpus")
        except InvalidExport as error:
            messages.error(request, str(error))
            return redirect("corpus")
    else:
        entries = file_entries(text)
        if not entries:
            messages.error(
                request,
                "Aucune entrée trouvée : le fichier n'est ni un export JSON de cette "
                "application, ni un fichier BibTeX ou RIS.",
            )
            return redirect("corpus")
        report = import_entries(request.user, entries, default_status, queued=queued)
    report_import(request, report)
    return redirect("corpus")


def decoded(content):
    """UTF-8 (with or without BOM), else Latin-1, which older BibTeX files use."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def report_import(request, report):
    """
    One short sentence (#411): the details stay at the top of « Mon corpus » until the
    report is closed (#330), and the queue has its own toast (#379).
    """
    import_reports.remember(request.session, report)
    added = import_reports.added_count(report)
    parts = [count(added, "publication ajoutée") if added else "aucune publication ajoutée"]
    ignored = len(report.ignored) + len(report.unregistered)
    if ignored:
        parts.append(count(ignored, "entrée ignorée"))
    summary = ", ".join(parts)
    messages.success(request, f"Import terminé : {summary} ; le rapport est en haut de la page.")


@login_required
@require_POST
def close_import_report(request):
    import_reports.forget(request.session)
    return redirect("corpus")
