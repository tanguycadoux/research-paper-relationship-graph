from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..models import Publication, UserPublication
from ..services.doi import is_valid_doi, normalize_doi
from ..services.importer import import_publication


@login_required
def add_to_user_refs(request, pk):
    pub = get_object_or_404(Publication, pk=pk)

    if not pub.parse_references:
        import_publication(pub, parse_references=True)
        pub.parse_references = True
        pub.save(update_fields=["parse_references"])

    UserPublication.objects.get_or_create(
        user=request.user,
        publication=pub,
    )
    return redirect("publication_detail", pk=pk)


@login_required
@require_POST
def add_publication_to_user_refs_by_doi(request):
    normalized_doi = normalize_doi(request.POST.get("doi", ""))

    if not is_valid_doi(normalized_doi):
        messages.error(request, "Veuillez entrer un DOI valide (de la forme 10.xxxx/…).")
        return redirect("my_references")

    pub, created = Publication.objects.get_or_create(doi=normalized_doi)

    if created:
        messages.success(request, f"Publication créée et importée : {pub}")
    else:
        messages.success(request, f"Publication importée : {pub}")

    UserPublication.objects.get_or_create(user=request.user, publication=pub)
    messages.success(request, "Publication ajoutée à vos références.")

    return redirect("my_references")


@login_required
def remove_from_user_refs(request, pk):
    pub = get_object_or_404(Publication, pk=pk)
    UserPublication.objects.filter(user=request.user, publication=pub).delete()
    return redirect("publication_detail", pk=pk)


@login_required
def my_references(request):
    pubs = Publication.objects.filter(userpublication__user=request.user)
    context = {
        "publications": pubs,
    }
    return render(request, "references/user_references.html", context)
