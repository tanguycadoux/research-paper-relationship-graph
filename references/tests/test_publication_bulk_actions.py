from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, FetchRequest, Publication, Tag, UserPublication
from references.services.display.publication_page import REFERENCES_SHOWN

READ = UserPublication.ReadingStatus.READ
TO_READ = UserPublication.ReadingStatus.TO_READ
IMPORT = "references.services.corpus.entries.import_publication"


class PublicationBulkActionsTests(TestCase):
    """The bulk actions of the references and « Cité par » of a publication (#408)."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        cls.bob = User.objects.create_user("bob")
        cls.pub = Publication.objects.create(doi="10.1000/pub", title="L'article")
        cls.cited = Publication.objects.create(doi="10.1000/cited", title="Citée")
        cls.kept = Publication.objects.create(doi="10.1000/kept", title="Déjà là")
        cls.citing = Publication.objects.create(doi="10.1000/citing", title="Citante")
        cls.stranger = Publication.objects.create(doi="10.1000/stranger", title="Étrangère")
        CitedReference.objects.create(source=cls.pub, target=cls.cited, position=0)
        CitedReference.objects.create(source=cls.pub, target=cls.kept, position=1)
        CitedReference.objects.create(source=cls.pub, position=2, unstructured="Inconnue, 1999.")
        CitedReference.objects.create(source=cls.citing, target=cls.pub, position=0)
        UserPublication.objects.create(user=cls.alice, publication=cls.kept)
        UserPublication.objects.create(user=cls.bob, publication=cls.cited)

    def setUp(self):
        self.client.force_login(self.alice)

    def page(self, **params):
        return self.client.get(reverse("publication_detail", args=[self.pub.pk]), params)

    def act(self, action, pubs, **data):
        back = reverse("publication_detail", args=[self.pub.pk]) + "#references-title"
        data = {"action": action, "publication": [p.pk for p in pubs], "next": back, **data}
        return self.client.post(reverse("publication_bulk", args=[self.pub.pk]), data)

    def follow(self, action, pubs, **data):
        response = self.act(action, pubs, **data)
        return self.client.get(response.url)

    def entry(self, pub, user=None):
        return UserPublication.objects.filter(user=user or self.alice, publication=pub).first()

    def tag_names(self, pub, user=None):
        return [tag.name for tag in self.entry(pub, user).tags.all()]

    def test_two_bars_on_the_page(self):
        response = self.page()
        for form_id in ("references-actions", "cited-by-actions"):
            with self.subTest(form_id=form_id):
                self.assertContains(response, f'id="{form_id}"')
                self.assertContains(response, f'data-bulk-all="{form_id}"')
                self.assertContains(response, f'id="{form_id}-tag"')
                self.assertContains(response, f'popovertarget="{form_id}-remove"')
        self.assertContains(response, 'form="cited-by-actions"', count=1)
        self.assertContains(response, 'name="action" value="add"', count=2)
        self.assertContains(response, reverse("publication_bulk", args=[self.pub.pk]), count=2)
        self.assertContains(response, "js/bulk_actions.js")

    def test_both_bars_fold_with_the_script(self):
        # Folded by bulk_actions.js while nothing is checked; served unfolded (#410).
        response = self.page()
        self.assertContains(response, "data-bulk-collapsible=", count=2)
        self.assertContains(response, "data-bulk-more", count=2)
        self.assertNotContains(response, "data-bulk-folded ")
        self.assertNotContains(response, "data-bulk-more hidden")

    def test_the_help_is_in_the_part_folded(self):
        response = self.page()
        html = response.content.decode()
        help_text = "« Ajouter à mon corpus » leur donne aussi"
        self.assertEqual(html.count(help_text), 2)
        for form_id in ("references-actions", "cited-by-actions"):
            with self.subTest(form_id=form_id):
                form = html[html.index(f'id="{form_id}"') :]
                form = form[: form.index("</form>")]
                more = form[form.index("data-bulk-more") : form.index(f'id="{form_id}-remove"')]
                self.assertIn(help_text, more)

    def test_each_tag_field_suggests_the_users_tags(self):
        Tag.objects.create(user=self.alice, name="Projet/Groupe")
        response = self.page()
        for form_id in ("references-actions", "cited-by-actions"):
            with self.subTest(form_id=form_id):
                self.assertContains(response, f'list="{form_id}-known-tags"')
                self.assertContains(response, f'<datalist id="{form_id}-known-tags">')
        self.assertContains(response, '<option value="Projet/Groupe"></option>', count=2)

    def test_only_identified_references_have_a_checkbox(self):
        response = self.page()
        self.assertContains(response, 'form="references-actions"', count=2)
        self.assertContains(response, f'value="{self.cited.pk}"\n')
        self.assertContains(response, 'aria-label="Cocher « Citée »"')

    def test_a_visitor_has_neither_boxes_nor_bars(self):
        self.client.logout()
        response = self.page()
        self.assertNotContains(response, "data-bulk")
        self.assertNotContains(response, "js/bulk_actions.js")
        self.assertContains(response, "Citante")

    def test_no_bar_without_an_identified_reference(self):
        CitedReference.objects.filter(source=self.pub).update(target=None)
        response = self.page()
        self.assertNotContains(response, 'id="references-actions"')
        self.assertContains(response, 'id="cited-by-actions"')

    def test_the_unfolded_references_have_their_box(self):
        extra = [
            Publication.objects.create(doi=f"10.1000/extra{i}", title=f"Extra {i}")
            for i in range(REFERENCES_SHOWN)
        ]
        for i, target in enumerate(extra, start=3):
            CitedReference.objects.create(source=self.pub, target=target, position=i)
        last = f'aria-label="Cocher « {extra[-1]} »"'
        self.assertNotContains(self.page(), last)
        response = self.page(references="toutes")
        self.assertContains(response, last)
        # Back to the unfolded list after an action.
        self.assertContains(response, "?references=toutes#references-title")

    @patch(IMPORT, side_effect=lambda pub, **_: pub)
    def test_checked_publications_are_added(self, import_publication):
        response = self.follow("add", [self.cited, self.citing])
        self.assertEqual(self.entry(self.cited).reading_status, "")
        self.assertIsNotNone(self.entry(self.citing))
        self.assertEqual(import_publication.call_count, 2)
        self.assertContains(response, "2 publications ajoutées.")
        # Bob's entry of the same publication is his own.
        self.assertIsNotNone(self.entry(self.cited, self.bob))

    @patch(IMPORT, side_effect=lambda pub, **_: pub)
    def test_added_to_read_with_a_tag(self, import_publication):
        response = self.follow("add", [self.cited, self.kept], status=TO_READ, name="Projet/A")
        self.assertEqual(self.entry(self.cited).reading_status, TO_READ)
        # The one already there keeps its status, gets the tag, and is not imported again.
        self.assertEqual(self.entry(self.kept).reading_status, "")
        self.assertEqual(self.tag_names(self.cited), ["Projet/A"])
        self.assertEqual(self.tag_names(self.kept), ["Projet/A"])
        import_publication.assert_called_once_with(self.cited, with_references=False)
        # One sentence (#411).
        self.assertContains(
            response,
            "1 publication ajoutée, à lire ; 1 autre y était déjà ; "
            "2 publications taguées « Projet › A ».",
        )

    def test_already_in_the_corpus_is_not_an_error(self):
        with patch(IMPORT) as import_publication:
            response = self.follow("add", [self.kept])
        import_publication.assert_not_called()
        self.assertContains(response, "Aucune publication ajoutée ; elle y était déjà.")

    @patch("references.services.corpus.bulk.fetch_queue.worker_alive", return_value=True)
    def test_with_a_worker_the_data_is_queued(self, _):
        with patch(IMPORT) as import_publication:
            response = self.follow("add", [self.cited])
        import_publication.assert_not_called()
        self.assertTrue(FetchRequest.objects.filter(publication=self.cited).exists())
        # The queue has its own toast (#411).
        self.assertContains(response, "1 publication ajoutée.")
        self.assertNotContains(response, "Données en file")

    @patch(IMPORT, return_value=None)
    def test_data_not_retrieved_is_said(self, _):
        response = self.follow("add", [self.cited])
        self.assertIsNotNone(self.entry(self.cited))
        self.assertContains(response, "1 publication n&#x27;a pas pu être récupérée")

    def test_a_too_long_tag_adds_nothing(self):
        with patch(IMPORT) as import_publication:
            response = self.follow("add", [self.cited], name="x" * 500)
        import_publication.assert_not_called()
        self.assertIsNone(self.entry(self.cited))
        self.assertContains(response, "Un tag ne dépasse pas")

    def test_tag_status_and_removal_leave_aside_those_out_of_the_corpus(self):
        response = self.follow("tag", [self.kept, self.cited], name="Lu")
        self.assertEqual(self.tag_names(self.kept), ["Lu"])
        self.assertIsNone(self.entry(self.cited))
        self.assertContains(response, "1 publication taguée « Lu ».")
        self.assertContains(
            response, "1 publication cochée n&#x27;est pas dans votre corpus : elle a été laissée"
        )
        response = self.follow("status", [self.kept, self.cited, self.citing], status=READ)
        self.assertEqual(self.entry(self.kept).reading_status, READ)
        self.assertContains(response, "2 publications cochées ne sont pas dans votre corpus")
        self.assertIsNone(self.entry(self.citing))

    def test_none_in_the_corpus_does_nothing(self):
        response = self.follow("remove", [self.cited, self.citing])
        self.assertContains(response, "Aucune publication cochée n&#x27;est dans votre corpus")
        # Bob's entry stays: nobody acts on another user's corpus.
        self.assertIsNotNone(self.entry(self.cited, self.bob))
        self.assertEqual(UserPublication.objects.count(), 2)

    def test_another_users_corpus_is_never_touched(self):
        for action, data in (("tag", {"name": "X"}), ("status", {"status": READ}), ("remove", {})):
            with self.subTest(action=action):
                self.act(action, [self.cited, self.kept], **data)
                self.assertEqual(self.entry(self.cited, self.bob).reading_status, "")
                self.assertEqual(self.tag_names(self.cited, self.bob), [])
        self.assertFalse(Tag.objects.filter(user=self.bob).exists())

    def test_removal_says_what_is_lost(self):
        UserPublication.objects.create(
            user=self.alice, publication=self.citing, reading_status=READ, note="À relire."
        )
        self.entry(self.kept).tags.add(Tag.objects.create(user=self.alice, name="Projet"))
        response = self.follow("remove", [self.kept, self.citing, self.cited])
        self.assertEqual(UserPublication.objects.filter(user=self.alice).count(), 0)
        self.assertContains(
            response,
            "2 publications retirées de votre corpus, avec 1 tag, 1 statut de lecture et 1 note.",
        )
        self.assertContains(response, "1 publication cochée n&#x27;est pas dans votre corpus")

    def test_a_publication_not_listed_is_dropped(self):
        with patch(IMPORT) as import_publication:
            response = self.follow("add", [self.stranger])
        import_publication.assert_not_called()
        self.assertIsNone(self.entry(self.stranger))
        self.assertContains(response, "Cochez au moins une publication.")

    def test_an_unidentified_reference_cannot_be_checked(self):
        # Its row has no box (two for three references), and nothing else can stand for it.
        self.assertContains(self.page(), 'form="references-actions"', count=2)
        response = self.follow("add", [], publication=["", "abc"])
        self.assertContains(response, "Cochez au moins une publication.")
        self.assertEqual(UserPublication.objects.filter(user=self.alice).count(), 1)

    def test_back_to_the_list(self):
        back = (
            reverse("publication_detail", args=[self.pub.pk]) + "?references=toutes#cited-by-title"
        )
        response = self.act("tag", [self.kept], name="X", next=back)
        self.assertEqual(response.url, back)

    def test_an_external_next_is_refused(self):
        response = self.act("tag", [self.kept], name="X", next="https://example.com/")
        self.assertEqual(response.url, reverse("publication_detail", args=[self.pub.pk]))

    def test_unknown_action_login_and_post(self):
        response = self.follow("delete_everything", [self.kept])
        self.assertContains(response, "Action inconnue.")
        url = reverse("publication_bulk", args=[self.pub.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.logout()
        self.client.post(url, {"action": "remove", "publication": [self.kept.pk]})
        self.assertIsNotNone(self.entry(self.kept))
        missing = reverse("publication_bulk", args=[999999])
        self.client.force_login(self.alice)
        self.assertEqual(self.client.post(missing, {"action": "tag"}).status_code, 404)
