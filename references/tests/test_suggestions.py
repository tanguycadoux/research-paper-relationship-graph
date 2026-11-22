from datetime import date

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from references.models import CitedReference, ExternalRecord, Publication, Tag, UserPublication
from references.services.corpus import tags
from references.services.discovery import importance, suggestions

Source = ExternalRecord.Source


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

    def counts(self, user=None, tag="", minimum=suggestions.MIN_CITING):
        rows, _ = suggestions.sorted_suggestions(user or self.alice, tag, minimum)
        return {pub.title: pub.citing_count for pub in rows}

    def get(self, **params):
        return self.client.get(reverse("corpus_suggestions"), params)

    def test_cited_by_the_corpus_most_cited_first(self):
        self.assertEqual(
            list(self.counts().items()), [("Central", 3), ("Partagé", 2), ("Cité une fois", 1)]
        )

    def test_cited_by_at_least_two_of_the_corpus(self):
        self.assertEqual(list(self.counts(minimum=2).items()), [("Central", 3), ("Partagé", 2)])
        response = self.get(min="2")
        self.assertEqual(response.context["min_citing"], 2)
        self.assertEqual(len(response.context["publications"]), 2)
        self.assertContains(response, "citées par au moins 2 articles")

    def test_unknown_minimum_is_the_default(self):
        self.assertEqual(suggestions.min_citing("7"), suggestions.MIN_CITING)
        self.assertEqual(suggestions.min_citing("x"), suggestions.MIN_CITING)
        self.assertEqual(suggestions.min_citing("2"), 2)

    def test_same_bibliography_counts_once(self):
        self.cite(self.mine[3], self.shared, self.shared)
        self.assertEqual(self.counts()["Partagé"], 3)

    def test_other_users_have_their_own_suggestions(self):
        self.assertEqual(self.counts(self.bob), {})

    def test_a_tag_includes_its_descendants(self):
        tags.tag_entry(self.entries[0], "Projet")
        tags.tag_entry(self.entries[1], "Projet/Groupe")
        self.assertEqual(self.counts(tag="Projet"), {"Central": 2, "Partagé": 2})
        self.assertEqual(self.counts(tag="Projet/Groupe"), {"Central": 1, "Partagé": 1})

    def test_in_a_tag_the_rest_of_the_corpus_is_suggested_and_marked(self):
        tags.tag_entry(self.entries[2], "Projet")
        tags.tag_entry(self.entries[3], "Projet")
        tags.tag_entry(self.entries[0], "Méthodes")
        response = self.get(tag="Projet")
        (pub,) = [pub for pub in response.context["publications"] if pub == self.mine[0]]
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
        self.assertNotIn(self.mine[0].title, self.counts(tag="Projet"))
        self.assertEqual(self.counts(tag="Projet")["Central"], 2)

    def test_page_lists_the_citing_publications_newest_first(self):
        response = self.get()
        central = response.context["publications"][0]
        self.assertEqual(central.citing, [self.mine[2], self.mine[1], self.mine[0]])
        self.assertFalse(central.in_corpus)
        self.assertContains(response, "Ajouter à mon corpus, à lire")
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
        self.assertEqual(len(response.context["publications"]), 3)
        self.assertContains(response, "Disparu » n&#x27;existe plus")

    def test_page_without_suggestions(self):
        self.client.force_login(self.bob)
        self.assertContains(self.get(), "Aucune publication n'est citée par ces articles.")

    def test_page_is_private(self):
        self.client.logout()
        self.assertEqual(self.get().status_code, 302)

    def test_corpus_page_links_to_the_suggestions_of_its_tag(self):
        tags.tag_entry(self.entries[0], "Projet/Groupe")
        response = self.client.get(reverse("corpus"), {"tag": "Projet/Groupe"})
        self.assertContains(response, reverse("corpus_suggestions") + "?tag=Projet/Groupe")
        self.assertTrue(Tag.objects.filter(name="Projet/Groupe").exists())


