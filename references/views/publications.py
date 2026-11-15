from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from ..forms import PublicationForm
from ..models import CitedReference, FetchRequest, Publication, UserPublication
from ..services.corpus import tags
from ..services.corrections.identification import is_to_identify
from ..services.corrections.publication_edits import (
    forget_fetched,
    identifier_changed,
    record_manual_edits,
    refetch_after_identifier_change,
    restore_source_values,
)
from ..services.discovery import incoming_citations
from ..services.display import filters, wording
from ..services.display.open_access import open_access_link
from ..services.display.publication_details import crossref_details, publication_abstract
from ..services.display.publication_table import (
    corpus_ids,
    for_publication_table,
    references_available,
)
from ..services.display.sorting import PUBLICATIONS
from ..services.imports import fetch_queue
from ..services.imports.importer import import_publication
from ..services.imports.jacow import is_jacow
from ..services.imports.organizations import numbered_affiliations
from ..services.imports.preprints import BIBLIOGRAPHY_NOT_FETCHED, arxiv_bibliography
from ..services.imports.published_versions import proposal_message
from ..services.sources.external_records import metadata_status
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

        # Its data still to come from the queue: the page says so, and reloads once done (#379).
        if self.request.user.is_authenticated and fetch_queue.publication_pending(pub):
            context["fetch_pending_publication"] = pub.pk
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
        ).order_by("-publication_date", "readable_title")
        context |= incoming_citations_context(self.request, pub)
        context["metadata_status"] = metadata_status(pub)
        context["references_available"] = references_available(pub)
        context["arxiv_bibliography"] = arxiv_bibliography(pub)
        context["version_proposal"] = proposal_message(pub)
        context["uncertain_author_order"] = is_jacow(pub.doi)
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
        # Those the source does not describe: the article alone says what they are (#273).
        context["references_undescribed"] = sum(1 for ref in to_identify if not ref.is_described)
        # Start of « Identifier en série » (#242).
        context["first_to_identify"] = min(to_identify, key=lambda ref: ref.position, default=None)
        context["references_unidentifiable"] = sum(
            1 for ref in context["cited_references"] if ref.unidentifiable
        )
        context["details"] = crossref_details(pub)
        context["abstract"] = publication_abstract(pub)
        context["open_access"] = open_access_link(pub)
        context.update(long_lists_context(self.request, pub, context["cited_references"]))
        return context


# Long lists folded (#269): a LIGO article has 1 012 authors, « Hallmarks of Cancer »
# 247 references; the page was 9 000 to 13 600 px high.
AUTHORS_SHOWN = 20
REFERENCES_SHOWN = 100


def long_lists_context(request, pub, cited_references):
    """
    The authors (the first 20 and the last one, with the affiliations of these only)
    and the references (the first 100) shown, unless ?auteurs=tous or
    ?references=toutes asks for all of them; and the links that unfold them.
    """
    slots = list(
        pub.authorpublication_set.select_related("author")
        .prefetch_related("organizations__ancestors")
        .order_by("order")
    )
    all_authors = request.GET.get("auteurs") == "tous" or len(slots) <= AUTHORS_SHOWN + 1
    shown = slots if all_authors else [*slots[:AUTHORS_SHOWN], slots[-1]]
    all_references = request.GET.get("references") == "toutes"
    references = list(cited_references)
    return {
        "authors": numbered_affiliations(shown),
        "author_total": len(slots),
        "authors_hidden": len(slots) - len(shown),
        "authors_shown": AUTHORS_SHOWN,
        "all_authors_url": query_with(request, auteurs="tous") + "#authors-title",
        "shown_references": references if all_references else references[:REFERENCES_SHOWN],
        "references_hidden": 0 if all_references else max(len(references) - REFERENCES_SHOWN, 0),
        "all_references_url": query_with(request, references="toutes") + "#references-title",
    }


def query_with(request, **params):
    query = request.GET.copy()
    for key, value in params.items():
        query[key] = value
    return f"?{query.urlencode()}"


