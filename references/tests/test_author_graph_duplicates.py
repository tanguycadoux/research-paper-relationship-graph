"""The probable duplicates gathered on the coauthorship graphs, without changing the base (#419)."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.http import urlencode

from references.models import Author, AuthorDistinction
from references.services.corrections.author_duplicates import duplicate_groups
from references.services.display.author_graph import all_authors_graph, author_graph
from references.services.display.author_groups import probable_groups
from references.tests.test_author_graph import links, nodes, publish


class GroupedGraphTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.abbott, cls.short, cls.alan, cls.grace = (
            Author.objects.create(first_name=first, last_name=last)
            for first, last in [
                ("B. P.", "Abbott"),
                ("B", "Abbott"),
                ("Alan", "Turing"),
                ("Grace", "Hopper"),
            ]
        )
        publish("Abbott et Alan", cls.abbott, cls.alan)
        publish("Abbott court et Alan", cls.short, cls.alan)
        publish("Abbott court et Grace", cls.short, cls.grace)
        # The two spellings on one publication: one person, counted once.
        publish("Les deux Abbott et Grace", cls.abbott, cls.short, cls.grace)

    def test_the_groups_are_those_of_the_page_of_duplicates(self):
        with self.assertNumQueries(2):
            groups = probable_groups()
        expected = [[author.pk for author in group] for group in duplicate_groups()]
        self.assertEqual(sorted(map(sorted, groups)), sorted(map(sorted, expected)))

    def test_a_group_is_one_node_its_publications_counted_once(self):
        graph = all_authors_graph(groups=probable_groups())
        self.assertEqual(graph["groups"], 1)
        abbott = nodes(graph)["B. P. Abbott"]
        self.assertNotIn("B Abbott", nodes(graph))
        self.assertEqual(abbott["id"], str(self.abbott.pk))
        self.assertTrue(abbott["grouped"])
        self.assertEqual(abbott["publications"], 4)
        self.assertEqual(
            [(v["label"], v["publications"]) for v in abbott["variants"]],
            [("B Abbott", 3), ("B. P. Abbott", 2)],
        )
        self.assertEqual(
            abbott["variants"][0]["url"], reverse("author_detail", args=[self.short.pk])
        )
        self.assertNotIn("grouped", nodes(graph)["Alan Turing"])

    def test_the_links_of_a_group_add_up(self):
        graph_links = links(all_authors_graph(groups=probable_groups()))
        self.assertEqual(graph_links[frozenset({"B. P. Abbott", "Alan Turing"})], (2.0, 2))
        # « Les deux Abbott et Grace »: two people, a link of 1.
        self.assertEqual(graph_links[frozenset({"B. P. Abbott", "Grace Hopper"})], (2.0, 2))
        self.assertEqual(len(graph_links), 2)

    def test_the_base_as_it_is(self):
        graph = all_authors_graph(groups=probable_groups(), grouped=False)
        self.assertEqual(graph["groups"], 1)
        self.assertEqual(
            set(nodes(graph)), {"B. P. Abbott", "B Abbott", "Alan Turing", "Grace Hopper"}
        )
        self.assertNotIn("variants", nodes(graph)["B Abbott"])
        self.assertIn(frozenset({"B. P. Abbott", "B Abbott"}), links(graph))

    def test_without_groups_nothing_is_gathered(self):
        graph = all_authors_graph()
        self.assertEqual(graph["groups"], 0)
        self.assertEqual(len(graph["nodes"]), 4)

    def test_the_author_of_the_graph_names_their_group(self):
        graph = author_graph(self.short, groups=probable_groups())
        first = graph["nodes"][0]["data"]
        self.assertEqual((first["label"], first["role"]), ("B Abbott", "source"))
        self.assertEqual(len(first["variants"]), 2)
        self.assertEqual(set(nodes(graph)), {"B Abbott", "Alan Turing", "Grace Hopper"})

    def test_a_declared_distinction_separates_them(self):
        AuthorDistinction.objects.create(first=self.abbott, second=self.short)
        graph = all_authors_graph(groups=probable_groups())
        self.assertEqual(graph["groups"], 0)
        self.assertEqual(len(graph["nodes"]), 4)

    def test_nothing_is_written(self):
        all_authors_graph(groups=probable_groups())
        self.assertEqual(Author.objects.count(), 4)
        self.assertEqual(self.short.publications.count(), 3)


class GroupedGraphPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.abbott = Author.objects.create(first_name="B. P.", last_name="Abbott")
        cls.short = Author.objects.create(first_name="B", last_name="Abbott")
        cls.alan = Author.objects.create(first_name="Alan", last_name="Turing")
        publish("Abbott et Alan", cls.abbott, cls.alan)
        publish("Abbott court et Alan", cls.short, cls.alan)
        cls.user = get_user_model().objects.create_user("alice")

    def test_gathered_by_default_and_said_in_the_legend(self):
        response = self.client.get(reverse("authors_graph"))
        self.assertContains(response, 'role="switch"')
        self.assertContains(response, 'aria-checked="true"')
        self.assertContains(response, "Regrouper les doublons probables (1)")
        self.assertContains(response, 'href="?doublons=separes"')
        self.assertContains(response, "Doublons probables regroupés (1)")
        self.assertContains(response, "2 auteurs, 1 lien de coautorat")
        self.assertContains(response, 'data-graph-export="graphe-auteurs"')

    def test_the_base_as_it_is_on_demand(self):
        response = self.client.get(reverse("authors_graph"), {"doublons": "separes"})
        self.assertContains(response, 'aria-checked="false"')
        self.assertContains(response, "Regrouper les doublons probables (1)")
        self.assertContains(response, 'href="?"')
        self.assertNotContains(response, "Doublons probables regroupés (1)")
        self.assertContains(response, "3 auteurs, 2 liens de coautorat")
        self.assertContains(response, 'data-graph-export="graphe-auteurs-doublons-separes"')

    def test_the_graph_of_an_author_gathers_too(self):
        url = reverse("author_graph", args=[self.alan.pk])
        response = self.client.get(url)
        self.assertContains(response, "2 auteurs, 1 lien de coautorat")
        self.assertContains(response, 'data-graph-export="graphe-auteur-')
        response = self.client.get(url, {"doublons": "separes"})
        self.assertContains(response, "3 auteurs, 2 liens de coautorat")

    def test_without_any_group_the_switch_is_disabled(self):
        AuthorDistinction.objects.create(first=self.abbott, second=self.short)
        response = self.client.get(reverse("authors_graph"))
        self.assertContains(response, 'aria-disabled="true"')
        self.assertContains(response, "Regrouper les doublons probables (0)")
        self.assertNotContains(response, 'role="switch"')

    def test_the_actions_of_a_group_for_a_logged_in_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("authors_graph"))
        self.assertContains(response, "data-card-variants-form")
        self.assertContains(response, f'action="{reverse("author_merge_select")}"')
        self.assertContains(response, f'formaction="{reverse("authors_graph_distinct")}"')
        self.assertContains(response, "Fusionner pour de bon…")
        self.assertContains(response, "Ce ne sont pas les mêmes")
        self.assertContains(response, f'name="next" value="{reverse("authors_graph")}"')

    def test_no_actions_for_a_visitor(self):
        response = self.client.get(reverse("authors_graph"))
        self.assertNotContains(response, "data-card-variants-form")
        self.assertContains(response, 'data-card-row="variants"')

    def test_merge_for_good_goes_to_the_usual_confirmation(self):
        self.client.force_login(self.user)
        back = reverse("authors_graph")
        response = self.client.post(
            reverse("author_merge_select"),
            {"authors": [self.abbott.pk, self.short.pk], "next": back},
        )
        self.assertEqual(response.status_code, 302)
        path, query = response.url.split("?")
        ids = path.removeprefix("/authors/merge/").strip("/").split(",")
        self.assertEqual(sorted(map(int, ids)), sorted([self.abbott.pk, self.short.pk]))
        self.assertEqual(query, urlencode({"next": back}))


class DistinctFromTheGraphTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.abbott = Author.objects.create(first_name="B. P.", last_name="Abbott")
        cls.short = Author.objects.create(first_name="B", last_name="Abbott")
        cls.user = get_user_model().objects.create_user("alice")

    def test_declared_distinct_then_back_to_the_graph(self):
        self.client.force_login(self.user)
        back = reverse("author_graph", args=[self.short.pk]) + "?doublons=separes"
        response = self.client.post(
            reverse("authors_graph_distinct"),
            {"authors": [self.abbott.pk, self.short.pk], "next": back},
            follow=True,
        )
        self.assertRedirects(response, back)
        self.assertContains(response, "Ne seront plus regroupés : B. P. Abbott, B Abbott.")
        pair = AuthorDistinction.objects.get()
        self.assertEqual(
            (pair.first, pair.second, pair.declared_by), (self.abbott, self.short, self.user)
        )
        self.assertEqual(probable_groups(), [])

    def test_at_least_two_authors(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("authors_graph_distinct"), {"authors": [self.abbott.pk]}, follow=True
        )
        self.assertRedirects(response, reverse("authors_graph"))
        self.assertContains(response, "Cochez au moins deux auteurs.")
        self.assertFalse(AuthorDistinction.objects.exists())

    def test_an_outside_next_is_refused(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("authors_graph_distinct"),
            {"authors": [self.abbott.pk, self.short.pk], "next": "https://example.org/"},
        )
        self.assertRedirects(response, reverse("authors_graph"), fetch_redirect_response=False)

    def test_logged_in_only(self):
        response = self.client.post(
            reverse("authors_graph_distinct"), {"authors": [self.abbott.pk, self.short.pk]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)
        self.assertFalse(AuthorDistinction.objects.exists())

    def test_post_only(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("authors_graph_distinct"))
        self.assertEqual(response.status_code, 405)
