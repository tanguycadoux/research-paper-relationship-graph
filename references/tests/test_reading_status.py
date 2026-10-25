from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Publication, UserPublication
from references.services import dashboard
from references.services.corpus_transfer import export_corpus, import_corpus

READ = UserPublication.ReadingStatus.READ
TO_READ = UserPublication.ReadingStatus.TO_READ
READING = UserPublication.ReadingStatus.READING


class ReadingStatusTests(TestCase):
    """The reading status of a publication of my corpus (#164)."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        cls.bob = User.objects.create_user("bob")
        cls.read = Publication.objects.create(doi="10.1000/read", title="Lue")
        cls.to_read = Publication.objects.create(doi="10.1000/to-read", title="À lire")
        cls.none = Publication.objects.create(doi="10.1000/none", title="Sans statut")
        for pub, status in ((cls.read, READ), (cls.to_read, TO_READ), (cls.none, "")):
            UserPublication.objects.create(user=cls.alice, publication=pub, reading_status=status)
        # Bob read the one Alice has still to read: his status must not leak into hers.
        UserPublication.objects.create(user=cls.bob, publication=cls.to_read, reading_status=READ)

    def setUp(self):
        self.client.force_login(self.alice)

    def entry(self, pub, user=None):
        return UserPublication.objects.get(user=user or self.alice, publication=pub)

    def titles(self, **params):
        response = self.client.get(reverse("corpus"), params)
        return [pub.title for pub in response.context["publications"]]

    def set_status(self, pub, status, **data):
        url = reverse("corpus_reading_status", args=[pub.pk])
        return self.client.post(url, {"status": status, **data}, follow=True)

    def test_new_entries_have_no_status(self):
        pub = Publication.objects.create(title="Nouvelle")
        entry = UserPublication.objects.create(user=self.alice, publication=pub)
        self.assertEqual(entry.reading_status, "")

    def test_status_is_set_and_reported(self):
        response = self.set_status(self.none, "reading", next=reverse("corpus"))
        self.assertEqual(self.entry(self.none).reading_status, READING)
        self.assertContains(response, "Statut de lecture de « Sans statut » : en cours.")
        self.assertEqual(response.redirect_chain[-1][0], reverse("corpus"))

    def test_status_is_removed(self):
        self.set_status(self.read, "")
        self.assertEqual(self.entry(self.read).reading_status, "")

    def test_unknown_status_is_refused(self):
        self.assertContains(self.set_status(self.read, "fini"), "Statut de lecture inconnu")
        self.assertEqual(self.entry(self.read).reading_status, READ)

    @patch("references.services.corpus.import_publication", side_effect=lambda pub, **_: pub)
    def test_only_my_own_entries(self, _import):
        outside = Publication.objects.create(title="Hors corpus")
        self.assertEqual(self.set_status(outside, "read").status_code, 404)
        self.set_status(self.to_read, "reading")
        self.assertEqual(self.entry(self.to_read, self.bob).reading_status, READ)

    def test_filter_by_status_ignores_other_users(self):
        self.assertEqual(self.titles(status="read"), ["Lue"])
        self.assertEqual(self.titles(status="to_read"), ["À lire"])
        self.assertEqual(self.titles(status="none"), ["Sans statut"])
        self.assertEqual(len(self.titles(status="nimporte")), 3)

    def test_sort_by_status_puts_the_publications_without_one_last(self):
        self.assertEqual(self.titles(sort="status"), ["À lire", "Lue", "Sans statut"])
        self.assertEqual(self.titles(sort="-status"), ["Lue", "À lire", "Sans statut"])

    def test_table_shows_the_current_status(self):
        response = self.client.get(reverse("corpus"))
        self.assertContains(response, f'id="reading-status-{self.read.pk}"')
        self.assertContains(response, "Statut de lecture de « Lue »")
        self.assertContains(response, '<option value="read" selected>Lu</option>', html=True)

    def test_other_tables_have_no_status_column(self):
        response = self.client.get(reverse("publication_list"))
        self.assertNotContains(response, "reading-status-")

    def test_publication_page_shows_the_form_only_in_my_corpus(self):
        url = reverse("publication_detail", args=[self.to_read.pk])
        option = '<option value="to_read" selected>À lire</option>'
        self.assertContains(self.client.get(url), option, html=True)
        self.client.force_login(get_user_model().objects.create_user("carol"))
        self.assertNotContains(self.client.get(url), "reading-status-")

    def test_dashboard_counts_each_status(self):
        figures = dashboard.corpus_figures(self.alice)["reading"]
        self.assertEqual(
            [(status["filter"], status["count"]) for status in figures],
            [("to_read", 1), ("reading", 0), ("read", 1), ("none", 1)],
        )
        response = self.client.get(reverse("index"))
        self.assertContains(response, f'href="{reverse("corpus")}?status=none"')


class ReadingStatusTransferTests(TestCase):
    """The status in the JSON export, version 2."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        cls.bob = User.objects.create_user("bob")
        cls.pub = Publication.objects.create(doi="10.1000/known", title="Connue")

    def import_into_bob(self, *entries, version=2):
        data = {**export_corpus(self.alice), "version": version, "publications": list(entries)}
        return import_corpus(self.bob, data)

    def status_of_bob(self):
        return UserPublication.objects.get(user=self.bob).reading_status

    def test_export_holds_the_status(self):
        UserPublication.objects.create(user=self.alice, publication=self.pub, reading_status=READ)
        data = export_corpus(self.alice)
        self.assertEqual(data["version"], 2)
        self.assertEqual(data["publications"][0]["status"], "read")

    def test_import_keeps_the_status_of_the_file(self):
        UserPublication.objects.create(user=self.bob, publication=self.pub)
        self.import_into_bob({"doi": "10.1000/known", "status": "reading"})
        self.assertEqual(self.status_of_bob(), READING)

    def test_import_never_replaces_a_status_chosen(self):
        UserPublication.objects.create(user=self.bob, publication=self.pub, reading_status=READ)
        self.import_into_bob({"doi": "10.1000/known", "status": "to_read"})
        self.assertEqual(self.status_of_bob(), READ)

    def test_unknown_status_and_version_1_are_accepted(self):
        UserPublication.objects.create(user=self.bob, publication=self.pub)
        report = self.import_into_bob({"doi": "10.1000/known", "status": "fini"})
        self.assertEqual(report.already_there, [self.pub])
        report = self.import_into_bob({"doi": "10.1000/known"}, version=1)
        self.assertEqual(report.already_there, [self.pub])
        self.assertEqual(self.status_of_bob(), "")
