from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView, UpdateView

from ..forms import AuthorForm, AuthorMergeConfirmForm, AuthorMergeSelectForm
from ..models import Author, FetchRequest, Publication
from ..services.corrections import author_distinctions, author_duplicates, author_merge
from ..services.display import filters
from ..services.display.publication_table import corpus_ids, for_publication_table
from ..services.display.search import parse, search_authors
from ..services.display.sorting import AUTHORS
from ..services.imports import fetch_queue
from ..services.imports.orcid_merge import merge_same_orcid
from ..services.imports.orcid_profile import orcid_profile, refresh_orcid_record
from ..services.imports.organizations import organization_groups
from .pagination import PageMixin, page_of
from .redirects import safe_next


class AuthorListView(PageMixin, ListView):
    model = Author
    template_name = "references/authors_list.html"
    context_object_name = "authors"

    def get_queryset(self):
        self.sort = AUTHORS.read(self.request.GET.get("sort"))
        self.active_filters = filters.AUTHORS.read(self.request.GET)
        return AUTHORS.apply(
            filters.AUTHORS.apply(Author.objects.all(), self.active_filters), self.sort
        )

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "sorting": AUTHORS,
            "sort": self.sort,
            "filters": filters.AUTHORS,
            "active_filters": self.active_filters,
        }


class AuthorDetailView(DetailView):
    model = Author

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # pk__in: after a merge, one author can hold several slots of a publication,
        # which a join would count twice (rows and badges).
        context["publications"] = for_publication_table(
            Publication.objects.filter(pk__in=self.object.publications.values("pk"))
        ).order_by("-publication_date", "readable_title")
        context["user_pub_ids"] = corpus_ids(self.request.user)
        context["organization_groups"] = organization_groups(self.object)
        context["merges"] = self.object.merges.select_related("merged_by")
        context["orcid_profile"] = orcid_profile(self.object)
        # Its ORCID profile still to come from the queue: said, and reloaded once there (#380).
        if self.request.user.is_authenticated and fetch_queue.author_pending(self.object):
            context["fetch_pending_author"] = self.object.pk
        return context


@login_required
@require_POST
def author_orcid_refresh_view(request, pk):
    """Ask ORCID for the public record of the author (on demand only, #59)."""
    author = get_object_or_404(Author, pk=pk)
    if not author.orcid:
        messages.error(request, "Cet auteur n'a pas d'ORCID.")
    elif fetch_queue.worker_alive():
        fetch_queue.enqueue_action(
            FetchRequest.Action.ORCID_PROFILE, request.user, author=author, identifier=author.orcid
        )
        messages.success(request, "Profil ORCID en file de récupération.")
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
    """
    Choose the authors to merge (#271): a search (name or ORCID) in pages of 50, and the
    authors chosen kept on top, in the URL (?selected=3,8), so that the choice survives
    the search and the pages. Nothing changes before the confirmation. A POST (the
    probable duplicates, with their boxes) goes to the confirmation at once.
    """
    if request.method == "POST":
        form = AuthorMergeSelectForm(request.POST)
        if form.is_valid():
            ids = [a.id for a in form.cleaned_data["authors"]]
            confirm_url = reverse("author_merge_confirm", args=[",".join(map(str, ids))])
            back = safe_next(request, request.POST.get("next", ""))
            return redirect(with_next(confirm_url, back) if back else confirm_url)
        messages.error(request, "Veuillez sélectionner au moins deux auteurs.")
    text = request.GET.get("q", "").strip()
    selected = authors_from_ids(request.GET.get("selected", ""))
    selected_ids = [author.pk for author in selected]
    found = search_authors(parse(text)) if text else Author.objects.all()
    found = (
        found.exclude(pk__in=selected_ids)
        .annotate(publication_count=Count("publications", distinct=True))
        .order_by("last_name", "first_name", "pk")
    )
    page = page_of(request, found, MERGE_PAGE_SIZE)
    for author in page.object_list:
        author.add_url = selection_url(request, [*selected_ids, author.pk])
    for author in selected:
        author.remove_url = selection_url(request, [pk for pk in selected_ids if pk != author.pk])
    context = {
        "q": text,
        "selected": selected,
        "selected_ids": ",".join(map(str, selected_ids)),
        "page_obj": page,
        "authors": page.object_list,
        "confirm_url": (
            with_next(
                reverse("author_merge_confirm", args=[",".join(map(str, selected_ids))]),
                search_url(request),
            )
            if len(selected) >= 2
            else ""
        ),
    }
    return render(request, "references/authors_merge_select.html", context)


MERGE_PAGE_SIZE = 50


def search_url(request):
    """This page with its search, without the selection: where a merge comes back (#388)."""
    query = request.GET.copy()
    for name in ("page", "selected"):
        query.pop(name, None)
    url = reverse("author_merge_select")
    return f"{url}?{query.urlencode()}" if query else url


def with_next(url, next_url):
    return f"{url}?{urlencode({'next': next_url})}"


def selection_url(request, ids):
    """The same page with another selection: the search kept, back to its first page."""
    query = request.GET.copy()
    query.pop("page", None)
    if ids:
        query["selected"] = ",".join(map(str, ids))
    else:
        query.pop("selected", None)
    return f"?{query.urlencode()}"


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
    # Back where the merge started (#388): the search, or the page of duplicates.
    back = safe_next(request, request.GET.get("next", "")) or reverse("author_merge_select")
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
        final = merge_same_orcid(kept, user=request.user)
        if final != kept:
            messages.success(request, f"Même ORCID : fusionné aussi dans « {final} ».")
        return redirect(back)

    return render(
        request,
        "references/authors_merge_confirm.html",
        {"form": form, "authors": authors, "back_url": back},
    )


@login_required
def author_duplicates_view(request):
    """The probable duplicates, the most likely first, in pages of 50 groups (#270)."""
    page = page_of(request, author_duplicates.duplicate_groups(), DUPLICATES_PAGE_SIZE)
    return render(
        request, "references/author_duplicates.html", {"groups": page.object_list, "page_obj": page}
    )


DUPLICATES_PAGE_SIZE = 50


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
    # Back to the same page of suggestions.
    page = request.POST.get("page", "")
    url = reverse("author_duplicates")
    return redirect(f"{url}?page={page}" if page.isdigit() else url)
