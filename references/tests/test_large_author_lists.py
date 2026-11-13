"""
Publications of large collaborations, with more than 1 000 authors (#268). On SQLite,
Django prefetches a foreign key (`authorpublication_set__author`) with one OR term
per related object: beyond 1 000 authors, SQLite refuses the expression tree.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from references.models import (
    Author,
    AuthorPublication,
    CitedReference,
    Organization,
    Publication,
    UserPublication,
)
from references.services.corpus.corpus_transfer import corpus_bibtex
from references.services.corrections.candidates import local_candidates
from references.tests.helpers import without_candidate_search

AUTHORS = 1100
TITLE = "Observation of Gravitational Waves from a Binary Black Hole Merger"


class LargeAuthorListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")
        cls.pub = Publication.objects.create(doi="10.1103/physrevlett.116.061102", title=TITLE)
        authors = Author.objects.bulk_create(
            Author(first_name=f"A{index}", last_name=f"Author{index}") for index in range(AUTHORS)
        )
        slots = AuthorPublication.objects.bulk_create(
            AuthorPublication(publication=cls.pub, author=author, order=index)
            for index, author in enumerate(authors)
        )
        cls.add_affiliations(slots)
        UserPublication.objects.create(user=cls.user, publication=cls.pub)
        cls.citing = Publication.objects.create(doi="10.1000/citing", title="Citing")
        cls.ref = CitedReference.objects.create(
            source=cls.citing, position=0, raw={"article-title": TITLE, "year": "2016"}
        )

    @classmethod
    def add_affiliations(cls, slots):
        """Every author at the same laboratory, part of a larger organization."""
        parent = Organization.objects.create(name="LIGO")
        lab = Organization.objects.create(name="LIGO Hanford Observatory")
        lab.ancestors.add(parent)
        links = AuthorPublication.organizations.through
        links.objects.bulk_create(links(authorpublication=slot, organization=lab) for slot in slots)

    def test_bibtex_export_lists_every_author_in_order(self):
        bibtex = corpus_bibtex(self.user)
        authors = bibtex.split("author = {")[1].split("},")[0].split(" and ")
        self.assertEqual(len(authors), AUTHORS)
        self.assertEqual(authors[:2], ["Author0, A0", "Author1, A1"])

    def test_local_candidate_gives_its_first_authors(self):
        (candidate,) = local_candidates(self.ref)
        self.assertEqual(candidate.publication, self.pub)
        self.assertEqual(candidate.authors, ("Author0", "Author1", "Author2"))

    @without_candidate_search
    def test_pages_that_load_the_authors_of_the_publication(self):
        self.client.force_login(self.user)
        author = Author.objects.get(last_name="Author0")
        pages = [
            reverse("publication_detail", args=[self.pub.pk]),
            reverse("publication_graph", args=[self.pub.pk]),
            reverse("publication_list"),
            reverse("author_list"),
            reverse("author_detail", args=[author.pk]),
            reverse("author_duplicates"),
            reverse("corpus"),
            reverse("corpus_graph"),
            reverse("corpus_export_bibtex"),
            reverse("base_graph"),
            reverse("reference_identify", args=[self.citing.pk, self.ref.position]),
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
