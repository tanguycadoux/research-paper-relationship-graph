from django.test import TestCase

from references.models import Author, AuthorPublication, MetadataConflict, Publication
from references.services import conflicts
from references.services.affiliations import attach_affiliations
from references.services.external_records import Source, store_record
from references.services.parser import parse_publication
from references.tests.helpers import with_crossref

LECUN = {"given": "Yann", "family": "LeCun"}
BENGIO = {"given": "Yoshua", "family": "Bengio"}


def authorship(raw_name, orcid=None):
    author = {"orcid": f"https://orcid.org/{orcid}"} if orcid else {}
    return {"raw_author_name": raw_name, "institutions": [], "author": author}


def publication(authors, authorships):
    pub = Publication.objects.create(title="Deep learning")
    with_crossref(pub, {"message": {"title": ["Deep learning"], "author": authors}})
    store_record(pub, Source.OPENALEX, {"authorships": authorships})
    parse_publication(pub)
    return pub


def author_named(family):
    return Author.objects.get(last_name=family)


class CompleteOrcidTests(TestCase):
    def test_missing_orcids_are_completed(self):
        publication(
            [LECUN, BENGIO],
            [authorship("Yann LeCun", "0000-0002-1992-2684"), authorship("Yoshua Bengio")],
        )
        self.assertEqual(author_named("LeCun").orcid, "0000-0002-1992-2684")
        self.assertEqual(author_named("Bengio").orcid, "")

    def test_published_orcid_of_the_signature_is_untouched(self):
        pub = publication([LECUN], [authorship("Yann LeCun", "0000-0002-1992-2684")])
        self.assertEqual(AuthorPublication.objects.get(publication=pub).published_orcid, "")

    def test_same_orcid_changes_nothing(self):
        lecun = {**LECUN, "ORCID": "https://orcid.org/0000-0002-1992-2684"}
        publication([lecun], [authorship("Yann LeCun", "0000-0002-1992-2684")])
        self.assertFalse(MetadataConflict.objects.exists())

    def test_different_orcid_is_kept_and_reported(self):
        lecun = {**LECUN, "ORCID": "https://orcid.org/0000-0001-1111-1111"}
        publication([lecun], [authorship("Yann LeCun", "0000-0002-1992-2684")])
        author = author_named("LeCun")
        self.assertEqual(author.orcid, "0000-0001-1111-1111")
        conflict = MetadataConflict.objects.get()
        self.assertEqual(
            (conflict.kind, conflict.author, conflict.current_value, conflict.proposed_value),
            (conflicts.Kind.ORCID, author, "0000-0001-1111-1111", "0000-0002-1992-2684"),
        )

    def test_accepting_the_conflict_replaces_the_orcid(self):
        lecun = {**LECUN, "ORCID": "https://orcid.org/0000-0001-1111-1111"}
        publication([lecun], [authorship("Yann LeCun", "0000-0002-1992-2684")])
        conflicts.resolve(MetadataConflict.objects.get(), conflicts.Status.ACCEPTED, None)
        self.assertEqual(author_named("LeCun").orcid, "0000-0002-1992-2684")

    def test_kept_decision_is_not_reopened(self):
        lecun = {**LECUN, "ORCID": "https://orcid.org/0000-0001-1111-1111"}
        pub = publication([lecun], [authorship("Yann LeCun", "0000-0002-1992-2684")])
        conflicts.resolve(MetadataConflict.objects.get(), conflicts.Status.KEPT, None)
        parse_publication(pub)
        self.assertEqual(MetadataConflict.objects.get().status, conflicts.Status.KEPT)
        self.assertEqual(author_named("LeCun").orcid, "0000-0001-1111-1111")

    def test_nothing_when_the_authors_do_not_match(self):
        publication([LECUN, BENGIO], [authorship("Yann LeCun", "0000-0002-1992-2684")])
        self.assertEqual(author_named("LeCun").orcid, "")

    def test_one_author_on_two_slots_gets_one_orcid(self):
        pub = Publication.objects.create(title="A")
        author = Author.objects.create(first_name="Yann", last_name="LeCun")
        for order, given in enumerate(["Yann", "Y."]):
            AuthorPublication.objects.create(
                publication=pub,
                author=author,
                order=order,
                published_given_name=given,
                published_family_name="LeCun",
            )
        store_record(
            pub,
            Source.OPENALEX,
            {
                "authorships": [
                    authorship("Yann LeCun", "0000-0002"),
                    authorship("Y. LeCun", "0000-0003"),
                ]
            },
        )
        attach_affiliations(pub)
        author.refresh_from_db()
        self.assertEqual(author.orcid, "0000-0002")
        self.assertEqual(MetadataConflict.objects.get().proposed_value, "0000-0003")
