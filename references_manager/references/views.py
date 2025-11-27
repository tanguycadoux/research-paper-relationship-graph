from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

from .forms import PublicationForm
from .models import Publication
from .services.importer import import_publication


class RegisterView(CreateView):
    form_class = UserCreationForm
    template_name = "registration/register.html"
    success_url = reverse_lazy("login")


class PublicationListView(ListView):
    model = Publication
    template_name = 'references/publications_list.html'
    context_object_name = 'publications'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["publications_lvl0"] = Publication.objects.filter(reference_level=0)
        context["publications_lvl1"] = Publication.objects.filter(reference_level=1)

        return context

class PublicationDetailView(DetailView):
    model = Publication

class PublicationCreateView(LoginRequiredMixin, CreateView):
    model = Publication
    form_class = PublicationForm
    success_url = reverse_lazy('publications_list')

class PublicationUpdateView(LoginRequiredMixin, UpdateView):
    model = Publication
    form_class = PublicationForm
    success_url = reverse_lazy('publications_list')

class PublicationDeleteView(LoginRequiredMixin, DeleteView):
    model = Publication
    success_url = reverse_lazy('publications_list')


def index(request):
    return render(request, "references/index.html", {})

@login_required
def fetch_crossref(request, pk):
    pub = get_object_or_404(Publication, pk=pk)

    try:
        return JsonResponse(pub.crossref_json)
    except:
        raise Http404(f'404 : JSON CrossRef non récupéré pour la publication id={pk}')

@login_required
def trigger_import_publication(request, pk):
    """
    Vue pour déclencher manuellement l'import CrossRef pour le debug.
    """
    pub = get_object_or_404(Publication, pk=pk)

    try:
        import_publication(pub, parse_references=True, force_fetch=False)
        messages.success(request, f"Import CrossRef terminé pour {pub}")
    except Exception as e:
        messages.error(request, f"Erreur lors de l'import : {e}")

    return redirect("publication_detail", pk=pub.pk)
