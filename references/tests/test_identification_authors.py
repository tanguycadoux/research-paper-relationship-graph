"""The authors of a reference identified without identifier (#259)."""

from django.test import TestCase
from django.urls import reverse

from references.forms import IdentifyReferenceForm
from references.models import Author, AuthorPublication, Publication
from references.services.corrections import identification, typed_authors
from references.tests.sources import simulated_sources
from references.tests.test_identification import IdentificationTestCase

CITED = {"key": "ref1", "author": "I. Goodfellow", "article-title": "Deep Learning", "year": "2016"}
LOWER_CASE = {"key": "ref2", "author": "rochepault", "volume-title": "Aimants"}
NO_AUTHOR = {"key": "ref3", "unstructured": "Private communication."}


def published(author, title="Autre"):
    pub = Publication.objects.create(title=title)
    AuthorPublication.objects.create(publication=pub, author=author, order=0)
    return pub


class TypedAuthorsTestCase(IdentificationTestCase):
    def setUp(self):
        super().setUp()
        self.parse([CITED, LOWER_CASE, NO_AUTHOR])
        self.ian = Author.objects.create(
            first_name="Ian", last_name="Goodfellow", orcid="0000-0001"
        )
        published(self.ian)


class CreationTests(TypedAuthorsTestCase):
    def test_existing_and_new_authors_in_order(self):
        typed = typed_authors.parse_lines(f"Bengio, Yoshua\n#{self.ian.pk}\nCourville")
        pub = identification.identify_without_identifier(
            self.ref(0), "Deep Learning", 2016, self.user, typed
        )
        slots = list(pub.authorpublication_set.order_by("order"))
        self.assertEqual([slot.order for slot in slots], [0, 1, 2])
        self.assertEqual(slots[1].author, self.ian)
        self.assertEqual(
            [(slot.published_family_name, slot.published_given_name) for slot in slots],
            [("Bengio", "Yoshua"), ("Goodfellow", "Ian"), ("Courville", "")],
        )
        self.assertEqual(slots[0].author.first_name, "Yoshua")

    def test_existing_author_is_never_modified(self):
        typed = typed_authors.parse_lines(f"#{self.ian.pk}")
        identification.identify_without_identifier(
            self.ref(0), "Deep Learning", 2016, self.user, typed
        )
        self.ian.refresh_from_db()
        self.assertEqual(
            (self.ian.first_name, self.ian.last_name, self.ian.orcid),
            ("Ian", "Goodfellow", "0000-0001"),
        )

    def test_new_author_is_not_matched_to_an_existing_one(self):
        typed = typed_authors.parse_lines("Goodfellow, Ian")
        pub = identification.identify_without_identifier(
            self.ref(0), "Deep Learning", 2016, self.user, typed
        )
        self.assertNotEqual(pub.authorpublication_set.get().author, self.ian)
        self.assertEqual(Author.objects.filter(last_name="Goodfellow").count(), 2)

    def test_without_authors(self):
        pub = identification.identify_without_identifier(
            self.ref(0), "Deep Learning", 2016, self.user
        )
        self.assertFalse(pub.authorpublication_set.exists())


class ParsingTests(TypedAuthorsTestCase):
    def test_spaces_and_blank_lines_are_ignored(self):
        typed = typed_authors.parse_lines("  Bengio ,  Yoshua \n\n")
        self.assertEqual([(t.family, t.given) for t in typed], [("Bengio", "Yoshua")])

    def test_malformed_line(self):
        for text in ("Bengio, Yoshua, Jr", ", Yoshua"):
            with self.subTest(text=text), self.assertRaises(typed_authors.AuthorLineError):
                typed_authors.parse_lines(text)

    def test_unknown_author(self):
        with self.assertRaisesMessage(typed_authors.AuthorLineError, "n° 999"):
            typed_authors.parse_lines("#999")

    def test_same_author_twice(self):
        with self.assertRaisesMessage(typed_authors.AuthorLineError, "deux fois"):
            typed_authors.parse_lines(f"#{self.ian.pk}\n#{self.ian.pk}")


