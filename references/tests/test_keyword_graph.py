"""The map of the keywords of a corpus (#418): built from the OpenAlex answers in base."""

from collections import Counter
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import Publication, UserPublication
from references.services.corpus import tags
from references.services.display.keyword_graph import (
    MAX_MINIMUM,
    MOST_TERMS,
    TOPICS,
    default_minimum,
    keyword_graph,
    requested_minimum,
)
from references.services.sources.external_records import Source, store_record


def openalex(pub, keywords=(), topics=()):
    """Store an OpenAlex answer with these keywords and topics (names, or (name, field))."""
    store_record(
        pub,
        Source.OPENALEX,
        {
            "id": f"https://openalex.org/W{pub.pk}",
            "keywords": [{"display_name": name, "score": 0.5} for name in keywords],
            "topics": [
                {
                    "display_name": name,
                    "field": {"display_name": field},
                    "subfield": {"display_name": f"{field} (sous-domaine)"},
                }
                for name, field in topics
            ],
        },
    )
    return pub


def nodes(graph):
    return {node["data"]["label"]: node["data"] for node in graph["nodes"]}


def links(graph):
    """{frozenset of two names: publications that carry both}."""
    names = {node["data"]["id"]: node["data"]["label"] for node in graph["nodes"]}
    return {
        frozenset((names[e["data"]["source"]], names[e["data"]["target"]])): e["data"]["shared"]
        for e in graph["edges"]
    }


class KeywordGraphTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.alice = get_user_model().objects.create_user("alice")
        cls.bob = get_user_model().objects.create_user("bob")
        cls.first = Publication.objects.create(title="Aimants")
        cls.second = Publication.objects.create(title="Protection")
        cls.third = Publication.objects.create(title="Sources d'ions")
        cls.unknown = Publication.objects.create(title="Inconnue d'OpenAlex")
        cls.unfetched = Publication.objects.create(title="Sans DOI")
        cls.others = Publication.objects.create(title="Corpus de Bob")
        openalex(cls.first, ["magnets", "quench", "LHC"], [("Accelerators", "Physics")])
        openalex(cls.second, ["magnets", "quench"], [("Accelerators", "Physics")])
        openalex(cls.third, ["magnets", "ion source"], [("Plasma", "Physics")])
        store_record(cls.unknown, Source.OPENALEX, None)
        openalex(cls.others, ["magnets", "quench"])
        for pub in (cls.first, cls.second, cls.third, cls.unknown, cls.unfetched):
            UserPublication.objects.create(user=cls.alice, publication=pub)
        UserPublication.objects.create(user=cls.bob, publication=cls.others)

    def test_a_node_per_term_sized_by_its_publications(self):
        graph = keyword_graph(self.alice, minimum=1)
        self.assertEqual(
            {name: data["publications"] for name, data in nodes(graph).items()},
            {"magnets": 3, "quench": 2, "LHC": 1, "ion source": 1},
        )

    def test_an_edge_weighs_the_publications_that_carry_both(self):
        graph = keyword_graph(self.alice, minimum=1)
        self.assertEqual(
            links(graph),
            {
                frozenset({"magnets", "quench"}): 2,
                frozenset({"magnets", "LHC"}): 1,
                frozenset({"quench", "LHC"}): 1,
                frozenset({"magnets", "ion source"}): 1,
            },
        )

    def test_the_threshold_keeps_the_terms_of_enough_publications(self):
        graph = keyword_graph(self.alice, minimum=2)
        self.assertEqual(set(nodes(graph)), {"magnets", "quench"})
        self.assertEqual(links(graph), {frozenset({"magnets", "quench"}): 2})
        self.assertIn((1, "1 publication (4 mots-clés)"), graph["thresholds"])
        self.assertIn((2, "2 publications (2 mots-clés)"), graph["thresholds"])
        self.assertIn((4, "4 publications (0 mot-clé)"), graph["thresholds"])

    def test_the_most_carried_term_comes_first(self):
        graph = keyword_graph(self.alice, minimum=1)
        self.assertEqual(graph["nodes"][0]["data"]["label"], "magnets")

    def test_a_term_lists_its_publications_and_opens_the_corpus_filtered(self):
        graph = keyword_graph(self.alice, minimum=1)
        quench = nodes(graph)["quench"]
        self.assertEqual(sorted(quench["publicationIds"]), sorted([self.first.pk, self.second.pk]))
        self.assertEqual(quench["url"], reverse("corpus") + "?keyword=quench")
        self.assertEqual(graph["publications"][str(self.first.pk)]["label"], "Aimants")

    def test_publications_without_an_answer_are_counted(self):
        graph = keyword_graph(self.alice)
        # The unknown publication and the one never asked.
        self.assertEqual(graph["unanswered"], 2)
        self.assertEqual(graph["without_terms"], 0)

    def test_topics_with_their_field(self):
        graph = keyword_graph(self.alice, terms=TOPICS, minimum=1)
        self.assertEqual(
            {name: data["publications"] for name, data in nodes(graph).items()},
            {"Accelerators": 2, "Plasma": 1},
        )
        self.assertEqual(nodes(graph)["Plasma"]["detail"], "Physics › Physics (sous-domaine)")
        self.assertEqual(nodes(graph)["Plasma"]["url"], reverse("corpus") + "?topic=Plasma")
        self.assertEqual(links(graph), {})

    def test_the_graph_of_a_tag(self):
        entry = UserPublication.objects.get(user=self.alice, publication=self.third)
        tags.tag_entry(entry, "Ions")
        graph = keyword_graph(self.alice, tag="Ions", minimum=1)
        self.assertEqual(set(nodes(graph)), {"magnets", "ion source"})
        self.assertEqual(
            nodes(graph)["magnets"]["url"], reverse("corpus") + "?keyword=magnets&tag=Ions"
        )

    def test_three_queries_whatever_the_corpus(self):
        with self.assertNumQueries(3):
            keyword_graph(self.alice)

    def test_the_requested_threshold(self):
        self.assertEqual(requested_minimum({"min": "3"}), 3)
        self.assertEqual(requested_minimum({"min": "11"}), 11)
        for wrong in ("0", "-1", "deux", ""):
            self.assertIsNone(requested_minimum({"min": wrong}))

    def test_the_default_threshold_keeps_all_the_terms_of_a_small_corpus(self):
        graph = keyword_graph(self.alice)
        self.assertEqual((graph["minimum"], graph["default_minimum"]), (1, 1))
        self.assertEqual(set(nodes(graph)), {"magnets", "quench", "LHC", "ion source"})

    def test_the_default_threshold_keeps_at_most_most_terms(self):
        with patch("references.services.display.keyword_graph.MOST_TERMS", 2):
            graph = keyword_graph(self.alice)
        self.assertEqual(graph["minimum"], 2)
        self.assertEqual(set(nodes(graph)), {"magnets", "quench"})
        self.assertEqual(graph["default_minimum"], 2)

    def test_a_threshold_beyond_the_choices_is_the_last_one(self):
        graph = keyword_graph(self.alice, minimum=40)
        self.assertEqual(graph["minimum"], MAX_MINIMUM)
        self.assertEqual(len(graph["thresholds"]), MAX_MINIMUM)
        self.assertEqual(nodes(graph), {})


def carried(*kept):
    """
    A Counter of terms {name: publications} such that kept[i] terms are carried by at
    least i + 1 publications.
    """
    counts = Counter()
    for index, many in enumerate(kept):
        exactly = many - (kept[index + 1] if index + 1 < len(kept) else 0)
        counts.update({f"t{index + 1}-{n}": index + 1 for n in range(exactly)})
    return counts


class DefaultMinimumTests(TestCase):
    """The default threshold aims at 30 to 50 terms (#468): the lowest that keeps 50 at most."""

    def test_one_when_every_term_fits(self):
        self.assertEqual(default_minimum(Counter()), 1)
        self.assertEqual(default_minimum(carried(MOST_TERMS, 10)), 1)
        self.assertEqual(default_minimum(carried(MOST_TERMS + 1, 10)), 2)

    def test_the_corpus_of_the_user(self):
        # The keywords of the copy of the user's base (26 publications): 117, 29, 17…
        self.assertEqual(default_minimum(carried(117, 29, 17, 13, 6, 4, 2, 1)), 2)

    def test_the_corpus_of_the_benchmark(self):
        # The keywords of the corpus of the benchmark (217 publications): 2 kept 169.
        kept = (737, 169, 109, 76, 58, 44, 33, 24, 21, 20, 18, 14, 13, 11, 9)
        self.assertEqual(default_minimum(carried(*kept)), 6)

    def test_beyond_the_usual_choices(self):
        # 60 terms carried by 12 publications: the default goes past MAX_MINIMUM, and so
        # do the choices.
        self.assertEqual(default_minimum(carried(*[60] * 12, 1)), 13)


