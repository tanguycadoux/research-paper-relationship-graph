from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Publication, Tag, UserPublication
from references.services.display.publication_table import corpus_ids

READ = UserPublication.ReadingStatus.READ


class RemoveConfirmationTests(TestCase):
    """Taking a publication away from my corpus, when it loses tags or a status (#280)."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice")
        cls.bare = Publication.objects.create(doi="10.1000/bare", title="Nue")
        cls.tagged = Publication.objects.create(doi="10.1000/tagged", title="Taguée")
        cls.read = Publication.objects.create(doi="10.1000/read", title="Lue")
        UserPublication.objects.create(user=cls.alice, publication=cls.bare)
        entry = UserPublication.objects.create(user=cls.alice, publication=cls.tagged)
        entry.tags.add(
            Tag.objects.create(user=cls.alice, name="Revue/Test"),
            Tag.objects.create(user=cls.alice, name="Projet"),
        )
        UserPublication.objects.create(user=cls.alice, publication=cls.read, reading_status=READ)

    def setUp(self):
        self.client.force_login(self.alice)

    def detail(self, pub):
        return self.client.get(reverse("publication_detail", args=[pub.pk]))

    def test_corpus_ids_know_what_a_removal_loses_in_one_query(self):
        with self.assertNumQueries(1):
            ids = corpus_ids(self.alice)
        self.assertEqual(ids, {self.bare.pk, self.tagged.pk, self.read.pk})
        self.assertEqual(ids.with_tags, {self.tagged.pk})
        self.assertEqual(ids.with_status, {self.read.pk})

    def test_without_tags_or_status_the_removal_is_immediate(self):
        response = self.detail(self.bare)
        self.assertNotContains(response, f'popovertarget="remove-{self.bare.pk}"')
        self.assertContains(response, "Retirer de mon corpus")

    def test_with_tags_or_a_status_it_is_confirmed(self):
        response = self.detail(self.tagged)
        self.assertContains(response, f'popovertarget="remove-{self.tagged.pk}"')
        self.assertContains(response, "Ses tags seront perdus.")
        self.assertContains(self.detail(self.read), "Son statut de lecture sera perdu.")

    def test_the_tables_confirm_too(self):
        response = self.client.get(reverse("publication_list"))
        self.assertContains(response, f'popovertarget="remove-{self.tagged.pk}"')
        self.assertNotContains(response, f'popovertarget="remove-{self.bare.pk}"')

    def test_the_message_says_what_was_lost(self):
        url = reverse("corpus_remove", args=[self.tagged.pk])
        response = self.client.post(url, follow=True)
        self.assertContains(
            response,
            "« Taguée » a été retiré de votre corpus, avec ses tags « Projet », « Revue › Test ».",
        )
        url = reverse("corpus_remove", args=[self.read.pk])
        response = self.client.post(url, follow=True)
        self.assertContains(response, "a été retiré de votre corpus, avec son statut « Lu ».")
        self.assertFalse(
            UserPublication.objects.filter(user=self.alice).exclude(publication=self.bare)
        )
