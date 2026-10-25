from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import CitedReference, Publication, Tag, UserPublication
from references.services import suggestions, tags


class SuggestionTests(TestCase):
    """Suggestions by co-citation, for the whole corpus or a tag (#162)."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        cls.bob = User.objects.create_user("bob")
        cls.mine = [
            Publication.objects.create(title=f"Mien {i}", publication_date=date(2020 + i, 1, 1))
            for i in range(4)
        ]
        cls.entries = [
            UserPublication.objects.create(user=cls.alice, publication=pub) for pub in cls.mine
        ]
        cls.central = Publication.objects.create(title="Central")
        cls.shared = Publication.objects.create(title="Partagé")
        cls.once = Publication.objects.create(title="Cité une fois")
        cls.cite(cls.mine[0], cls.central, cls.shared)
        cls.cite(cls.mine[1], cls.central, cls.shared)
        cls.cite(cls.mine[2], cls.central)
        # Twice in the same bibliography: one citing publication, not enough.
        cls.cite(cls.mine[3], cls.once, cls.once)
        # A publication of the corpus cited by others is not a suggestion of the corpus.
        cls.cite(cls.mine[2], cls.mine[0])
        cls.cite(cls.mine[3], cls.mine[0])
        # Citations from outside the corpus do not count.
        stranger = Publication.objects.create(title="Hors corpus")
        cls.cite(stranger, cls.once)

    @classmethod
    def cite(cls, source, *targets):
        start = source.cited_references.count()
        for position, target in enumerate(targets, start):
            CitedReference.objects.create(source=source, target=target, position=position)

    def setUp(self):
        self.client.force_login(self.alice)

    def counts(self, user=None, tag=""):
        return {
            pub.title: pub.citing_count for pub in suggestions.co_cited(user or self.alice, tag)
        }

    def get(self, **params):
        return self.client.get(reverse("corpus_suggestions"), params)

    def test_cited_by_at_least_two_of_the_corpus_most_cited_first(self):
        self.assertEqual(list(self.counts().items()), [("Central", 3), ("Partagé", 2)])

    def test_same_bibliography_counts_once(self):
        self.cite(self.mine[3], self.shared, self.shared)
        self.assertEqual(self.counts()["Partagé"], 3)

    def test_other_users_have_their_own_suggestions(self):
        self.assertEqual(self.counts(self.bob), {})

    def test_a_tag_includes_its_descendants(self):
        tags.tag_entry(self.entries[0], "Projet")
        tags.tag_entry(self.entries[1], "Projet/Groupe")
        self.assertEqual(self.counts(tag="Projet"), {"Central": 2, "Partagé": 2})
        self.assertEqual(self.counts(tag="Projet/Groupe"), {})

    def test_in_a_tag_the_rest_of_the_corpus_is_suggested_and_marked(self):
        tags.tag_entry(self.entries[2], "Projet")
        tags.tag_entry(self.entries[3], "Projet")
        tags.tag_entry(self.entries[0], "Méthodes")
        response = self.get(tag="Projet")
        (pub,) = response.context["publications"]
        self.assertEqual(pub, self.mine[0])
        self.assertTrue(pub.in_corpus)
        self.assertEqual([tag.name for tag in pub.my_tags], ["Méthodes"])
        self.assertContains(response, "déjà dans mon corpus")
        self.assertContains(response, "Ajouter le tag « Projet »")

    def test_tagging_a_suggestion_takes_it_out_of_the_tag_suggestions(self):
        tags.tag_entry(self.entries[2], "Projet")
        tags.tag_entry(self.entries[3], "Projet")
        url = reverse("corpus_suggestions") + "?tag=Projet"
        response = self.client.post(
            reverse("corpus_tag", args=[self.mine[0].pk]), {"name": "Projet", "next": url}
        )
        self.assertRedirects(response, url)
        # Now in the tag, its own citations count.
        self.assertEqual(self.counts(tag="Projet"), {"Central": 2})

    def test_page_lists_the_citing_publications_newest_first(self):
        response = self.get()
        central = response.context["publications"][0]
        self.assertEqual(central.citing, [self.mine[2], self.mine[1], self.mine[0]])
        self.assertFalse(central.in_corpus)
        self.assertContains(response, "Ajouter à mes références, à lire")
        self.assertContains(response, 'popovertarget="citing-1"')
        self.assertContains(response, '<div popover id="citing-1"')

    def test_page_says_what_does_not_count(self):
        CitedReference.objects.create(source=self.mine[0], position=99, unstructured="Inconnu")
        response = self.get()
        self.assertEqual(response.context["context_count"], 4)
        self.assertContains(response, "1 de leurs références est encore à identifier")

    def test_unknown_tag_falls_back_on_the_corpus(self):
        response = self.get(tag="Disparu")
        self.assertEqual(response.context["active_tag"], "")
        self.assertEqual(len(response.context["publications"]), 2)
        self.assertContains(response, "Disparu » n&#x27;existe plus")

    def test_page_without_suggestions(self):
        self.client.force_login(self.bob)
        self.assertContains(self.get(), "Aucune publication n'est citée par 2")

    def test_page_is_private(self):
        self.client.logout()
        self.assertEqual(self.get().status_code, 302)

    def test_corpus_page_links_to_the_suggestions_of_its_tag(self):
        tags.tag_entry(self.entries[0], "Projet/Groupe")
        response = self.client.get(reverse("corpus"), {"tag": "Projet/Groupe"})
        self.assertContains(response, reverse("corpus_suggestions") + "?tag=Projet/Groupe")
        self.assertTrue(Tag.objects.filter(name="Projet/Groupe").exists())
