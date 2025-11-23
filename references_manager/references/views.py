from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

import requests

from .forms import PublicationForm
from .models import Publication, Author, AuthorPublication


class PublicationListView(ListView):
    model = Publication
    template_name = 'references/publications_list.html'
    context_object_name = 'publications'

class PublicationDetailView(DetailView):
    model = Publication

class PublicationCreateView(CreateView):
    model = Publication
    form_class = PublicationForm
    success_url = reverse_lazy('publications_list')

class PublicationUpdateView(UpdateView):
    model = Publication
    form_class = PublicationForm
    success_url = reverse_lazy('publications_list')

class PublicationDeleteView(DeleteView):
    model = Publication
    success_url = reverse_lazy('publications_list')


def index(request):
    return render(request, "references/index.html", {})

def fetch_crossref(request, pk):
    pub = get_object_or_404(Publication, pk=pk)

    if not pub.crossref_json and pub.doi:
        url = f"https://api.crossref.org/works/{pub.doi}"
        response = requests.get(url)
        if response.status_code == 200:
            pub.crossref_json = response.json()
            pub.save()

    return JsonResponse(pub.crossref_json)

def parse_crossref_json(request, pk):
    pub = get_object_or_404(Publication, pk=pk)

    try:
        message = pub.crossref_json.get("message")

        titles = message.get("title", [])
        if titles:
            pub.title = titles[0]
        pub.save()

        authors_data = message.get("author", [])

        for index, a in enumerate(authors_data):
            first_name = a.get("given")
            last_name = a.get("family")
            orcid = a.get("ORCID")

            if orcid:
                orcid = orcid.replace("https://orcid.org/", "").strip()

            author, created = Author.objects.get_or_create(
                first_name=first_name,
                last_name=last_name,
                orcid=orcid,
            )

            AuthorPublication.objects.create(
                publication=pub,
                author=author,
                order=index
            )

            if created:
                messages.success(request, f"Auteur créé : {author}")
            else:
                messages.info(request, f"Auteur existant lié : {author}")

        messages.success(request, "Données Crossref mises à jour.")
    except Exception as e:
        messages.error(request, f'Erreur dans le parsing CrossRef : {e}')

    return redirect("publications_list")
