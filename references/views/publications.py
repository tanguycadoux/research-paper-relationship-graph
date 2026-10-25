from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from ..forms import PublicationForm
from ..models import CitedReference, Publication, UserPublication
from ..services import filters, tags
from ..services.external_records import metadata_status
from ..services.identification import is_to_identify
from ..services.importer import import_publication
from ..services.organizations import numbered_affiliations
from ..services.preprints import BIBLIOGRAPHY_NOT_FETCHED, arxiv_bibliography
from ..services.publication_details import crossref_details, publication_abstract
from ..services.publication_edits import (
    identifier_changed,
    record_manual_edits,
    refetch_after_identifier_change,
    restore_source_values,
)
from ..services.publication_table import (
    corpus_ids,
    for_publication_table,
    references_available,
)
from ..services.published_versions import proposal_message
from ..services.sorting import PUBLICATIONS
from .pagination import PageMixin


class PublicationListView(PageMixin, ListView):
    model = Publication
    template_name = "references/publications_list.html"
    context_object_name = "publications"

    def get_queryset(self):
        self.sort = PUBLICATIONS.read(self.request.GET.get("sort"))
        self.active_filters = filters.PUBLICATIONS.read(self.request.GET)
        publications = filters.PUBLICATIONS.apply(Publication.objects.all(), self.active_filters)
        return PUBLICATIONS.apply(for_publication_table(publications), self.sort)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context |= {
            "user_pub_ids": corpus_ids(self.request.user),
            "sorting": PUBLICATIONS,
            "sort": self.sort,
            "filters": filters.PUBLICATIONS,
            "active_filters": self.active_filters,
        }
        return context


class PublicationDetailView(DetailView):
    model = Publication

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pub = self.object

        context["user_pub_ids"] = corpus_ids(self.request.user)
        context["belongs_to_user"] = pub.pk in context["user_pub_ids"]
        if context["belongs_to_user"]:
            entry = UserPublication.objects.get(user=self.request.user, publication=pub)
            context["reading_status"] = entry.reading_status
            context["reading_statuses"] = UserPublication.ReadingStatus.choices
            context["entry_tags"] = entry.tags.all()
            context["known_tags"] = sorted(tags.known_paths(self.request.user), key=str.casefold)

        context["cited_references"] = pub.cited_references.select_related("target")
        # Only publications whose bibliography was imported (those of a corpus) can cite it.
        context["citing_publications"] = for_publication_table(
            Publication.objects.filter(
                pk__in=CitedReference.objects.filter(target=pub).values("source")
            )
        ).order_by("-publication_date", "title")
        context["metadata_status"] = metadata_status(pub)
        context["references_available"] = references_available(pub)
        context["arxiv_bibliography"] = arxiv_bibliography(pub)
        context["version_proposal"] = proposal_message(pub)
        # The bibliography of a preprint is fetched by the same action (#227).
        context["can_import_references"] = (
            self.request.user.is_authenticated
            and not context["cited_references"]
            and (
                context["references_available"]
                or context["arxiv_bibliography"] == BIBLIOGRAPHY_NOT_FETCHED
            )
        )
        to_identify = [ref for ref in context["cited_references"] if is_to_identify(ref)]
        context["references_to_identify"] = len(to_identify)
        # Start of « Identifier en série » (#242).
        context["first_to_identify"] = min(to_identify, key=lambda ref: ref.position, default=None)
        context["references_unidentifiable"] = sum(
            1 for ref in context["cited_references"] if ref.unidentifiable
        )
        context["details"] = crossref_details(pub)
        context["abstract"] = publication_abstract(pub)
        context["authors"] = numbered_affiliations(
            pub.authorpublication_set.select_related("author")
            .prefetch_related("organizations__ancestors")
            .order_by("order")
        )
        return context


class PublicationCreateView(LoginRequiredMixin, CreateView):
    model = Publication
    form_class = PublicationForm
    success_url = reverse_lazy("publication_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.object.doi:
            import_publication(self.object)
        return response


class PublicationUpdateView(LoginRequiredMixin, UpdateView):
    model = Publication
    form_class = PublicationForm

    def form_valid(self, form):
        record_manual_edits(form.instance, form.changed_data)
        response = super().form_valid(form)
        if identifier_changed(form.changed_data):
            imported = refetch_after_identifier_change(self.object)
            # A preprint DOI may lead to its published version, already in the base (#227).
            self.object = imported or self.object
            report_refetch(self.request, self.object, imported)
        else:
            messages.success(self.request, f"« {self.object} » a été modifiée.")
        return response

    def get_success_url(self):
        return reverse("publication_detail", args=[self.object.pk])


def report_refetch(request, pub, imported):
    pub.refresh_from_db()
    if imported:
        messages.success(request, f"Identifiant modifié : données de « {pub} » récupérées.")
    else:
        messages.warning(
            request,
            f"Identifiant modifié, mais les données de « {pub} » n'ont pas pu être récupérées "
            "(identifiant inconnu des sources, ou service injoignable).",
        )


@login_required
@require_POST
def restore_publication_sources(request, pk):
    """Forget the manual corrections of the title and date: the sources decide again."""
    pub = get_object_or_404(Publication, pk=pk)
    restore_source_values(pub)
    messages.success(request, f"Titre et date repris des sources pour « {pub} ».")
    return redirect("publication_detail", pk=pk)


@login_required
def publication_metadata(request, pk):
    """Raw answers of the external sources about a publication, as JSON."""
    pub = get_object_or_404(Publication, pk=pk)
    records = {
        record.source: {"fetched_at": record.fetched_at.isoformat(), "data": record.data}
        for record in pub.external_records.all()
    }
    if not records:
        raise Http404(f"Aucune métadonnée récupérée pour la publication id={pk}")
    return JsonResponse(records)


@login_required
@require_POST
def trigger_import_publication(request, pk):
    """
    Fetch the Crossref data of a publication again: the only way to call
    Crossref for a publication whose data was already fetched.
    """
    pub = get_object_or_404(Publication, pk=pk)
    if imported := import_publication(pub, with_references=pub.parse_references, force_fetch=True):
        pub = imported
        messages.success(request, f"Métadonnées rafraîchies pour « {pub} ».")
    else:
        messages.error(request, f"Impossible de récupérer les métadonnées de « {pub} ».")
    return redirect("publication_detail", pk=pub.pk)


@login_required
@require_POST
def import_publication_references(request, pk):
    """
    Import the bibliography of a publication outside any corpus, without adding it
    to the user's corpus: its references join the shared base (#23).
    """
    pub = get_object_or_404(Publication, pk=pk)
    if imported := import_publication(pub, with_references=True):
        pub = imported
        count = pub.cited_references.count()
        messages.success(request, f"{count} référence(s) importée(s) pour « {pub} ».")
    else:
        messages.error(request, f"Impossible de récupérer les métadonnées de « {pub} ».")
    return redirect("publication_detail", pk=pub.pk)
