from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import DetailView, ListView, UpdateView

from ..forms import AuthorForm, AuthorMergeConfirmForm, AuthorMergeSelectForm
from ..models import Author
from ..services import author_merge


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

    kept = authors[0]
    candidates = author_merge.candidate_values(authors)
    form = AuthorMergeConfirmForm(
        request.POST or None,
        initial=author_merge.default_values(candidates),
        candidates=candidates,
        orcid_conflict=author_merge.has_orcid_conflict(candidates),
    )
    if request.method == "POST" and form.is_valid():
        author_merge.merge_authors(kept, authors[1:], form.cleaned_data)
        messages.success(request, f"{len(authors)} auteurs fusionnés en « {kept} ».")
        return redirect("author_detail", pk=kept.pk)

    return render(
        request, "references/authors_merge_confirm.html", {"form": form, "authors": authors}
    )
