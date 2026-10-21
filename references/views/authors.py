from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, UpdateView

from ..forms import AuthorMergeConfirmForm, AuthorMergeSelectForm
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


class AuthorUpdateView(LoginRequiredMixin, UpdateView):
    model = Author
    success_url = reverse_lazy("author_detail")


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
            pivot.last_name = form.cleaned_data["last_name"]
            pivot.orcid = form.cleaned_data["orcid"]
            pivot.save()

            pivot.merge_with([a for a in authors if a != pivot])

            messages.success(request, "Les auteurs ont été fusionnés.")
            return redirect("author_detail", pk=pivot.pk)

    else:
        form = AuthorMergeConfirmForm(
            initial={
                "first_name": pivot.first_name,
                "last_name": pivot.last_name,
                "orcid": pivot.orcid,
            }
        )

    return render(
        request,
        "references/authors_merge_confirm.html",
        {
            "form": form,
            "authors": authors,
            "pivot": pivot,
        },
    )
