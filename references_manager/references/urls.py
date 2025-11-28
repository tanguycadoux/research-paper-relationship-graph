from django.urls import path

from .views import (index, fetch_crossref, trigger_import_publication,
                    add_to_user_refs, remove_from_user_refs, my_references, add_publication_to_user_refs_by_doi,
                    PublicationCreateView, PublicationDeleteView, PublicationDetailView, PublicationListView, PublicationUpdateView, RegisterView, AuthorListView)


urlpatterns = [
    path('', index, name="index"),

    path('publications/', PublicationListView.as_view(), name='publications_list'),
    path('authors/', AuthorListView.as_view(), name='authors_list'),

    path('publication/<int:pk>/', PublicationDetailView.as_view(), name='publication_detail'),
    path('publication/add/', PublicationCreateView.as_view(), name='publication_add'),
    path('publication/<int:pk>/edit/', PublicationUpdateView.as_view(), name='publication_edit'),
    path('publication/<int:pk>/delete/', PublicationDeleteView.as_view(), name='publication_delete'),
    path('publication/<int:pk>/crossref/', fetch_crossref, name='publication_crossref'),
    path('publication/<int:pk>/trigger_import/', trigger_import_publication, name='publication_trigger_import'),
    
    path('publication/<int:pk>/add_to_my_refs/', add_to_user_refs, name='add_publication_to_my_refs'),
    path('publication/<int:pk>/remove_from_my_refs/', remove_from_user_refs, name='remove_publication_from_my_refs'),
    path('publication/add_to_my_refs_by_doi/', add_publication_to_user_refs_by_doi, name='add_publication_to_user_refs_by_doi'),
    path('my_references/', my_references, name='my_references'),

    path("accounts/register/", RegisterView.as_view(), name="register"),
]
