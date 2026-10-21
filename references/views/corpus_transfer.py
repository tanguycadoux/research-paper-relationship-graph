import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..services.corpus_transfer import InvalidExport, corpus_bibtex, export_corpus, import_corpus

MAX_IMPORT_SIZE = 1024 * 1024


def attachment(response, extension):
    filename = f"corpus-{timezone.localdate().isoformat()}.{extension}"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def export_json(request):
    data = export_corpus(request.user)
    return attachment(
        JsonResponse(data, json_dumps_params={"ensure_ascii": False, "indent": 2}), "json"
    )


@login_required
def export_bibtex(request):
    response = HttpResponse(
        corpus_bibtex(request.user), content_type="text/x-bibtex; charset=utf-8"
    )
    return attachment(response, "bib")


@login_required
@require_POST
def import_json(request):
    upload = request.FILES.get("file")
    if upload is None:
        messages.error(request, "Choisissez un fichier d'export (.json).")
        return redirect("my_references")
    if upload.size > MAX_IMPORT_SIZE:
        messages.error(request, "Le fichier dépasse 1 Mo : ce n'est pas un export de corpus.")
        return redirect("my_references")
    try:
        report = import_corpus(request.user, json.loads(upload.read().decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError):
        messages.error(request, "Le fichier n'est pas un JSON valide.")
    except InvalidExport as error:
        messages.error(request, str(error))
    else:
        report_import(request, report)
    return redirect("my_references")


def report_import(request, report):
    messages.success(
        request,
        f"Import terminé : {len(report.added)} publication(s) ajoutée(s), "
        f"{len(report.already_there)} déjà dans votre corpus.",
    )
    if report.without_metadata:
        names = ", ".join(f"« {pub} »" for pub in report.without_metadata)
        messages.warning(
            request, f"Ajoutées sans métadonnées (source inconnue ou injoignable) : {names}."
        )
    if report.ignored:
        messages.warning(request, f"{report.ignored} entrée(s) ignorée(s) : ni DOI ni ISBN valide.")
