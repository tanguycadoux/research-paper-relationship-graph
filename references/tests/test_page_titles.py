"""
Titles of the pages (#417): the <h1> of a page of the menu, or of a page reached from
one, is its group of the navigation; the page itself is the first <h2>; the headings then
follow each other without skipping a level; the <title> reads « Page · Group · … ».
Their content takes the whole width of the window: no max-w around it (#453).
"""

import re
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import (
    Author,
    AuthorPublication,
    CitedReference,
    Publication,
    UserPublication,
)
from references.templatetags.navigation import NAVIGATION


class Headings(HTMLParser):
    """The headings of a page, in order: (level, text), and the text of its <title>."""

    def __init__(self, html):
        super().__init__()
        self.headings, self.title, self.open = [], "", None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if re.fullmatch(r"h[1-6]", tag):
            self.open = [int(tag[1]), ""]
        elif tag == "title":
            self.open = [0, ""]

    def handle_endtag(self, tag):
        if self.open is None or tag not in ("title", f"h{self.open[0]}"):
            return
        text = " ".join(self.open[1].split())
        if self.open[0]:
            self.headings.append((self.open[0], text))
        else:
            self.title = text
        self.open = None

    def handle_data(self, data):
        if self.open is not None:
            self.open[1] += data


# The page of each link of the menu, by URL name: its <h2>, which begins with it.
MENU_PAGES = {
    "corpus": "Publications",
    "corpus_suggestions": "Suggestions",
    "corpus_graph": "Graphe",
    "corpus_keywords": "Mots-clés",
    "publication_list": "Publications",
    "author_list": "Auteurs",
    "author_merge_select": "Combiner des auteurs",
    "author_duplicates": "Doublons probables",
    "conflict_list": "Conflits",
    "fetch_queue_admin": "File des récupérations",
}


class PageTitleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice", is_staff=True)
        source = Publication.objects.create(title="Source")
        cited = Publication.objects.create(title="Cité")
        CitedReference.objects.create(source=source, target=cited, position=0)
        UserPublication.objects.create(user=cls.user, publication=source)
        cls.authors = [Author.objects.create(last_name=name) for name in ("Ada", "Ada")]
        for order, author in enumerate(cls.authors):
            AuthorPublication.objects.create(publication=source, author=author, order=order)

    def setUp(self):
        self.client.force_login(self.user)

    def assert_titled(self, url, group, page):
        with self.subTest(url=url):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            parsed = Headings(response.content.decode())
            levels = [level for level, _ in parsed.headings]
            self.assertEqual(levels.count(1), 1)
            self.assertEqual(parsed.headings[0], (1, group))
            self.assertEqual(parsed.headings[1][0], 2)
            self.assertTrue(parsed.headings[1][1].startswith(page), parsed.headings[1])
            for previous, level in zip(levels, levels[1:], strict=False):
                self.assertLessEqual(level, previous + 1, parsed.headings)
            self.assertTrue(parsed.title.startswith(f"{page} · {group} · "), parsed.title)
            column = re.search(
                r'<main[^>]*class="([^"]*)"[^>]*>\s*<div class="([^"]*)"', response.content.decode()
            )
            self.assertNotIn("max-w", " ".join(column.groups()))

    def test_the_pages_of_the_menu_are_titled_by_their_group(self):
        menu = [(entry[1], title) for title, _, links in NAVIGATION for entry in links]
        self.assertEqual({name for name, _ in menu}, set(MENU_PAGES))
        for name, group in menu:
            self.assert_titled(reverse(name), group, MENU_PAGES[name])

    def test_the_pages_reached_from_the_menu_take_its_group(self):
        ids = ",".join(str(author.pk) for author in self.authors)
        for url, group, page in [
            (reverse("tag_list"), "Mon corpus", "Tags"),
            (reverse("base_graph"), "Base commune", "Graphe des publications"),
            (reverse("authors_graph"), "Base commune", "Graphe des auteurs"),
            (reverse("publication_title_search"), "Base commune", "Chercher par titre"),
            (reverse("publication_create"), "Base commune", "Saisir une publication à la main"),
            (reverse("author_merge_confirm", args=[ids]), "Corrections", "Fusionner 2 auteurs"),
        ]:
            self.assert_titled(url, group, page)
