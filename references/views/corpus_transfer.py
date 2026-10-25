import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import UserPublication
from ..services.bibliography_files import file_entries
from ..services.corpus_transfer import (
    InvalidExport,
    corpus_bibtex,
    export_corpus,
    import_corpus,
    import_entries,
)

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
    if text.lstrip().startswith(("{", "[")):
        try:
            report = import_corpus(request.user, json.loads(text), default_status)
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
        report = import_entries(request.user, entries, default_status)
    report_import(request, report)
    return redirect("corpus")


def decoded(content):
    """UTF-8 (with or without BOM), else Latin-1, which older BibTeX files use."""
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


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
        messages.warning(
            request,
            f"{len(report.ignored)} entrée(s) ignorée(s), sans DOI, identifiant arXiv ni "
            f"ISBN valide : {listed(report.ignored)}.",
        )


def listed(titles, limit=10):
    names = ", ".join(
        f"« {title} »" if title else "une entrée sans titre" for title in titles[:limit]
    )
    rest = len(titles) - limit
    return f"{names} et {rest} autre(s)" if rest > 0 else names
