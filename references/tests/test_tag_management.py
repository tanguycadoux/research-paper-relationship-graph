from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Publication, Tag, UserPublication
from references.services import tags
from references.services.corpus_transfer import EXPORT_FORMAT, import_corpus
from references.tests.helpers import without_doi_org


class TagsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alice = User.objects.create_user("alice")
        cls.bob = User.objects.create_user("bob")
        cls.pubs = [Publication.objects.create(doi=f"10.1000/{i}", title=f"P{i}") for i in range(3)]
        cls.entries = [
            UserPublication.objects.create(user=cls.alice, publication=pub) for pub in cls.pubs
        ]

    def setUp(self):
        self.client.force_login(self.alice)

    def names(self, entry):
        return sorted(entry.tags.values_list("name", flat=True))

    def all_names(self, user=None):
        return sorted(Tag.objects.filter(user=user or self.alice).values_list("name", flat=True))


@without_doi_org
class RedundantTagsTests(TagsTestCase):
    """A tag beside one of its descendants is redundant: the filter includes them."""

    def test_more_precise_tag_replaces_its_ancestors(self):
        tags.tag_entry(self.entries[0], "Projet")
        tagging = tags.tag_entry(self.entries[0], "Projet/Groupe/Sous-groupe")
        self.assertEqual([tag.name for tag in tagging.replaced], ["Projet"])
        self.assertEqual(self.names(self.entries[0]), ["Projet/Groupe/Sous-groupe"])
        # « Projet » classed nothing else: forgotten.
        self.assertEqual(self.all_names(), ["Projet/Groupe/Sous-groupe"])

    def test_less_precise_tag_is_not_added(self):
        tags.tag_entry(self.entries[0], "Projet/Groupe")
        tagging = tags.tag_entry(self.entries[0], "projet")
        self.assertIsNone(tagging.tag)
        self.assertEqual(tagging.covered_by.name, "Projet/Groupe")
        self.assertEqual(self.names(self.entries[0]), ["Projet/Groupe"])

    def test_siblings_and_lookalikes_stay(self):
        for name in ("Projet/Groupe A", "Projet/Groupe B", "Projet Bis"):
            tags.tag_entry(self.entries[0], name)
        self.assertEqual(
            self.names(self.entries[0]), ["Projet Bis", "Projet/Groupe A", "Projet/Groupe B"]
        )

    def test_messages_of_the_publication_page(self):
        url = reverse("corpus_tag", args=[self.pubs[0].pk])
        self.client.post(url, {"name": "Projet"})
        response = self.client.post(url, {"name": "Projet/Groupe"}, follow=True)
        self.assertContains(response, "Il remplace « Projet », moins précis.")
        response = self.client.post(url, {"name": "Projet"}, follow=True)
        self.assertContains(response, "a déjà le tag « Projet › Groupe », plus précis")

    def test_import_follows_the_same_rule(self):
        data = {
            "format": EXPORT_FORMAT,
            "version": 2,
            "publications": [{"doi": "10.1000/0", "tags": ["Projet", "Projet/Groupe"]}],
        }
        import_corpus(self.alice, data)
        self.assertEqual(self.names(self.entries[0]), ["Projet/Groupe"])


