from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.template import Context, Template
from django.test import RequestFactory, TestCase

from references.models import (
    Author,
    CitedReference,
    MetadataConflict,
    Publication,
    UserPublication,
)
from references.services.display import pending
from references.templatetags.navigation import current_url


def render_navigation(path, user):
    request = RequestFactory().get(path)
    template = Template("{% load navigation %}{% main_navigation %}")
    return template.render(Context({"request": request, "user": user}))


class CurrentUrlTests(TestCase):
    URLS = ["/corpus/", "/corpus/graph/", "/publications/", "/authors/", "/authors/merge/"]

    def test_the_longest_parent_wins(self):
        self.assertEqual(current_url(self.URLS, "/authors/merge/1,2/"), "/authors/merge/")
        self.assertEqual(current_url(self.URLS, "/corpus/graph/"), "/corpus/graph/")
        self.assertEqual(current_url(self.URLS, "/publications/3/edit/"), "/publications/")

    def test_a_link_with_a_query_is_current_on_its_filtered_page(self):
        user = get_user_model().objects.create_user("hugo")
        html = render_navigation("/corpus/?to_identify=1&sort=year", user)
        self.assertIn("À identifier", html.split('aria-current="page"')[1].split("</a>")[0])
        html = render_navigation("/corpus/?sort=year", user)
        self.assertIn("Publications", html.split('aria-current="page"')[1].split("</a>")[0])

    def test_root_matches_only_itself(self):
        self.assertIsNone(current_url(["/", "/publications/"], "/conflicts/"))
        self.assertEqual(current_url(["/", "/publications/"], "/"), "/")


class MainNavigationTests(TestCase):
    def current_link(self, path, current):
        user = get_user_model().objects.create_user(f"user{path.count('/')}{len(path)}")
        html = render_navigation(path, user)
        # Once in the menus of a small screen, once in the sidebar (#207).
        self.assertEqual(html.count("aria-current"), 2)
        return html.split(f'aria-current="{current}"')[1].split("</a>")[0]

    def test_current_page(self):
        self.assertIn("Publications", self.current_link("/publications/", "page"))

    def test_page_below_a_link(self):
        self.assertIn("Combiner des auteurs", self.current_link("/authors/merge/1,2/", "true"))

    def test_private_groups_are_hidden_from_visitors(self):
        html = render_navigation("/", AnonymousUser())
        self.assertIn("Publications", html)
        self.assertNotIn("Mon corpus", html)
        self.assertNotIn("Conflits", html)

    def test_short_menu_names_below_sm(self):
        # #331: the three menus fit in 390 px.
        user = get_user_model().objects.create_user("jade")
        html = render_navigation("/", user)
        summaries = [part.split("</summary>")[0] for part in html.split("<summary")[1:]]
        self.assertIn('<span class="sm:hidden">Corpus</span>', summaries[0])
        self.assertIn('<span class="hidden sm:inline">Mon corpus</span>', summaries[0])
        self.assertIn('<span class="sm:hidden">Base</span>', summaries[1])
        self.assertNotIn("sm:hidden", summaries[2])

    def test_one_menu_per_group_on_a_small_screen(self):
        user = get_user_model().objects.create_user("gina")
        html = render_navigation("/authors/merge/", user)
        self.assertEqual(html.count('<details name="navigation"'), 3)
        # The menu of the current page stands out.
        menus = html.split("<summary")[1:]
        current = [
            menu for menu in menus if "bg-gray-100 font-semibold" in menu.split("</summary>")[0]
        ]
        self.assertEqual(len(current), 1)
        self.assertIn("Corrections", current[0].split("</summary>")[0])

    def test_a_single_group_keeps_its_links_in_view(self):
        self.assertNotIn("<details", render_navigation("/", AnonymousUser()))

    def test_graph_of_the_base_and_of_the_corpus(self):
        # Two graphs (#131): /corpus/graph/ does not start with /graph/.
        self.assertIn("Graphe", self.current_link("/graph/", "page"))
        self.assertIn("Mon graphe", self.current_link("/corpus/graph/", "page"))
        self.assertIn("Graphe", render_navigation("/", AnonymousUser()))


class NavigationCounterTests(TestCase):
    """What waits for an action, counted in the navigation (#152)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("erin")
        pub = Publication.objects.create(title="Mienne")
        UserPublication.objects.create(user=cls.user, publication=pub)
        CitedReference.objects.create(source=pub, position=0, unstructured="À trouver")
        CitedReference.objects.create(
            source=pub, position=1, unstructured="Rapport", unidentifiable=True
        )
        CitedReference.objects.create(source=pub, target=pub, position=2)
        # Not in the corpus of the user: not counted.
        other = Publication.objects.create(title="Autre")
        CitedReference.objects.create(source=other, position=0, unstructured="Ailleurs")

    def link(self, html, url):
        return html.split(f'href="{url}"')[1].split("</a>")[0]

    def test_counts_with_a_text_for_screen_readers(self):
        MetadataConflict.objects.create(
            kind="orcid",
            publication=Publication.objects.get(title="Mienne"),
            field="orcid",
            current_value="a",
            proposed_value="b",
            source="crossref",
        )
        html = render_navigation("/", self.user)
        self.assertIn(
            '<span class="sr-only">, 1 en attente</span>', self.link(html, "/corpus/?to_identify=1")
        )
        # Publications has no counter: the count is not read as a number of publications.
        self.assertNotIn("sr-only", self.link(html, "/corpus/"))
        self.assertIn('<span class="sr-only">, 1 en attente</span>', self.link(html, "/conflicts/"))

    def test_the_menu_of_a_group_shows_the_total_of_its_counters(self):
        html = render_navigation("/", self.user)
        corpus_menu = html.split("<summary")[1].split("</summary>")[0]
        self.assertIn("Mon corpus", corpus_menu)
        self.assertIn('<span class="sr-only">, 1 à traiter</span>', corpus_menu)

    def test_nothing_at_zero(self):
        html = render_navigation("/", self.user)
        self.assertNotIn("sr-only", self.link(html, "/conflicts/"))

    def test_visitors_have_no_counter_and_no_query(self):
        with self.assertNumQueries(0):
            html = render_navigation("/", AnonymousUser())
        self.assertNotIn("sr-only", html)

    def test_a_constant_number_of_queries(self):
        cache.clear()
        # One per counter; for the probable duplicates, two for the key of the cache,
        # and two more to count them when the authors have changed.
        with self.assertNumQueries(6):
            render_navigation("/", self.user)
        with self.assertNumQueries(4):
            render_navigation("/", self.user)
        Author.objects.bulk_create(Author(first_name="A.", last_name=f"N{i}") for i in range(20))
        with self.assertNumQueries(6):
            render_navigation("/", self.user)

    def test_the_duplicates_are_counted_again_when_a_name_changes(self):
        cache.clear()
        Author.objects.create(first_name="Ada", last_name="Lovelace")
        other = Author.objects.create(first_name="Alan", last_name="Lovelace")
        self.assertEqual(pending.probable_duplicates(), 0)
        Author.objects.filter(pk=other.pk).update(first_name="A.")
        self.assertEqual(pending.probable_duplicates(), 1)

    def test_probable_duplicates_are_counted(self):
        # #270: like the conflicts, something to look at.
        Author.objects.create(first_name="Ada", last_name="Lovelace")
        Author.objects.create(first_name="A.", last_name="Lovelace")
        html = render_navigation("/", self.user)
        self.assertIn(
            '<span class="sr-only">, 1 à examiner</span>', self.link(html, "/authors/duplicates/")
        )
