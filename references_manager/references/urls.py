from django.urls import path

from .views import (index, fetch_crossref, trigger_import_publication,
                    PublicationCreateView, PublicationDeleteView, PublicationDetailView, PublicationListView, PublicationUpdateView)


urlpatterns = [
    path('', index, name="index"),
    path('publications/', PublicationListView.as_view(), name='publications_list'),
    path('publication/<int:pk>/', PublicationDetailView.as_view(), name='publication_detail'),
    path('publication/add/', PublicationCreateView.as_view(), name='publication_add'),
    path('publication/<int:pk>/edit/', PublicationUpdateView.as_view(), name='publication_edit'),
    path('publication/<int:pk>/delete/', PublicationDeleteView.as_view(), name='publication_delete'),
    path('publication/<int:pk>/crossref/', fetch_crossref, name='publication_crossref'),
    path('publication/<int:pk>/trigger_import/', trigger_import_publication, name='publication_trigger_import'),
]
