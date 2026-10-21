from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView, UpdateView

from ..forms import AuthorForm, AuthorMergeConfirmForm, AuthorMergeSelectForm
from ..models import Author


class AuthorListView(ListView):
    model = Author
    template_name = "references/authors_list.html"
    context_object_name = "authors"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        authors = Author.objects.all()
        authors = authors.order_by("last_name")

        context["authors"] = authors

        return context


class AuthorDetailView(DetailView):
    model = Author

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # distinct: after a merge, one author can hold several slots of a publication.
        context["publications"] = self.object.publications.distinct().order_by("-publication_date")
        return context


class AuthorUpdateView(LoginRequiredMixin, UpdateView):
    model = Author
    form_class = AuthorForm

    def get_success_url(self):
        messages.success(self.request, f"« {self.object} » a été modifié.")
        return reverse("author_detail", args=[self.object.pk])


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


def authors_from_ids(ids):
    """Authors of a comma-separated list of ids, the first created one first."""
    pks = [int(pk) for pk in ids.split(",") if pk.isdigit()]
    return list(
        Author.objects.filter(pk__in=pks)
        .annotate(publication_count=Count("publications", distinct=True))
        .order_by("pk")
    )


@login_required
def author_merge_confirm_view(request, ids):
    authors = authors_from_ids(ids)

    if len(authors) < 2:
        messages.error(request, "Il faut au moins deux auteurs.")
        return redirect("authors_merge_select")

    pivot = authors[0]
    form = AuthorMergeConfirmForm(request.POST or None, initial=editable_fields(pivot))
    if request.method == "POST" and form.is_valid():
        merge_authors(pivot, authors[1:], form.cleaned_data)
        messages.success(request, f"{len(authors)} auteurs fusionnés en « {pivot} ».")
        return redirect("author_detail", pk=pivot.pk)

    context = {"form": form, "authors": authors, "pivot": pivot}
    return render(request, "references/authors_merge_confirm.html", context)


MERGE_FIELDS = ("first_name", "last_name", "orcid")


def editable_fields(author):
    return {field: getattr(author, field) for field in MERGE_FIELDS}


@transaction.atomic
def merge_authors(pivot, others, data):
    """Keep pivot with the chosen values and move the publications of the others to it."""
    for field in MERGE_FIELDS:
        setattr(pivot, field, data[field])
    pivot.save()
    pivot.merge_with(others)
