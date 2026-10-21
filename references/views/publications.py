from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from ..forms import PublicationForm
from ..models import Publication, UserPublication
from ..services.importer import import_publication
from ..services.publication_details import crossref_details


class PublicationListView(ListView):
    model = Publication
    template_name = "references/publications_list.html"
    context_object_name = "publications"
    queryset = Publication.objects.exclude(title="")
    ordering = "-publication_date"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        if user.is_authenticated:
            context["user_pub_ids"] = set(
                UserPublication.objects.filter(user=user).values_list("publication_id", flat=True)
            )
        else:
            context["user_pub_ids"] = set()

        return context


class PublicationDetailView(DetailView):
    model = Publication

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pub = self.get_object()
        user = self.request.user

        if user.is_authenticated:
            context["belongs_to_user"] = pub.userpublication_set.filter(user=user).exists()
        else:
            context["belongs_to_user"] = False

        context["cited_references"] = pub.cited_references.select_related("target")
        context["details"] = crossref_details(pub)
        context["author_slots"] = (
            pub.authorpublication_set.select_related("author")
            .prefetch_related("organizations")
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
    success_url = reverse_lazy("publication_list")


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
    if import_publication(pub, with_references=pub.parse_references, force_fetch=True):
        messages.success(request, f"Métadonnées rafraîchies pour « {pub} ».")
    else:
        messages.error(request, f"Impossible de récupérer les métadonnées de « {pub} ».")
    return redirect("publication_detail", pk=pub.pk)
