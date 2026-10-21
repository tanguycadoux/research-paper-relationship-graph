from django.contrib.auth import get_user_model
from django.test import TestCase

from references.models import CitedReference, Publication, UserPublication
from references.services.corpus import add_to_corpus
from references.tests.helpers import without_other_sources
from references.tests.test_importer import SOURCE_DOI, with_mocked_crossref


@without_other_sources
@with_mocked_crossref
class CorpusReferencesTests(TestCase):
    """References are imported while a publication is in at least one corpus (#23)."""

    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user("alice")
        self.bob = User.objects.create_user("bob")
        self.pub = Publication.objects.create(doi=SOURCE_DOI)

    def test_outside_any_corpus_references_are_not_wanted(self, fetch, fetch_works):
        self.assertFalse(self.pub.parse_references)

    def test_in_the_corpus_of_any_user_references_are_wanted(self, fetch, fetch_works):
        add_to_corpus(self.alice, self.pub)
        self.assertTrue(self.pub.parse_references)
        self.assertEqual(CitedReference.objects.filter(source=self.pub).count(), 2)

    def test_still_wanted_while_another_user_keeps_it(self, fetch, fetch_works):
        add_to_corpus(self.alice, self.pub)
        add_to_corpus(self.bob, self.pub)
        UserPublication.objects.filter(user=self.alice).delete()
        self.assertTrue(self.pub.parse_references)

    def test_leaving_the_last_corpus_keeps_imported_references(self, fetch, fetch_works):
        add_to_corpus(self.alice, self.pub)
        UserPublication.objects.filter(user=self.alice).delete()
        self.assertFalse(self.pub.parse_references)
        self.assertEqual(CitedReference.objects.filter(source=self.pub).count(), 2)
