from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from references.models import MetadataConflict, Organization, Publication
from references.services.imports.parser import parse_publication
from references.services.sources.external_records import Source, store_record
from references.tests.helpers import with_crossref

CEA = {
    "id": "https://openalex.org/I2738703131",
    "display_name": "CEA",
    "lineage": ["https://openalex.org/I2738703131"],
}
IRFU = {
    "id": "https://openalex.org/I4210165232",
    "display_name": "IRFU",
    "lineage": ["https://openalex.org/I2738703131", "https://openalex.org/I4210165232"],
}
WORK = {"authorships": [{"raw_author_name": "Thomas Thuillier", "institutions": [IRFU]}]}


def parsed_publication(doi):
    pub = Publication.objects.create(doi=doi, title="A")
    with_crossref(
        pub, {"message": {"title": ["A"], "author": [{"given": "Thomas", "family": "Thuillier"}]}}
    )
    parse_publication(pub)
    return pub


def run(*args):
    out = StringIO()
    call_command("complete_affiliations", *args, stdout=out)
    return out.getvalue()


class CompleteAffiliationsCommandTests(TestCase):
    def organizations(self, pub):
        return [str(o) for o in pub.authorpublication_set.get().organizations.all()]

    @patch("references.services.imports.enrichment.fetch_openalex_works")
    @patch(
        "references.services.imports.enrichment.fetch_openalex_institutions",
        return_value={"I2738703131": CEA},
    )
    def test_uses_the_stored_works_without_requesting_the_publications(self, institutions, works):
        pub = parsed_publication("10.1000/a")
        store_record(pub, Source.OPENALEX, WORK)

        output = run()

        works.assert_not_called()
        institutions.assert_called_once_with(["I2738703131"])
        self.assertEqual(self.organizations(pub), ["IRFU"])
        irfu = Organization.objects.get(name="IRFU")
        self.assertEqual([str(a) for a in irfu.ancestors.all()], ["CEA"])
        self.assertIn("Publications dont les affiliations sont rattachées : 1", output)

    def test_refresh_ancestors_repairs_a_known_ancestor(self):
        drf = {
            "id": "https://openalex.org/I4210113668",
            "display_name": "DRF",
            "lineage": ["https://openalex.org/I2738703131", "https://openalex.org/I4210113668"],
        }
        irfu = IRFU | {"lineage": IRFU["lineage"] + [drf["id"]]}
        pub = parsed_publication("10.1000/a")
        store_record(
            pub,
            Source.OPENALEX,
            {"authorships": [WORK["authorships"][0] | {"institutions": [irfu, CEA]}]},
        )
        Organization.objects.create(name="DRF", openalex_id="I4210113668")  # without its ancestors

        with patch(
            "references.services.imports.enrichment.fetch_openalex_institutions", return_value={}
        ) as fetch:
            run()
        fetch.assert_not_called()
        with patch(
            "references.services.imports.enrichment.fetch_openalex_institutions",
            return_value={"I4210113668": drf},
        ) as fetch:
            run("--refresh-ancestors")
        fetch.assert_called_once_with(["I4210113668"])
        repaired = Organization.objects.get(name="DRF")
        self.assertEqual([str(a) for a in repaired.ancestors.all()], ["CEA"])

    @patch(
        "references.services.imports.enrichment.fetch_openalex_institutions",
        return_value={"I2738703131": CEA},
    )
    def test_fetch_missing_requests_the_publications_without_openalex(self, _institutions):
        pub = parsed_publication("10.1000/a")
        known = parsed_publication("10.1000/known")
        store_record(known, Source.OPENALEX, None)  # already answered: not requested again
        with patch(
            "references.services.imports.enrichment.fetch_openalex_works",
            return_value={"10.1000/a": WORK},
        ) as works:
            output = run("--fetch-missing")
        works.assert_called_once_with(["10.1000/a"])
        self.assertEqual(self.organizations(pub), ["IRFU"])
        self.assertIn("Publications demandées à OpenAlex : 1", output)


THUILLIER_ONLY = {"raw_author_name": "Thomas Thuillier", "institutions": []}


class FalseAuthorConflictsTests(TestCase):
    """Conflicts reported before #265 on a truncated or empty author list are closed."""

    def test_publication_without_authors_takes_the_openalex_ones(self):
        pub = Publication.objects.create(doi="10.1017/9781316809976.027", title="A")
        with_crossref(pub, {"message": {"title": ["A"], "author": []}})
        MetadataConflict.objects.create(
            kind=MetadataConflict.Kind.AUTHORS_MISMATCH,
            publication=pub,
            field="authors",
            current_value="0 auteur : ",
            proposed_value="1 auteur : Thomas Thuillier",
            source=Source.OPENALEX,
        )
        store_record(pub, Source.OPENALEX, {"authorships": [THUILLIER_ONLY]})
        output = run()
        self.assertFalse(MetadataConflict.objects.exists())
        self.assertEqual(str(pub.authorpublication_set.get().author), "Thomas Thuillier")
        self.assertIn("Publications sans auteur complétées par OpenAlex : 1", output)

    def test_conflict_on_a_truncated_list_is_closed(self):
        authors = [{"given": "Thomas", "family": "Thuillier"}] * 101
        pub = Publication.objects.create(doi="10.1007/lrr-2016-1", title="A")
        with_crossref(pub, {"message": {"title": ["A"], "author": authors}})
        parse_publication(pub)  # no OpenAlex answer yet
        MetadataConflict.objects.create(
            kind=MetadataConflict.Kind.AUTHORS_MISMATCH,
            publication=pub,
            field="authors",
            current_value="101 auteurs",
            proposed_value="100 auteurs",
            source=Source.OPENALEX,
        )
        store_record(pub, Source.OPENALEX, {"authorships": [THUILLIER_ONLY] * 100})
        run()
        self.assertFalse(MetadataConflict.objects.exists())

    def test_a_real_difference_stays_reported(self):
        pub = parsed_publication("10.1000/a")
        store_record(pub, Source.OPENALEX, {"authorships": [{"raw_author_name": "Someone Else"}]})
        run()
        self.assertTrue(MetadataConflict.objects.filter(publication=pub).exists())