class RenameTagTests(TagsTestCase):
    def test_rename_cascades_to_the_descendants(self):
        tags.tag_entry(self.entries[0], "Projet B/Groupe 1")
        tags.tag_entry(self.entries[1], "Projet B")
        self.assertEqual(tags.rename_path(self.alice, "Projet B", "ASTERICS"), 2)
        self.assertEqual(self.all_names(), ["ASTERICS", "ASTERICS/Groupe 1"])
        self.assertEqual(self.names(self.entries[1]), ["ASTERICS"])

    def test_rename_to_a_known_name_merges(self):
        tags.tag_entry(self.entries[0], "Aimants")
        tags.tag_entry(self.entries[1], "Magnets/Nb3Sn")
        tags.tag_entry(self.entries[2], "Aimants/Nb3Sn")
        tags.rename_path(self.alice, "Magnets", "aimants")
        self.assertEqual(self.all_names(), ["Aimants", "Aimants/Nb3Sn"])
        self.assertEqual(self.names(self.entries[1]), ["Aimants/Nb3Sn"])

    def test_merge_drops_the_redundant_ancestors(self):
        tags.tag_entry(self.entries[0], "A")
        tags.tag_entry(self.entries[0], "B/C")
        tags.rename_path(self.alice, "B", "A")
        self.assertEqual(self.names(self.entries[0]), ["A/C"])

    def test_move_under_itself_and_fix_the_case(self):
        tags.tag_entry(self.entries[0], "a")
        tags.tag_entry(self.entries[1], "a/x")
        tags.rename_path(self.alice, "a", "a/x")
        self.assertEqual(self.all_names(), ["a/x", "a/x/x"])
        tags.rename_path(self.alice, "a", "A")
        self.assertEqual(self.all_names(), ["A/x", "A/x/x"])

    def test_invalid_renames(self):
        tags.tag_entry(self.entries[0], "A")
        for path, name in (("Inconnu", "B"), ("A", " / "), ("A", "x" * 201)):
            with self.subTest(path=path, name=name), self.assertRaises(tags.InvalidTag):
                tags.rename_path(self.alice, path, name)
        self.assertEqual(self.all_names(), ["A"])

    def test_other_users_are_untouched(self):
        tags.tag_entry(self.entries[0], "A")
        bob_entry = UserPublication.objects.create(user=self.bob, publication=self.pubs[0])
        tags.tag_entry(bob_entry, "A")
        tags.rename_path(self.alice, "A", "B")
        self.assertEqual(self.all_names(self.bob), ["A"])

    def test_rename_view(self):
        tags.tag_entry(self.entries[0], "Projet B/Groupe")
        response = self.client.post(
            reverse("tag_rename"), {"path": "Projet B", "name": "ASTERICS"}, follow=True
        )
        self.assertContains(response, "Tag « Projet B » renommé : 1 publication(s) concernée(s).")
        self.assertContains(response, 'value="ASTERICS/Groupe"')
        response = self.client.post(reverse("tag_rename"), {"path": "Z", "name": "Y"}, follow=True)
        self.assertContains(response, "Le tag « Z » n&#x27;existe plus.")


class DeleteTagTests(TagsTestCase):
    def test_delete_with_descendants_keeps_the_publications(self):
        tags.tag_entry(self.entries[0], "A/B")
        tags.tag_entry(self.entries[1], "A")
        tags.tag_entry(self.entries[1], "C")
        self.assertEqual(tags.delete_path(self.alice, "A"), 2)
        self.assertEqual(self.all_names(), ["C"])
        self.assertEqual(UserPublication.objects.filter(user=self.alice).count(), 3)

    def test_delete_view(self):
        tags.tag_entry(self.entries[0], "A/B")
        response = self.client.post(reverse("tag_delete"), {"path": "A"}, follow=True)
        self.assertContains(response, "Tag « A » supprimé : retiré de 1 publication(s)")
        response = self.client.post(reverse("tag_delete"), {"path": "A"}, follow=True)
        self.assertContains(response, "n&#x27;existe plus")


class TagPageTests(TagsTestCase):
    def test_page_lists_the_tree_with_its_forms(self):
        tags.tag_entry(self.entries[0], "A/B")
        response = self.client.get(reverse("tag_list"))
        self.assertContains(response, "Retirer « A » et ses sous-tags de 1 publication ?")
        self.assertContains(response, "Retirer « A/B » de 1 publication ?")
        self.assertContains(response, 'action="/corpus/tags/rename/"', count=2)

    def test_corpus_page_links_to_it(self):
        tags.tag_entry(self.entries[0], "A")
        self.assertContains(self.client.get(reverse("corpus")), 'href="/corpus/tags/"')

    def test_actions_need_a_login_and_post(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("tag_list")).status_code, 302)
        self.client.force_login(self.alice)
        for name in ("tag_rename", "tag_delete"):
            with self.subTest(action=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 405)
