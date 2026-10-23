from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.template import Context, Template
from django.test import RequestFactory, TestCase

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

    def test_root_matches_only_itself(self):
        self.assertIsNone(current_url(["/", "/publications/"], "/conflicts/"))
        self.assertEqual(current_url(["/", "/publications/"], "/"), "/")


class MainNavigationTests(TestCase):
    def current_link(self, path, current):
        user = get_user_model().objects.create_user(f"user{path.count('/')}{len(path)}")
        html = render_navigation(path, user)
        self.assertEqual(html.count("aria-current"), 1)
        return html.split(f'aria-current="{current}"')[1].split("</a>")[0]

    def test_current_page(self):
        self.assertIn("Publications", self.current_link("/publications/", "page"))

    def test_page_below_a_link(self):
        self.assertIn("Combiner des auteurs", self.current_link("/authors/merge/1,2/", "true"))

    def test_private_groups_are_hidden_from_visitors(self):
        html = render_navigation("/", AnonymousUser())
        self.assertIn("Publications", html)
        self.assertNotIn("Mes références", html)
        self.assertNotIn("Conflits", html)

    def test_graph_of_the_base_and_of_the_corpus(self):
        # Two graphs (#131): /corpus/graph/ does not start with /graph/.
        self.assertIn("Graphe", self.current_link("/graph/", "page"))
        self.assertIn("Mon graphe", self.current_link("/corpus/graph/", "page"))
        self.assertIn("Graphe", render_navigation("/", AnonymousUser()))
