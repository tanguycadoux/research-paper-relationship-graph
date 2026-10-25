from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, UpdateView

from ..forms import AuthorForm, AuthorMergeConfirmForm, AuthorMergeSelectForm
from ..models import Author, Publication
from ..services import author_distinctions, author_duplicates, author_merge
from ..services.orcid_merge import merge_same_orcid
from ..services.orcid_profile import orcid_profile, refresh_orcid_record
from ..services.organizations import organization_groups
from ..services.publication_table import corpus_ids, for_publication_table


class AuthorListView(ListView):
    model = Author
    template_name = "references/authors_list.html"
    context_object_name = "authors"
    ordering = "last_name"


class AuthorDetailView(DetailView):
    model = Author

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # pk__in: after a merge, one author can hold several slots of a publication,
        # which a join would count twice (rows and badges).
        context["publications"] = for_publication_table(
            Publication.objects.filter(pk__in=self.object.publications.values("pk"))
        ).order_by("-publication_date", "title")
        context["user_pub_ids"] = corpus_ids(self.request.user)
        context["organization_groups"] = organization_groups(self.object)
        context["merges"] = self.object.merges.select_related("merged_by")
        context["orcid_profile"] = orcid_profile(self.object)
        return context


@login_required
@require_POST
def author_orcid_refresh_view(request, pk):
    """Ask ORCID for the public record of the author (on demand only, #59)."""
    author = get_object_or_404(Author, pk=pk)
    if not author.orcid:
        messages.error(request, "Cet auteur n'a pas d'ORCID.")
    elif refresh_orcid_record(author):
        messages.success(request, "Profil ORCID mis à jour.")
    else:
        messages.error(request, "ORCID n'a pas répondu ou ne connaît pas cet identifiant.")
    return redirect("author_detail", pk=author.pk)


class AuthorUpdateView(LoginRequiredMixin, UpdateView):
    model = Author
    form_class = AuthorForm

    def form_valid(self, form):
        if {"first_name", "last_name"} & set(form.changed_data):
            form.instance.name_edited = True  # ORCID no longer changes it (#220)
        response = super().form_valid(form)
        kept = merge_same_orcid(self.object, user=self.request.user)
        if kept != self.object:
            messages.success(self.request, f"Même ORCID : fusionné dans « {kept} ».")
            return redirect("author_detail", pk=kept.pk)
        report_shared_orcid(self.request, self.object)
        return response

    def get_success_url(self):
        messages.success(self.request, f"« {self.object} » a été modifié.")
        return reverse("author_detail", args=[self.object.pk])


def report_shared_orcid(request, author):
    """An ORCID kept by several authors: they were declared different people."""
    if author.orcid and Author.objects.filter(orcid=author.orcid).exclude(pk=author.pk).exists():
        messages.warning(
            request,
            "Cet ORCID est aussi porté par des auteurs déclarés distincts : "
            "ils ne sont pas fusionnés, le cas est signalé dans « Conflits ».",
        )


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
        return redirect("author_merge_select")

    kept = authors[0]
    candidates = author_merge.candidate_values(authors)
    form = AuthorMergeConfirmForm(
        request.POST or None,
        initial=author_merge.default_values(candidates),
        candidates=candidates,
        orcid_conflict=author_merge.has_orcid_conflict(candidates),
    )
    if request.method == "POST" and form.is_valid():
        author_merge.merge_authors(kept, authors[1:], form.cleaned_data, user=request.user)
        messages.success(request, f"{len(authors)} auteurs fusionnés en « {kept} ».")
        kept = merge_same_orcid(kept, user=request.user)
        return redirect("author_detail", pk=kept.pk)

    return render(
        request, "references/authors_merge_confirm.html", {"form": form, "authors": authors}
    )


@login_required
def author_duplicates_view(request):
    groups = author_duplicates.duplicate_groups()
    return render(request, "references/author_duplicates.html", {"groups": groups})


@login_required
@require_POST
def author_duplicates_dismiss_view(request):
    """Declare the checked authors of a suggestion as different people."""
    pks = [pk for pk in request.POST.getlist("authors") if pk.isdigit()]
    authors = list(Author.objects.filter(pk__in=pks))
    if len(authors) < 2:
        messages.error(request, "Cochez au moins deux auteurs.")
    else:
        author_distinctions.declare_distinct(authors, request.user)
        names = ", ".join(str(author) for author in authors)
        messages.success(request, f"Ne seront plus proposés ensemble : {names}.")
    return redirect("author_duplicates")
