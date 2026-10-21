from django.urls import path

from .views import (
    authors,
    cited_references,
    conflicts,
    corpus,
    corpus_transfer,
    graphs,
    home,
    publication_merge,
    publications,
)

urlpatterns = [
    path("", home.index, name="index"),
    # Publications
    path("publications/", publications.PublicationListView.as_view(), name="publications_list"),
    path("publications/add/", publications.PublicationCreateView.as_view(), name="publication_add"),
    path(
        "publications/<int:pk>/",
        publications.PublicationDetailView.as_view(),
        name="publication_detail",
    ),
    path(
        "publications/<int:pk>/edit/",
        publications.PublicationUpdateView.as_view(),
        name="publication_edit",
    ),
    path(
        "publications/<int:pk>/metadata/",
        publications.publication_metadata,
        name="publication_metadata",
    ),
    path(
        "publications/<int:pk>/import/",
        publications.trigger_import_publication,
        name="publication_trigger_import",
    ),
    path("publications/<int:pk>/graph/", graphs.pub_graph, name="publication_graph"),
    path(
        "publications/<int:pk>/merge/",
        publication_merge.merge_publication,
        name="publication_merge",
    ),
    path(
        "publications/<int:pk>/references/<int:position>/identify/",
        cited_references.identify_reference,
        name="reference_identify",
    ),
    # Authors
    path("authors/", authors.AuthorListView.as_view(), name="authors_list"),
    path("authors/<int:pk>/", authors.AuthorDetailView.as_view(), name="author_detail"),
    path("authors/<int:pk>/edit/", authors.AuthorUpdateView.as_view(), name="author_edit"),
    path("authors/merge/", authors.author_merge_select_view, name="authors_merge_select"),
    path("authors/duplicates/", authors.author_duplicates_view, name="author_duplicates"),
    path(
        "authors/duplicates/dismiss/",
        authors.author_duplicates_dismiss_view,
        name="author_duplicates_dismiss",
    ),
    path(
        "authors/merge/confirm/<str:ids>/",
        authors.author_merge_confirm_view,
        name="author_merge_confirm",
    ),
    # Contradictions between sources
    path("conflicts/", conflicts.conflicts_view, name="conflicts"),
    path("conflicts/<int:pk>/resolve/", conflicts.resolve_conflict_view, name="resolve_conflict"),
    # Corpus of the current user
    path("my-references/", corpus.my_references, name="my_references"),
    path("my-references/graph/", graphs.my_refs_graph, name="my_refs_graph"),
    path("my-references/export/json/", corpus_transfer.export_json, name="corpus_export_json"),
    path(
        "my-references/export/bibtex/", corpus_transfer.export_bibtex, name="corpus_export_bibtex"
    ),
    path("my-references/import/", corpus_transfer.import_json, name="corpus_import"),
    path(
        "my-references/add-by-doi/",
        corpus.add_publication_to_user_refs_by_doi,
        name="add_publication_to_user_refs_by_doi",
    ),
    path(
        "my-references/<int:pk>/add/",
        corpus.add_to_user_refs,
        name="add_publication_to_my_refs",
    ),
    path(
        "my-references/<int:pk>/remove/",
        corpus.remove_from_user_refs,
        name="remove_publication_from_my_refs",
    ),
]
