from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from ..forms import PublicationForm
from ..models import Publication, UserPublication
from ..services.importer import import_publication


class PublicationListView(ListView):
    model = Publication
    template_name = "references/publications_list.html"
    context_object_name = "publications"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        pubs = Publication.objects.exclude(title="")
        pubs = pubs.order_by("-publication_date")

        context["publications"] = pubs

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
        return context


class PublicationCreateView(LoginRequiredMixin, CreateView):
    model = Publication
    form_class = PublicationForm
    success_url = reverse_lazy("publications_list")


class PublicationUpdateView(LoginRequiredMixin, UpdateView):
    model = Publication
    form_class = PublicationForm
    success_url = reverse_lazy("publications_list")


class PublicationDeleteView(LoginRequiredMixin, DeleteView):
    model = Publication
    success_url = reverse_lazy("publications_list")


@login_required
def fetch_crossref(request, pk):
    pub = get_object_or_404(Publication, pk=pk)

    if not pub.crossref_json:
        raise Http404(f"404 : JSON CrossRef non récupéré pour la publication id={pk}")
    return JsonResponse(pub.crossref_json)


@login_required
def trigger_import_publication(request, pk):
    """
    Manually trigger the Crossref import of a publication (debug helper).
    """
    pub = get_object_or_404(Publication, pk=pk)

    try:
        import_publication(pub, parse_references=True, force_fetch=False)
        messages.success(request, f"Import CrossRef terminé pour {pub}")
    except Exception as e:
        messages.error(request, f"Erreur lors de l'import : {e}")

    return redirect("publication_detail", pk=pub.pk)
