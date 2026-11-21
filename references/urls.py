from django.urls import path
from django.views.generic import RedirectView

from .views import (
    author_graphs,
    author_suggestions,
    authors,
    cited_references,
    conflicts,
    corpus,
    corpus_bulk,
    corpus_transfer,
    fetch_admin,
    fetch_progress,
    graph_images,
    graphs,
    home,
    keywords,
    publication_merge,
    publications,
    search,
    suggestions,
    title_search,
)

urlpatterns = [
    # Images of the graphs too large for the page (#328)
    path(
        "graph/image/<str:kind>/generate/",
        graph_images.generate_graph_image,
        name="graph_image_generate",
    ),
    path("graph/image/<str:kind>.svg", graph_images.graph_image_svg, name="graph_image_svg"),
    path(
        "graph/image/<str:kind>/status/",
        graph_images.graph_image_status,
        name="graph_image_status",
    ),
    # Progress of the requests in the queue (#379)
    path("queue/progress/", fetch_progress.fetch_progress, name="fetch_progress"),
    # Administration of the queue, reserved to the staff (#382)
    path("queue/", fetch_admin.fetch_queue_admin, name="fetch_queue_admin"),
    path("queue/<int:pk>/retry/", fetch_admin.fetch_request_retry, name="fetch_request_retry"),
    path("queue/<int:pk>/cancel/", fetch_admin.fetch_request_cancel, name="fetch_request_cancel"),
    path("", home.index, name="index"),
    path("search/", search.search, name="search"),
    # Publications
    path("publications/", publications.PublicationListView.as_view(), name="publication_list"),
    path(
        "publications/new/", publications.PublicationCreateView.as_view(), name="publication_create"
    ),
    # Find a publication by its title, to add it (#309)
    path("publications/by-title/", title_search.title_search_view, name="publication_title_search"),
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
    # Reached from the list of publications, as the graph of the authors from theirs.
    path("publications/graph/", graphs.base_graph_view, name="base_graph"),
    # Its former address, kept for the bookmarks.
    path("graph/", RedirectView.as_view(pattern_name="base_graph", permanent=True)),
    path(
        "publications/<int:pk>/references/import/",
        publications.import_publication_references,
        name="publication_import_references",
    ),
    path(
        "publications/<int:pk>/bulk/",
        corpus_bulk.publication_bulk_action,
        name="publication_bulk",
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
    # Authors of the base suggested while typing, in « Sans identifiant » (#259)
    path(
        "authors/suggestions/",
        author_suggestions.author_suggestions,
        name="author_suggestions",
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
    path("authors/<int:pk>/graph/", author_graphs.author_graph_view, name="author_graph"),
    path("authors/graph/", author_graphs.authors_graph_view, name="authors_graph"),
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
    # The map of its keywords (#418)
    path("corpus/keywords/", keywords.corpus_keywords, name="corpus_keywords"),
    path("corpus/bulk/", corpus_bulk.bulk_action, name="corpus_bulk"),
    path("corpus/export/json/", corpus_transfer.export_json, name="corpus_export_json"),
    path("corpus/export/bibtex/", corpus_transfer.export_bibtex, name="corpus_export_bibtex"),
    path("corpus/import/", corpus_transfer.import_file, name="corpus_import"),
    path(
        "corpus/import/report/close/",
        corpus_transfer.close_import_report,
        name="corpus_import_report_close",
    ),
    path(
        "corpus/add/",
        corpus.add_publication_to_user_refs_by_identifier,
        name="corpus_add_by_identifier",
    ),
    path("corpus/<int:pk>/status/", corpus.set_reading_status, name="corpus_reading_status"),
    path("corpus/<int:pk>/note/", corpus.set_note, name="corpus_note"),
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
