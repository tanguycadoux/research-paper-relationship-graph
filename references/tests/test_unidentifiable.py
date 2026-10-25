from django.urls import reverse

from references.models import Publication
from references.services import identification
from references.services.identification import with_references_to_identify
from references.tests.helpers import without_candidate_search
from references.tests.test_identification import (
    BOOK,
    NO_KEY,
    WITH_DOI,
    IdentificationTestCase,
)


class UnidentifiableReferenceTests(IdentificationTestCase):
    """A reference matching no importable publication leaves the count to identify (#129)."""

    def to_identify(self):
        return with_references_to_identify(Publication.objects).get(pk=self.source.pk).to_identify

    def test_declaration_is_traced_and_no_longer_counted(self):
        self.assertEqual(self.to_identify(), 2)
        identification.declare_unidentifiable(self.ref(1), self.user)
        ref = self.ref(1)
        self.assertTrue(ref.unidentifiable)
        self.assertTrue(ref.resolved_manually)
        self.assertEqual(ref.resolved_by, self.user)
        self.assertEqual(self.to_identify(), 1)

    def test_declaration_unlinks_the_reference(self):
        previous = self.ref(2).target
        identification.declare_unidentifiable(self.ref(2), self.user)
        self.assertIsNone(self.ref(2).target)
        # Empty, cited by nothing else: removed like after a new identification.
        self.assertFalse(Publication.objects.filter(pk=previous.pk).exists())

    def test_kept_when_the_source_is_imported_again(self):
        identification.declare_unidentifiable(self.ref(1), self.user)
        self.parse([BOOK, NO_KEY, WITH_DOI])
        self.assertTrue(self.ref(1).unidentifiable)
        self.assertEqual(self.to_identify(), 1)

    def test_cancel(self):
        identification.declare_unidentifiable(self.ref(1), self.user)
        identification.cancel_unidentifiable(self.ref(1))
        ref = self.ref(1)
        self.assertFalse(ref.unidentifiable)
        self.assertFalse(ref.resolved_manually)
        self.assertIsNone(ref.resolved_by)
        self.assertEqual(self.to_identify(), 2)

    def test_a_later_identification_replaces_the_declaration(self):
        identification.declare_unidentifiable(self.ref(0), self.user)
        pub = identification.identify_without_identifier(self.ref(0), "Deep Learning", None, None)
        self.assertEqual(self.ref(0).target, pub)
        self.assertFalse(self.ref(0).unidentifiable)


@without_candidate_search
class UnidentifiableViewTests(IdentificationTestCase):
    def url(self, position):
        return reverse("reference_unidentifiable", args=[self.source.pk, position])

    def detail(self):
        return self.client.get(reverse("publication_detail", args=[self.source.pk]))

    def test_login_and_post_required(self):
        self.assertEqual(self.client.post(self.url(1)).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url(1)).status_code, 405)

    def test_declare_then_cancel(self):
        self.client.force_login(self.user)
        identify_page = self.client.get(reverse("reference_identify", args=[self.source.pk, 1]))
        self.assertContains(identify_page, "Déclarer non identifiable")

        response = self.client.post(self.url(1), follow=True)
        self.assertContains(response, "déclarée non identifiable")
        # Only the reference left to identify stays highlighted.
        self.assertContains(response, 'class="bg-amber-50"', count=1)
        self.assertEqual(response.context["references_to_identify"], 1)
        self.assertEqual(response.context["references_unidentifiable"], 1)

        identify_page = self.client.get(reverse("reference_identify", args=[self.source.pk, 1]))
        self.assertContains(identify_page, "Annuler « non identifiable »")
        # A valid HTML date: no microseconds (#143).
        self.assertRegex(
            identify_page.content.decode(),
            r'datetime="\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d{4}"',
        )
        self.client.post(self.url(1))
        self.assertFalse(self.ref(1).unidentifiable)

    def test_summary_when_nothing_is_left_to_identify(self):
        for position in (0, 1):
            identification.declare_unidentifiable(self.ref(position), self.user)
        self.assertContains(self.detail(), "ou déclarées non identifiables")
