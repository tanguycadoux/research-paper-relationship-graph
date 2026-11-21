from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from references.forms import TitleSearchForm
from references.models import Publication, UserPublication
from references.services.discovery import title_search
from references.tests.sources import simulated_sources

URL = reverse("publication_title_search")
TITLE = "Attention is all you need"


def crossref_item(title, doi, family="Vaswani", year=2017):
    return {
        "DOI": doi,
        "title": [title],
        "author": [{"family": family}],
        "issued": {"date-parts": [[year]]},
        "container-title": ["NeurIPS"],
        "type": "proceedings-article",
    }


CROSSREF = [
    crossref_item(TITLE, "10.5555/attention"),
    crossref_item("Attention is all you need in speech separation", "10.1109/speech", "Subakan"),
    crossref_item("Deep residual learning for image recognition", "10.1109/resnet", "He", 2016),
]


class TitleSearchPageTests(TestCase):
    """Find a publication by its title, to add it (#309)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")

    def setUp(self):
        cache.clear()
        self.client.force_login(self.user)
        searches = {TITLE: CROSSREF, f"Vaswani {TITLE} 2017": CROSSREF}
        self.sources = self.enterContext(simulated_sources(crossref_searches=searches))

    def search(self, **params):
        return self.client.get(URL, {"title": TITLE, **params})

    def test_reached_from_the_form_that_adds(self):
        response = self.client.get(reverse("corpus"))
        self.assertContains(response, f'href="{URL}"')
        self.assertContains(response, "Chercher par titre")

    def test_nothing_is_asked_before_the_form_is_sent(self):
        response = self.client.get(URL)
        self.assertContains(response, "Chercher par titre</h2>")
        self.assertNotContains(response, "Publications trouvées")
        self.assertEqual(self.sources.requests, [])

    def test_the_works_close_to_the_title(self):
        response = self.search(author="Vaswani", year=2017)
        self.assertEqual(self.sources.searches("crossref"), [f"Vaswani {TITLE} 2017"])
        self.assertEqual(
            self.sources.to("crossref")[0].params["rows"], str(title_search.CROSSREF_ROWS)
        )
        self.assertEqual(self.sources.searches("datacite"), [TITLE])
        titles = [candidate.title for candidate in response.context["candidates"]]
        # The same title first; another work on another topic is left out.
        self.assertEqual(titles[0], TITLE)
        self.assertNotIn("Deep residual learning for image recognition", titles)
        first = response.context["candidates"][0]
        self.assertEqual(
            (first.same_title, first.year_found, first.author_found), (True, True, True)
        )
        self.assertContains(response, "Premier auteur concordant")

    def test_the_beginning_of_a_long_title(self):
        long_title = (
            "Measurement of quench back behavior on the normal zone propagation velocity "
            "in a superconducting magnet"
        )
        found = [crossref_item(long_title, "10.1000/long")]
        self.sources.add(crossref_searches={"Measurement of quench back behavior": found})
        response = self.client.get(URL, {"title": "Measurement of quench back behavior"})
        self.assertEqual([c.doi for c in response.context["candidates"]], ["10.1000/long"])
        self.assertContains(response, "Titre proche")

    def test_without_author_none_is_required(self):
        response = self.search()
        candidates = response.context["candidates"]
        self.assertTrue(candidates)
        self.assertTrue(all(candidate.author_found is None for candidate in candidates))

    def test_a_work_found_is_added_by_its_doi(self):
        response = self.search()
        self.assertContains(response, f'action="{reverse("corpus_add_by_identifier")}"')
        self.assertContains(response, 'name="identifier" value="10.5555/attention"')
        self.assertContains(response, f'value="{URL}?title=Attention+is+all+you+need"')
        self.assertFalse(Publication.objects.exists())  # nothing created before the click

    def test_a_publication_of_the_base_comes_first_once(self):
        pub = Publication.objects.create(doi="10.5555/attention", title=TITLE)
        response = self.search()
        candidates = response.context["candidates"]
        self.assertEqual(candidates[0].publication, pub)
        self.assertEqual([c.doi for c in candidates].count("10.5555/attention"), 1)
        self.assertContains(response, f'action="{reverse("corpus_add", args=[pub.pk])}"')
        self.assertContains(response, "Dans la base")

    def test_a_publication_of_my_corpus(self):
        pub = Publication.objects.create(doi="10.5555/attention", title=TITLE)
        UserPublication.objects.create(user=self.user, publication=pub)
        response = self.search()
        self.assertContains(response, "Dans votre corpus")
        self.assertNotContains(response, f'action="{reverse("corpus_add", args=[pub.pk])}"')

    def test_the_sources_are_asked_once(self):
        self.search()
        self.search()
        self.assertEqual(len(self.sources.searches("crossref")), 1)

    def test_a_source_that_fails_is_said_and_asked_again(self):
        self.sources.add(unreachable=["datacite"])
        response = self.search()
        self.assertContains(response, "a pas répondu : la liste peut être incomplète")
        self.search()
        self.assertEqual(len(self.sources.searches("crossref")), 2)

    def test_nothing_close(self):
        self.sources.add(crossref_searches={TITLE: [CROSSREF[2]]})
        response = self.search()
        self.assertContains(response, "Aucune publication proche de ce titre.")

    def test_visitors_are_sent_to_the_login_page(self):
        self.client.logout()
        self.assertRedirects(self.client.get(URL), f"{reverse('login')}?next={URL}")


class TitleSearchFormTests(TestCase):
    def test_at_least_two_words(self):
        for title in ("", "Attention", "the of and"):
            with self.subTest(title=title):
                self.assertFalse(TitleSearchForm({"title": title}).is_valid())

    def test_spaces_are_collapsed(self):
        form = TitleSearchForm({"title": "  Attention   is all  ", "author": " Vaswani "})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["title"], "Attention is all")
        self.assertEqual(form.cleaned_data["author"], "Vaswani")