class ProposalTests(TypedAuthorsTestCase):
    def test_first_cited_author_with_matches(self):
        Author.objects.create(first_name="Jean", last_name="Goodfellow")
        proposal = typed_authors.proposal(self.ref(0))
        self.assertEqual(proposal["line"], "Goodfellow, I.")
        self.assertEqual([match["id"] for match in proposal["matches"]], [self.ian.pk])
        self.assertEqual(proposal["matches"][0]["publications"], 1)

    def test_lower_case_name_without_match(self):
        proposal = typed_authors.proposal(self.ref(1))
        self.assertEqual(proposal, {"line": "Rochepault", "matches": []})

    def test_matches_ignore_accents_and_case(self):
        author = Author.objects.create(first_name="Étienne", last_name="Rochepault")
        proposal = typed_authors.proposal(self.ref(1))
        self.assertEqual([match["id"] for match in proposal["matches"]], [author.pk])

    def test_no_author_cited(self):
        self.assertIsNone(typed_authors.proposal(self.ref(2)))


class SuggestionRouteTests(TypedAuthorsTestCase):
    url = reverse("author_suggestions")

    def get(self, text):
        self.client.force_login(self.user)
        return self.client.get(self.url, {"q": text}).json()["results"]

    def test_visitors_are_refused(self):
        response = self.client.get(self.url, {"q": "Goodfellow"})
        self.assertEqual(response.status_code, 302)

    def test_by_name(self):
        results = self.get("goodf")
        self.assertEqual(results[0]["id"], self.ian.pk)
        self.assertEqual(results[0]["name"], "Ian Goodfellow")
        self.assertEqual(results[0]["publications"], 1)

    def test_typed_as_a_new_author(self):
        self.assertEqual([result["id"] for result in self.get("Goodfellow, Ian")], [self.ian.pk])

    def test_by_orcid(self):
        self.assertEqual([result["id"] for result in self.get("0000-0001")], [self.ian.pk])

    def test_too_short(self):
        self.assertEqual(self.get("g"), [])

    def test_limited(self):
        Author.objects.bulk_create(Author(last_name=f"Martin{index}") for index in range(15))
        self.assertEqual(len(self.get("martin")), typed_authors.SUGGESTION_LIMIT)


class FormTests(TestCase):
    def form(self, authors):
        return IdentifyReferenceForm({"method": "none", "title": "Livre", "authors": authors})

    def test_malformed_line_is_an_error_of_the_field(self):
        form = self.form("Bengio, Yoshua, Jr")
        self.assertFalse(form.is_valid())
        self.assertIn("Nom, Prénom", form.errors["authors"][0])

    def test_authors_ignored_with_a_doi(self):
        form = IdentifyReferenceForm({"method": "doi", "doi": "10.1000/x", "authors": "#999"})
        self.assertTrue(form.is_valid())


@simulated_sources()
class PageTests(TypedAuthorsTestCase):
    def url(self, position):
        return reverse("reference_identify", args=[self.source.pk, position])

    def test_sent_without_script(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url(0),
            {
                "method": "none",
                "title": "Deep Learning",
                "year": "2016",
                "authors": f"#{self.ian.pk}\r\nBengio, Yoshua\r\n",
            },
        )
        self.assertRedirects(response, reverse("publication_detail", args=[self.source.pk]))
        pub = self.ref(0).target
        self.assertEqual(
            [str(slot.author) for slot in pub.authorpublication_set.order_by("order")],
            ["Ian Goodfellow", "Yoshua Bengio"],
        )

    def test_wrong_line_keeps_the_form(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url(0), {"method": "none", "title": "Deep Learning", "authors": "#999"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "L&#x27;auteur n° 999 n&#x27;existe pas")
        self.assertIsNone(self.ref(0).target)
        self.assertEqual(Publication.objects.filter(title="Deep Learning").count(), 0)

    def test_proposal_and_entries_on_the_page(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url(0))
        self.assertContains(response, "La référence cite d'abord")
        self.assertContains(response, f"« #{self.ian.pk} » pour Ian Goodfellow")
        self.assertContains(response, 'id="author-entries"')
        self.assertEqual(response.context["author_entries"], [])

    def test_entries_rebuilt_after_an_error(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url(0), {"method": "none", "title": "", "authors": f"#{self.ian.pk}\nBengio"}
        )
        entries = response.context["author_entries"]
        self.assertEqual([entry["line"] for entry in entries], [f"#{self.ian.pk}", "Bengio"])
        self.assertEqual(entries[0]["name"], "Ian Goodfellow")
