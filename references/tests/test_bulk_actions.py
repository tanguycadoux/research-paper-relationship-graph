from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Publication, Tag, UserPublication

READ = UserPublication.ReadingStatus.READ
TO_READ = UserPublication.ReadingStatus.TO_READ


class BulkActionsTests(TestCase):
    """The bulk actions of « Mon corpus » (#287)."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        cls.bob = User.objects.create_user("bob")
        cls.first = Publication.objects.create(doi="10.1000/first", title="Première")
        cls.second = Publication.objects.create(doi="10.1000/second", title="Deuxième")
        cls.other = Publication.objects.create(doi="10.1000/other", title="Autre")
        for pub in (cls.first, cls.second, cls.other):
            UserPublication.objects.create(user=cls.alice, publication=pub)
        cls.bobs = Publication.objects.create(doi="10.1000/bob", title="De Bob")
        UserPublication.objects.create(user=cls.bob, publication=cls.bobs)

    def setUp(self):
        self.client.force_login(self.alice)

    def act(self, action, pubs, **data):
        checked = [pub.pk for pub in pubs]
        data = {"action": action, "publication": checked, "next": reverse("corpus"), **data}
        return self.client.post(reverse("corpus_bulk"), data, follow=True)

    def entry(self, pub, user=None):
        return UserPublication.objects.get(user=user or self.alice, publication=pub)

    def tag_names(self, pub, user=None):
        return [tag.name for tag in self.entry(pub, user).tags.all()]

    def test_the_page_has_the_bar_and_a_checkbox_per_row(self):
        response = self.client.get(reverse("corpus"))
        self.assertContains(response, 'id="bulk-actions"')
        self.assertContains(response, 'form="bulk-actions"', count=3)
        self.assertContains(response, 'aria-label="Cocher « Première »"')
        # The buttons are there, enabled: the page works without JavaScript.
        self.assertContains(response, 'name="action" value="tag"')
        self.assertContains(response, 'name="action" value="status"')
        self.assertContains(response, 'name="action" value="remove"')

    def test_checked_publications_are_tagged(self):
        response = self.act("tag", [self.first, self.second], name="Projet/Groupe")
        self.assertEqual(self.tag_names(self.first), ["Projet/Groupe"])
        self.assertEqual(self.tag_names(self.second), ["Projet/Groupe"])
        self.assertEqual(self.tag_names(self.other), [])
        self.assertContains(response, "2 publications taguées « Projet › Groupe ».")
        self.assertEqual(response.redirect_chain[-1][0], reverse("corpus"))

    def test_a_more_precise_tag_is_kept_and_counted(self):
        entry = self.entry(self.first)
        entry.tags.add(Tag.objects.create(user=self.alice, name="Projet/Groupe"))
        response = self.act("tag", [self.first, self.second], name="projet")
        self.assertEqual(self.tag_names(self.first), ["Projet/Groupe"])
        self.assertEqual(self.tag_names(self.second), ["Projet"])
        self.assertContains(response, "1 publication taguée « Projet ».")
        self.assertContains(response, "1 autre a déjà un tag plus précis")

    def test_an_empty_tag_does_nothing(self):
        response = self.act("tag", [self.first], name="  ")
        self.assertEqual(self.tag_names(self.first), [])
        self.assertContains(response, "Écrivez le nom du tag")

    def test_the_status_of_checked_publications_changes(self):
        response = self.act("status", [self.first, self.second], status=READ)
        self.assertEqual(self.entry(self.first).reading_status, READ)
        self.assertEqual(self.entry(self.second).reading_status, READ)
        self.assertEqual(self.entry(self.other).reading_status, "")
        self.assertContains(response, "Statut de lecture de 2 publications : lu.")

    @patch(
        "references.services.corpus.entries.import_publication", side_effect=lambda pub, **_: pub
    )
    def test_leaving_to_read_imports_the_bibliographies(self, import_publication):
        UserPublication.objects.filter(user=self.alice).update(reading_status=TO_READ)
        response = self.act("status", [self.first, self.second], status=READ)
        self.assertEqual(import_publication.call_count, 2)
        self.assertContains(response, "Bibliographies importées : 2.")

    @patch("references.services.corpus.bulk.fetch_queue.worker_alive", return_value=True)
    def test_with_a_worker_the_bibliographies_are_queued(self, _):
        UserPublication.objects.filter(user=self.alice).update(reading_status=TO_READ)
        with patch("references.services.corpus.entries.import_publication") as import_publication:
            response = self.act("status", [self.first], status=READ)
        import_publication.assert_not_called()
        self.assertContains(response, "Bibliographies en file de récupération : 1.")

    def test_an_unknown_status_does_nothing(self):
        response = self.act("status", [self.first], status="burnt")
        self.assertEqual(self.entry(self.first).reading_status, "")
        self.assertContains(response, "Statut de lecture inconnu.")

    def test_checked_publications_are_removed_with_their_tags(self):
        entry = self.entry(self.first)
        entry.tags.add(Tag.objects.create(user=self.alice, name="Seul"))
        response = self.act("remove", [self.first, self.second])
        remaining = UserPublication.objects.filter(user=self.alice)
        self.assertEqual([e.publication for e in remaining], [self.other])
        self.assertFalse(Tag.objects.filter(user=self.alice, name="Seul").exists())
        # What is lost is said (#408).
        self.assertContains(response, "2 publications retirées de votre corpus, avec 1 tag.")
        # The publications stay in the database: only the entries go.
        self.assertTrue(Publication.objects.filter(pk=self.first.pk).exists())

    def test_nothing_checked_does_nothing(self):
        for action, data in (("tag", {"name": "X"}), ("status", {"status": READ}), ("remove", {})):
            with self.subTest(action=action):
                response = self.act(action, [], **data)
                self.assertContains(response, "Cochez au moins une publication.")
        self.assertEqual(UserPublication.objects.filter(user=self.alice).count(), 3)
        self.assertFalse(Tag.objects.exists())

    def test_another_users_publication_cannot_be_touched(self):
        for action, data in (("tag", {"name": "X"}), ("status", {"status": READ}), ("remove", {})):
            with self.subTest(action=action):
                response = self.act(action, [self.first, self.bobs], **data)
                self.assertContains(response, "pas dans votre corpus : rien n&#x27;a été fait")
        # Neither Bob's entry nor Alice's own checked one changed.
        self.assertEqual(self.entry(self.bobs, self.bob).reading_status, "")
        self.assertEqual(self.tag_names(self.bobs, self.bob), [])
        self.assertEqual(self.entry(self.first).reading_status, "")
        self.assertEqual(UserPublication.objects.count(), 4)
        self.assertFalse(Tag.objects.exists())

    def test_a_publication_outside_any_corpus_cannot_be_added(self):
        stranger = Publication.objects.create(doi="10.1000/stranger", title="Étrangère")
        self.act("tag", [stranger], name="X")
        self.assertFalse(UserPublication.objects.filter(publication=stranger).exists())

    def test_invalid_ids_and_unknown_actions_are_refused(self):
        response = self.act("tag", [], publication=["abc"], name="X")
        self.assertContains(response, "Cochez au moins une publication.")
        response = self.act("delete_everything", [self.first])
        self.assertContains(response, "Action inconnue.")
        self.assertEqual(UserPublication.objects.filter(user=self.alice).count(), 3)

    def test_login_and_post_are_required(self):
        self.assertEqual(self.client.get(reverse("corpus_bulk")).status_code, 405)
        self.client.logout()
        response = self.client.post(reverse("corpus_bulk"), {"action": "remove"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(UserPublication.objects.count(), 4)

    def test_back_to_the_filtered_page(self):
        back = reverse("corpus") + "?tag=Projet"
        response = self.act("status", [self.first], status=READ, next=back)
        self.assertEqual(response.redirect_chain[-1][0], back)