def incoming_citations_context(request, pub):
    """Beyond the base, according to OpenAlex, once someone asked (#163)."""
    citations = getattr(pub, "incoming_citations", None)
    order = request.GET.get("citants", "")
    order = order if order in incoming_citations.ORDERS else "citees"
    return {
        "incoming_citations": citations,
        "citing_order": order,
        "citing_orders": incoming_citations.ORDERS,
        "citing_works": (
            incoming_citations.citing_works(citations, request.user, order) if citations else []
        ),
    }


class PublicationCreateView(LoginRequiredMixin, CreateView):
    model = Publication
    form_class = PublicationForm

    def form_valid(self, form):
        """Then to the page of the publication, with what the sources gave (#272)."""
        response = super().form_valid(form)
        if not self.object.doi:
            messages.success(self.request, f"« {self.object} » a été ajoutée à la base.")
            return response
        imported = import_publication(self.object)
        # A preprint DOI may lead to its published version, already in the base (#227).
        self.object = imported or self.object
        self.object.refresh_from_db()
        if imported:
            messages.success(
                self.request, f"« {self.object} » a été ajoutée à la base, avec ses métadonnées."
            )
        else:
            messages.warning(
                self.request,
                f"« {self.object} » a été ajoutée à la base, mais ses métadonnées n'ont pas pu "
                "être récupérées (DOI inconnu des sources, ou service injoignable).",
            )
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("publication_detail", args=[self.object.pk])


class PublicationUpdateView(LoginRequiredMixin, UpdateView):
    model = Publication
    form_class = PublicationForm

    def form_valid(self, form):
        record_manual_edits(form.instance, form.changed_data)
        response = super().form_valid(form)
        if identifier_changed(form.changed_data) and self.object.doi and fetch_queue.worker_alive():
            # Dropping what was fetched is quick; fetching the new DOI waits in the queue.
            forget_fetched(self.object)
            fetch_queue.enqueue(
                self.object, self.request.user, with_references=self.object.parse_references
            )
            messages.success(
                self.request,
                f"Identifiant modifié : les données de « {self.object} » sont en file de "
                "récupération.",
            )
        elif identifier_changed(form.changed_data):
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
    message = f"Rafraîchissement des métadonnées de « {pub} » en file de récupération."
    if queued(request, FetchRequest.Action.REFRESH, pub, message):
        return redirect("publication_detail", pk=pk)
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
    action = FetchRequest.Action.IMPORT_WITH_REFERENCES
    if queued(request, action, pub, f"Références de « {pub} » en file de récupération."):
        return redirect("publication_detail", pk=pk)
    if imported := import_publication(pub, with_references=True):
        pub = imported
        count = pub.cited_references.count()
        messages.success(request, f"{wording.count(count, 'référence importée')} pour « {pub} ».")
    else:
        messages.error(request, f"Impossible de récupérer les métadonnées de « {pub} ».")
    return redirect("publication_detail", pk=pub.pk)


@login_required
@require_POST
def fetch_incoming_citations(request, pk):
    """Ask OpenAlex for the works that cite a publication (#163)."""
    pub = get_object_or_404(Publication, pk=pk)
    action = FetchRequest.Action.INCOMING_CITATIONS
    message = f"Recherche des publications qui citent « {pub} » en file de récupération."
    if queued(request, action, pub, message):
        return redirect(reverse("publication_detail", args=[pk]) + "#incoming-title")
    try:
        citations = incoming_citations.fetch(pub)
    except incoming_citations.IncomingCitationsError as error:
        messages.error(request, str(error))
    else:
        citing = wording.count(citations.total, "publication qui cite", "publications qui citent")
        messages.success(request, f"OpenAlex recense {citing} « {pub} ».")
    return redirect(reverse("publication_detail", args=[pub.pk]) + "#incoming-title")


def queued(request, action, pub, message):
    """
    With a worker, put the action in the queue and say so (#380); False without one: the
    view does the work itself.
    """
    if not fetch_queue.worker_alive():
        return False
    fetch_queue.enqueue_action(action, request.user, publication=pub)
    messages.success(request, message)
    return True