class SuggestionSortTests(TestCase):
    """Sorts by the citations in the literature, per year and by importance (#432)."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice")
        cls.mine = [Publication.objects.create(title=f"Mien {i}") for i in range(2)]
        for pub in cls.mine:
            UserPublication.objects.create(user=cls.alice, publication=pub)
        cls.old = Publication.objects.create(title="Ancien", publication_date=date(2000, 1, 1))
        cls.recent = Publication.objects.create(title="Récent", publication_date=date(2020, 1, 1))
        cls.unknown = Publication.objects.create(title="Inconnu", publication_date=date(2010, 1, 1))
        for target in (cls.old, cls.recent, cls.unknown):
            SuggestionTests.cite(cls.mine[0], target)
        SuggestionTests.cite(cls.mine[1], cls.unknown)
        # OpenAlex first; Crossref when OpenAlex has no count.
        cls.record(cls.old, Source.OPENALEX, {"cited_by_count": 260})
        cls.record(cls.old, Source.CROSSREF, {"message": {"is-referenced-by-count": 999}})
        cls.record(cls.recent, Source.OPENALEX, {"display_name": "Récent"})
        cls.record(cls.recent, Source.CROSSREF, {"message": {"is-referenced-by-count": 60}})
        # Outside the corpus, two publications cite the recent one: it is important.
        for i in range(2):
            citing = Publication.objects.create(title=f"Citant {i}")
            SuggestionTests.cite(citing, cls.recent)

    @staticmethod
    def record(pub, source, data):
        ExternalRecord.objects.create(
            publication=pub, source=source, data=data, fetched_at=timezone.now()
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.alice)

    def titles(self, sort):
        rows, _ = suggestions.sorted_suggestions(
            self.alice, sort=suggestions.SUGGESTIONS.read(sort)
        )
        return [pub.title for pub in rows]

    def test_literature_citations_from_openalex_else_crossref(self):
        rows = {pub.title: pub for pub in suggestions.co_cited(self.alice)}
        self.assertEqual(rows["Ancien"].cited_count, 260)
        self.assertEqual(rows["Ancien"].cited_source, Source.OPENALEX)
        self.assertEqual(rows["Récent"].cited_count, 60)
        self.assertEqual(rows["Récent"].cited_source, Source.CROSSREF)
        self.assertIsNone(rows["Inconnu"].cited_count)

    def test_sort_by_citations_without_count_last(self):
        self.assertEqual(self.titles("-cited"), ["Ancien", "Récent", "Inconnu"])
        self.assertEqual(self.titles("cited"), ["Récent", "Ancien", "Inconnu"])

    def test_sort_by_citations_per_year(self):
        years = timezone.now().year
        rows = {pub.title: pub for pub in suggestions.co_cited(self.alice)}
        self.assertAlmostEqual(rows["Ancien"].cited_per_year, 260 / (years - 2000))
        self.assertEqual(self.titles("-per_year"), ["Récent", "Ancien", "Inconnu"])

    def test_default_sort_by_citing_articles(self):
        self.assertEqual(self.titles(""), ["Inconnu", "Récent", "Ancien"])

    def test_sort_by_importance(self):
        self.assertEqual(self.titles("-importance")[0], "Récent")
        self.assertEqual(self.titles("importance")[-1], "Récent")

    def test_page_shows_the_counts_and_sort_links(self):
        response = self.client.get(reverse("corpus_suggestions"), {"sort": "-importance"})
        self.assertEqual(response.context["publications"][0], self.recent)
        self.assertEqual(response.context["publications"][0].importance, 100)
        self.assertContains(response, 'aria-sort="descending"')
        self.assertContains(response, "?sort=-cited")
        self.assertContains(response, "Selon OpenAlex")
        self.assertContains(response, "Ni OpenAlex ni Crossref")


class ImportanceTests(TestCase):
    """The PageRank of the citation graph, of the whole base or of a context (#432)."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice")
        cls.mine = Publication.objects.create(title="Mien")
        UserPublication.objects.create(user=cls.alice, publication=cls.mine)
        cls.a = Publication.objects.create(title="A")
        cls.b = Publication.objects.create(title="B")
        SuggestionTests.cite(cls.mine, cls.a, cls.b)
        cls.outside = [Publication.objects.create(title=f"Dehors {i}") for i in range(3)]
        for pub in cls.outside:
            SuggestionTests.cite(pub, cls.b)

    def setUp(self):
        cache.clear()

    def test_pagerank_favours_the_cited(self):
        ranks = importance.pagerank({(1, 2), (3, 2), (2, 4)})
        self.assertEqual(max(ranks, key=ranks.get), 4)
        self.assertEqual(importance.pagerank(set()), {})

    def test_base_counts_citations_from_outside_the_context(self):
        base = importance.ranks(self.alice, scope=importance.SCOPE_BASE)
        self.assertGreater(base[self.b.pk], base[self.a.pk])
        context = importance.ranks(self.alice, scope=importance.SCOPE_CONTEXT)
        self.assertAlmostEqual(context[self.a.pk], context[self.b.pk])
        self.assertNotIn(self.outside[0].pk, context)

    def test_base_ranks_are_cached_until_the_citations_change(self):
        with self.assertNumQueries(2):
            first = importance.base_ranks()
        with self.assertNumQueries(1):
            importance.base_ranks()
        SuggestionTests.cite(self.outside[0], self.a)
        self.assertGreater(importance.base_ranks()[self.a.pk], first[self.a.pk])

    def test_self_citation_is_left_out(self):
        SuggestionTests.cite(self.a, self.a)
        self.assertNotIn((self.a.pk, self.a.pk), importance.citation_edges())
