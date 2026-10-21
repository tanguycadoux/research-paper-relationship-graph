from unittest.mock import patch

from django.db.models.signals import post_save
from django.test import TestCase

from references.models import Publication


class SignalRegistrationTests(TestCase):
    def test_post_save_receiver_is_connected_at_startup(self):
        # Must not import references.signals here: the app config is responsible for it.
        self.assertTrue(post_save.has_listeners(Publication))


@patch("references.services.importer.fetch_crossref_json", return_value=None)
class AutoImportSignalTests(TestCase):
    def test_creating_publication_with_doi_fetches_crossref(self, fetch):
        Publication.objects.create(doi="10.1000/abc")
        fetch.assert_called_once_with("10.1000/abc")

    def test_creating_publication_without_doi_does_not_fetch(self, fetch):
        Publication.objects.create(title="Sans DOI")
        fetch.assert_not_called()

    def test_updating_publication_does_not_fetch(self, fetch):
        pub = Publication.objects.create(title="Sans DOI")
        pub.doi = "10.1000/abc"
        pub.save()
        fetch.assert_not_called()