class DefaultMinimumPageTests(TestCase):
    """The page keeps the threshold asked only, never the default (#468)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        for index in range(3):
            pub = Publication.objects.create(title=f"Publication {index}")
            # 60 keywords on a single publication each, 2 on all three.
            names = ["magnets", "quench", *(f"k{index}-{n}" for n in range(20))]
            openalex(pub, names)
            entry = UserPublication.objects.create(user=cls.user, publication=pub)
            tags.tag_entry(entry, "Aimants")

    def setUp(self):
        self.client.force_login(self.user)

    def test_the_default_keeps_the_terms_of_several_publications(self):
        response = self.client.get(reverse("corpus_keywords"))
        self.assertContains(response, "2 mots-clés, 1 lien")
        self.assertContains(response, '<option value="2" selected>2 publications (2 mots-clés)')
        self.assertContains(
            response, "Par défaut : 2 publications, le plus petit seuil qui garde au plus 50"
        )
        # The tag form does not keep it: another tag has its own default.
        self.assertContains(response, 'id="graph-tag"')
        self.assertNotContains(response, '<input type="hidden" name="min"')

    def test_a_threshold_asked_is_kept(self):
        response = self.client.get(reverse("corpus_keywords"), {"min": "1"})
        self.assertContains(response, "62 mots-clés")
        self.assertContains(response, '<option value="1" selected>')
        self.assertContains(response, '<input type="hidden" name="min" value="1">')


class KeywordPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        cls.first = Publication.objects.create(title="Aimants")
        cls.second = Publication.objects.create(title="Protection")
        cls.third = Publication.objects.create(title="Sources d'ions")
        openalex(cls.first, ["magnets", "quench"], [("Accelerators", "Physics")])
        openalex(cls.second, ["magnets", "quench"], [("Accelerators", "Physics")])
        openalex(cls.third, ["magnets"])
        for pub in (cls.first, cls.second, cls.third):
            UserPublication.objects.create(user=cls.user, publication=pub)

    def setUp(self):
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("corpus_keywords"))
        self.assertEqual(response.status_code, 302)

    def test_the_map_of_the_keywords(self):
        response = self.client.get(reverse("corpus_keywords"))
        self.assertContains(response, 'id="citation-graph"')
        self.assertContains(response, "2 mots-clés, 1 lien")
        self.assertContains(response, "graph/keywords.js")
        self.assertNotContains(response, "pas de réponse OpenAlex")

    def test_the_topics(self):
        response = self.client.get(reverse("corpus_keywords"), {"kind": "topics", "min": "1"})
        # A single topic: no edge, the message and the controls instead of the graph.
        self.assertNotContains(response, 'id="citation-graph"')
        self.assertContains(response, "Un seul thème gardé, « Accelerators »")
        self.assertContains(response, "1 publication n'a aucun thème selon OpenAlex.")
        # The threshold keeps the kind.
        self.assertContains(response, '<input type="hidden" name="kind" value="topics">')

    def test_says_the_publications_without_an_answer(self):
        pub = Publication.objects.create(title="Sans DOI")
        UserPublication.objects.create(user=self.user, publication=pub)
        response = self.client.get(reverse("corpus_keywords"))
        self.assertContains(response, "1 publication n'a pas de réponse OpenAlex")

    def test_my_corpus_filtered_on_a_keyword(self):
        response = self.client.get(reverse("corpus"), {"keyword": "quench"})
        self.assertContains(response, "Aimants")
        self.assertContains(response, "Protection")
        self.assertNotContains(response, "Sources d&#x27;ions")

    def test_my_corpus_filtered_on_a_topic(self):
        response = self.client.get(reverse("corpus"), {"topic": "Accelerators"})
        self.assertContains(response, "Aimants")
        self.assertNotContains(response, "Sources d&#x27;ions")
