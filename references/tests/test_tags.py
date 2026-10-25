from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import Publication, Tag, UserPublication
from references.services import tags
from references.services.corpus_transfer import (
    EXPORT_FORMAT,
    corpus_bibtex,
    export_corpus,
    import_corpus,
)


class PathTests(SimpleTestCase):
    def test_clean_path(self):
        self.assertEqual(tags.clean_path("  Projet A /  Groupe   A/ "), "Projet A/Groupe A")
        self.assertEqual(tags.clean_path("//"), "")

    def test_label_and_ancestors(self):
        self.assertEqual(tags.label("A/B/C"), "A › B › C")
        self.assertEqual(tags.ancestors_and_self("A/B/C"), ["A", "A/B", "A/B/C"])


class TagTests(TestCase):
    """Hierarchical tags of a user's corpus (#130)."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        cls.bob = User.objects.create_user("bob")
        cls.pubs = [Publication.objects.create(doi=f"10.1000/{i}", title=f"P{i}") for i in range(4)]
        cls.entries = [
            UserPublication.objects.create(user=cls.alice, publication=pub) for pub in cls.pubs
        ]

    def setUp(self):
        self.client.force_login(self.alice)

    def names(self, entry):
        return sorted(entry.tags.values_list("name", flat=True))

    def titles(self, **params):
        response = self.client.get(reverse("corpus"), params)
        return sorted(pub.title for pub in response.context["publications"])

    def test_known_levels_keep_their_case(self):
        tags.tag_entry(self.entries[0], "Projet Été/Groupe A")
        tag = tags.tag_entry(self.entries[1], " projet été / groupe a ").tag
        self.assertEqual(tag.name, "Projet Été/Groupe A")
        tag = tags.tag_entry(self.entries[2], "PROJET ÉTÉ/Écarté").tag
        self.assertEqual(tag.name, "Projet Été/Écarté")
        self.assertEqual(Tag.objects.filter(user=self.alice).count(), 2)

    def test_tags_belong_to_each_user(self):
        tags.tag_entry(self.entries[0], "Projet A")
        bob_entry = UserPublication.objects.create(user=self.bob, publication=self.pubs[0])
        self.assertEqual(tags.tag_entry(bob_entry, "projet a").tag.name, "projet a")
        self.assertEqual(Tag.objects.count(), 2)

    def test_empty_and_too_long_names(self):
        self.assertIsNone(tags.tag_entry(self.entries[0], " / ").tag)
        with self.assertRaises(tags.InvalidTag):
            tags.tag_entry(self.entries[0], "x" * 201)

    def test_unused_tags_are_forgotten(self):
        tag = tags.tag_entry(self.entries[0], "A/B").tag
        tags.tag_entry(self.entries[1], "A/B")
        tags.untag_entry(self.entries[0], tag)
        self.assertTrue(Tag.objects.filter(pk=tag.pk).exists())
        tags.untag_entry(self.entries[1], tag)
        self.assertFalse(Tag.objects.filter(pk=tag.pk).exists())

    def test_tree_counts_the_descendants(self):
        tags.tag_entry(self.entries[0], "B/Groupe 1")
        tags.tag_entry(self.entries[1], "B/Groupe 2")
        tags.tag_entry(self.entries[1], "a")
        tags.tag_entry(self.entries[2], "B")
        tree = [(item["path"], item["depth"], item["count"]) for item in tags.tag_tree(self.alice)]
        self.assertEqual(
            tree, [("a", 0, 1), ("B", 0, 3), ("B/Groupe 1", 1, 1), ("B/Groupe 2", 1, 1)]
        )

    def test_filter_includes_the_descendants_only(self):
        tags.tag_entry(self.entries[0], "Projet B/Groupe B")
        tags.tag_entry(self.entries[1], "Projet B")
        tags.tag_entry(self.entries[2], "Projet Bis")
        # Bob's tags never filter Alice's corpus.
        bob_entry = UserPublication.objects.create(user=self.bob, publication=self.pubs[3])
        tags.tag_entry(bob_entry, "Projet B")
        self.assertEqual(self.titles(tag="Projet B"), ["P0", "P1"])
        self.assertEqual(self.titles(tag="Projet B/Groupe B"), ["P0"])
        self.assertEqual(self.titles(tag="Inconnu"), [])

    def test_corpus_page_shows_badges_tree_and_active_filter(self):
        tags.tag_entry(self.entries[0], "Projet B/Écarté")
        response = self.client.get(reverse("corpus"), {"tag": "Projet B"})
        self.assertContains(response, "Projet B › Écarté")
        self.assertContains(response, 'href="?tag=Projet%20B/%C3%89cart%C3%A9"')
        self.assertContains(response, 'aria-current="true"')
        self.assertContains(response, "Tag « Projet B »")

    def test_corpus_page_without_tags_explains_them(self):
        self.assertContains(self.client.get(reverse("corpus")), "« / » sépare les niveaux")

    def test_tag_and_untag_from_the_publication_page(self):
        pub = self.pubs[0]
        url = reverse("corpus_tag", args=[pub.pk])
        response = self.client.post(url, {"name": "Projet A/Groupe A"}, follow=True)
        self.assertContains(response, "Tag « Projet A › Groupe A » ajouté")
        self.assertContains(response, 'list="known-tags"')
        self.assertContains(response, '<option value="Projet A/Groupe A">', html=True)
        tag = Tag.objects.get()
        self.client.post(reverse("corpus_untag", args=[pub.pk, tag.pk]))
        self.assertEqual(self.names(self.entries[0]), [])

    def test_empty_tag_is_refused(self):
        url = reverse("corpus_tag", args=[self.pubs[0].pk])
        self.assertContains(self.client.post(url, {"name": " "}, follow=True), "Écrivez le nom")

    def test_only_my_own_entries_and_tags(self):
        outside = Publication.objects.create(title="Hors corpus")
        url = reverse("corpus_tag", args=[outside.pk])
        self.assertEqual(self.client.post(url, {"name": "A"}).status_code, 404)
        bob_entry = UserPublication.objects.create(user=self.bob, publication=self.pubs[0])
        bob_tag = tags.tag_entry(bob_entry, "B").tag
        url = reverse("corpus_untag", args=[self.pubs[0].pk, bob_tag.pk])
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_removing_from_the_corpus_forgets_unused_tags(self):
        tags.tag_entry(self.entries[0], "Seul")
        self.client.post(reverse("corpus_remove", args=[self.pubs[0].pk]))
        self.assertFalse(Tag.objects.exists())

    def test_publication_outside_my_corpus_has_no_tag_form(self):
        self.client.force_login(self.bob)
        response = self.client.get(reverse("publication_detail", args=[self.pubs[0].pk]))
        self.assertNotContains(response, "known-tags")


class TagTransferTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        cls.bob = User.objects.create_user("bob")
        cls.pub = Publication.objects.create(doi="10.1000/known", title="Connue")
        entry = UserPublication.objects.create(user=cls.alice, publication=cls.pub)
        tags.tag_entry(entry, "Projet A/Groupe A")
        tags.tag_entry(entry, "R&D")

    def test_json_export_holds_the_tags(self):
        entry = export_corpus(self.alice)["publications"][0]
        self.assertEqual(entry["tags"], ["Projet A/Groupe A", "R&D"])

    def test_bibtex_keywords(self):
        self.assertIn("keywords = {Projet A/Groupe A, R\\&D},", corpus_bibtex(self.alice))

    def test_import_adds_the_tags(self):
        entry = UserPublication.objects.create(user=self.bob, publication=self.pub)
        tags.tag_entry(entry, "projet a/Autre")
        data = {
            "format": EXPORT_FORMAT,
            "version": 2,
            "publications": [{"doi": "10.1000/known", "tags": ["Projet A/Groupe A", "", 3]}],
        }
        import_corpus(self.bob, data)
        names = sorted(entry.tags.values_list("name", flat=True))
        self.assertEqual(names, ["projet a/Autre", "projet a/Groupe A"])
