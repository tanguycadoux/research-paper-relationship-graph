from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

from plotly.offline import plot

from .forms import PublicationForm, AuthorMergeSelectForm, AuthorMergeConfirmForm
from .models import Publication, UserPublication, Author
from .services.importer import import_publication
from .utils import build_user_refs_graph, build_pub_graph, plotly_graph_from_nx


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

        pubs = Publication.objects.exclude(title='')
        pubs = pubs.order_by('-publication_date')

        context["publications"] = pubs

        user = self.request.user
        if user.is_authenticated:
            context["user_pub_ids"] = set(
                UserPublication.objects.filter(user=user).values_list('publication_id', flat=True)
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
            context['belongs_to_user'] = pub.userpublication_set.filter(user=user).exists()
        else:
            context['belongs_to_user'] = False

        return context

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

class AuthorListView(ListView):
    model = Author
    template_name = 'references/authors_list.html'
    context_object_name = 'authors'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        authors = Author.objects.all()
        authors = authors.order_by('last_name')

        context["authors"] = authors

        return context

class AuthorDetailView(DetailView):
    model = Author

class AuthorUpdateView(LoginRequiredMixin, UpdateView):
    model = Author
    success_url = reverse_lazy('author_detail')


def index(request):
    return render(request, "references/index.html", {})

def pub_graph(request, pk):
    pub = get_object_or_404(Publication, pk=pk)

    G = build_pub_graph(pub)
    fig = plotly_graph_from_nx(G, [pub.pk])
    plot_div = plot(
        fig,
        output_type='div',
        include_plotlyjs=True,
        config={
            'responsive': True,
            'displayModeBar': False
        }
    )

    return render(request, "references/publication_graph.html", {"plot_div": plot_div})


@login_required
def my_refs_graph(request):
    G = build_user_refs_graph(request.user)
    user_pub_ids = set(
        UserPublication.objects
        .filter(user=request.user)
        .values_list('publication_id', flat=True)
    )

    fig = plotly_graph_from_nx(G, user_pub_ids)
    plot_div = plot(
        fig,
        output_type='div',
        include_plotlyjs=True,
        config={
            'responsive': True,
            'displayModeBar': False
        }
    )

    return render(request, "references/user_references_graph.html", {"plot_div": plot_div})

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
    raw_doi = request.POST.get("doi", "").strip()

    if not raw_doi:
        messages.error(request, "Veuillez entrer un DOI.")
        return redirect("my_references")
    
    normalized_doi = raw_doi.lower().replace("https///doi.org/", "").strip()

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

@login_required
def author_merge_select_view(request):
    if request.method == "POST":
        form = AuthorMergeSelectForm(request.POST)
        if form.is_valid():
            ids = [a.id for a in form.cleaned_data["authors"]]
            return redirect("author_merge_confirm", ids=",".join(map(str, ids)))
    else:
        form = AuthorMergeSelectForm()

    return render(request, "references/authors_merge_select.html", {"form": form})

@login_required
def author_merge_confirm_view(request, ids):
    ids = [int(i) for i in ids.split(",")]
    authors = list(Author.objects.filter(id__in=ids))

    if len(authors) < 2:
        messages.error(request, "Il faut au moins deux auteurs.")
        return redirect("merge_select")

    pivot = authors[0]

    if request.method == "POST":
        form = AuthorMergeConfirmForm(request.POST)
        if form.is_valid():
            pivot.first_name = form.cleaned_data["first_name"]
            pivot.last_name  = form.cleaned_data["last_name"]
            pivot.orcid      = form.cleaned_data["orcid"]
            pivot.save()

            pivot.merge_with([a for a in authors if a != pivot])

            messages.success(request, "Les auteurs ont été fusionnés.")
            return redirect("author_detail", pk=pivot.pk)

    else:
        form = AuthorMergeConfirmForm(initial={
            "first_name": pivot.first_name,
            "last_name": pivot.last_name,
            "orcid": pivot.orcid,
        })

    return render(request, "references/authors_merge_confirm.html", {
        "form": form,
        "authors": authors,
        "pivot": pivot,
    })
