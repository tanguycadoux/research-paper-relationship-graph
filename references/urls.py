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
    search,
    suggestions,
)

urlpatterns = [
    path("", home.index, name="index"),
    path("search/", search.search, name="search"),
    # Publications
    path("publications/", publications.PublicationListView.as_view(), name="publication_list"),
    path(
        "publications/new/", publications.PublicationCreateView.as_view(), name="publication_create"
    ),
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
        "publications/<int:pk>/refresh/",
        publications.trigger_import_publication,
        name="publication_refresh",
    ),
    path(
        "publications/<int:pk>/incoming-citations/",
        publications.fetch_incoming_citations,
        name="publication_incoming_citations",
    ),
    path("publications/<int:pk>/graph/", graphs.pub_graph, name="publication_graph"),
    path("graph/", graphs.base_graph_view, name="base_graph"),
    path(
        "publications/<int:pk>/references/import/",
        publications.import_publication_references,
        name="publication_import_references",
    ),
    path(
        "publications/<int:pk>/merge/",
        publication_merge.merge_publication,
        name="publication_merge",
    ),
    path(
        "publications/<int:pk>/restore-sources/",
        publications.restore_publication_sources,
        name="publication_restore_sources",
    ),
    path(
        "publications/<int:pk>/references/<int:position>/identify/",
        cited_references.identify_reference,
        name="reference_identify",
    ),
    path(
        "publications/<int:pk>/references/<int:position>/candidate/",
        cited_references.choose_candidate,
        name="reference_candidate",
    ),
    path(
        "publications/<int:pk>/references/<int:position>/search-again/",
        cited_references.search_candidates_again,
        name="reference_search_again",
    ),
    path(
        "publications/<int:pk>/references/<int:position>/unidentifiable/",
        cited_references.toggle_unidentifiable,
        name="reference_unidentifiable",
    ),
    path(
        "publications/<int:pk>/references/<int:position>/skip/",
        cited_references.skip_reference,
        name="reference_skip",
    ),
    # Authors
    path("authors/", authors.AuthorListView.as_view(), name="author_list"),
    path("authors/<int:pk>/", authors.AuthorDetailView.as_view(), name="author_detail"),
    path("authors/<int:pk>/edit/", authors.AuthorUpdateView.as_view(), name="author_edit"),
    path("authors/<int:pk>/orcid/", authors.author_orcid_refresh_view, name="author_orcid_refresh"),
    path("authors/merge/", authors.author_merge_select_view, name="author_merge_select"),
    path("authors/duplicates/", authors.author_duplicates_view, name="author_duplicates"),
    path(
        "authors/duplicates/dismiss/",
        authors.author_duplicates_dismiss_view,
        name="author_duplicates_dismiss",
    ),
    path(
        "authors/merge/<str:ids>/",
        authors.author_merge_confirm_view,
        name="author_merge_confirm",
    ),
    # Contradictions between sources
    path("conflicts/", conflicts.conflicts_view, name="conflict_list"),
    path("conflicts/<int:pk>/resolve/", conflicts.resolve_conflict_view, name="conflict_resolve"),
    # Corpus of the current user
    path("corpus/", corpus.my_references, name="corpus"),
    path("corpus/graph/", graphs.my_refs_graph, name="corpus_graph"),
    path("corpus/export/json/", corpus_transfer.export_json, name="corpus_export_json"),
    path("corpus/export/bibtex/", corpus_transfer.export_bibtex, name="corpus_export_bibtex"),
    path("corpus/import/", corpus_transfer.import_file, name="corpus_import"),
    path(
        "corpus/add/",
        corpus.add_publication_to_user_refs_by_identifier,
        name="corpus_add_by_identifier",
    ),
    path("corpus/<int:pk>/status/", corpus.set_reading_status, name="corpus_reading_status"),
    path("corpus/suggestions/", suggestions.corpus_suggestions, name="corpus_suggestions"),
    path("corpus/tags/", corpus.manage_tags, name="tag_list"),
    path("corpus/tags/rename/", corpus.rename_tag, name="tag_rename"),
    path("corpus/tags/delete/", corpus.delete_tag, name="tag_delete"),
    path("corpus/<int:pk>/tags/", corpus.tag_publication, name="corpus_tag"),
    path(
        "corpus/<int:pk>/tags/<int:tag_pk>/remove/",
        corpus.untag_publication,
        name="corpus_untag",
    ),
    path(
        "corpus/<int:pk>/add/",
        corpus.add_to_user_refs,
        name="corpus_add",
    ),
    path(
        "corpus/<int:pk>/remove/",
        corpus.remove_from_user_refs,
        name="corpus_remove",
    ),
]
