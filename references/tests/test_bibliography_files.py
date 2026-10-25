from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import Publication, UserPublication
from references.services.bibliography_files import file_entries
from references.tests.helpers import with_crossref, without_other_sources
from references.tests.test_importer import with_mocked_crossref

ZOTERO_BIBTEX = r"""
@article{abbott_observation_2016,
	title = {Observation of {Gravitational} {Waves} from a {Binary} {Black} {Hole} {Merger}},
	volume = {116},
	url = {https://link.aps.org/doi/10.1103/PhysRevLett.116.061102},
	doi = {10.1103/PhysRevLett.116.061102},
	journal = {Physical Review Letters},
	author = {Abbott, B. P. and {LIGO Scientific Collaboration}},
	year = {2016},
	note = {Contact: someone@example.org},
}

@book{goodfellow_deep_2016,
	address = {Cambridge, Massachusetts},
	title = {Deep {Learning}},
	isbn = {978-0-262-03561-3 0-262-03561-8},
	publisher = {The MIT Press},
	year = {2016},
}

@misc{vaswani_attention_2023,
	title = {Attention {Is} {All} {You} {Need}},
	url = {http://arxiv.org/abs/1706.03762},
	doi = {10.48550/arXiv.1706.03762},
	publisher = {arXiv},
	year = {2023},
}
"""


class BibtexEntriesTests(SimpleTestCase):
    def test_zotero_export(self):
        self.assertEqual(
            file_entries(ZOTERO_BIBTEX),
            [
                {
                    "doi": "10.1103/physrevlett.116.061102",
                    "isbn": "",
                    "title": "Observation of Gravitational Waves from a Binary Black Hole Merger",
                },
                {"doi": "", "isbn": "9780262035613", "title": "Deep Learning"},
                {
                    "doi": "10.48550/arxiv.1706.03762",
                    "isbn": "",
                    "title": "Attention Is All You Need",
                },
            ],
        )

    def test_arxiv_eprint_becomes_its_doi(self):
        text = r"""@misc{vaswani2017,
            title={Attention Is All You Need},
            author={Ashish Vaswani and others},
            year={2017},
            eprint={1706.03762v7},
            archivePrefix={arXiv},
            primaryClass={cs.CL},
        }"""
        self.assertEqual(file_entries(text)[0]["doi"], "10.48550/arxiv.1706.03762")

    def test_old_arxiv_identifier(self):
        text = "@article{m, eprint = {hep-th/9711200}, archivePrefix = {arXiv}}"
        self.assertEqual(file_entries(text)[0]["doi"], "10.48550/arxiv.hep-th/9711200")

    def test_eprint_of_another_archive_is_not_arxiv(self):
        text = "@article{x, eprint = {1706.03762}, archivePrefix = {HAL}}"
        self.assertEqual(file_entries(text)[0]["doi"], "")

    def test_google_scholar_arxiv_reference_in_the_journal(self):
        text = """@article{vaswani2017attention,
          title={Attention is all you need},
          journal={arXiv preprint arXiv:1706.03762},
          year={2017}
        }"""
        self.assertEqual(file_entries(text)[0]["doi"], "10.48550/arxiv.1706.03762")

    def test_doi_with_escaped_underscore_or_resolver(self):
        text = r"""@article{a, doi = {10.1000/abc\_def}}
        @article{b, doi = "https://doi.org/10.1000/XYZ"}"""
        self.assertEqual(
            [entry["doi"] for entry in file_entries(text)], ["10.1000/abc_def", "10.1000/xyz"]
        )

    def test_quoted_values_concatenation_and_bare_numbers(self):
        text = r"""@string{prl = "Phys. Rev. Lett."}
        @comment{jabref-meta: databaseType:bibtex;}
        @Article{key,
          Title   = "A {\"U}ber " # "Title",
          Journal = prl,
          Year    = 2016,
          ISBN    = "0-262-03561-8; 978-0-262-03561-3"
        }"""
        self.assertEqual(
            file_entries(text), [{"doi": "", "isbn": "9780262035613", "title": "A Über Title"}]
        )

    def test_entry_without_identifier_keeps_its_title(self):
        text = "@techreport{r, title = {Rapport interne {CEA}}, year = {1998}}"
        self.assertEqual(
            file_entries(text), [{"doi": "", "isbn": "", "title": "Rapport interne CEA"}]
        )

    def test_malformed_entries_do_not_stop_the_reading(self):
        text = "@article{broken, title = {Pas fermé\n@article{ok, doi = {10.1000/ok}}"
        self.assertEqual(len(file_entries(text)), 1)
        text = "@article{garbage = = ,}\n@article{ok, doi = {10.1000/ok}}"
        self.assertEqual([entry["doi"] for entry in file_entries(text)], ["", "10.1000/ok"])

    def test_text_without_entries(self):
        self.assertEqual(file_entries("rien à lire ici, écrire à a@b.fr"), [])


class RisEntriesTests(SimpleTestCase):
    def test_zotero_export(self):
        text = "﻿" + "\r\n".join(
            [
                "TY  - JOUR",
                "TI  - Observation of Gravitational Waves from a Binary Black Hole Merger",
                "AU  - Abbott, B. P.",
                "DO  - 10.1103/PhysRevLett.116.061102",
                "SN  - 0031-9007",
                "ER  - ",
                "",
                "TY  - BOOK",
                "TI  - Deep Learning",
                "SN  - 978-0-262-03561-3",
                "ER  - ",
                "",
                "TY  - RPRT",
                "T1  - Rapport interne",
                "ER  - ",
                "",
                "TY  - PREP",
                "TI  - Attention Is All You Need",
                "UR  - http://arxiv.org/abs/1706.03762",
                "ER  - ",
            ]
        )
        self.assertEqual(
            file_entries(text),
            [
                {
                    "doi": "10.1103/physrevlett.116.061102",
                    "isbn": "",
                    "title": "Observation of Gravitational Waves from a Binary Black Hole Merger",
                },
                {"doi": "", "isbn": "9780262035613", "title": "Deep Learning"},
                {"doi": "", "isbn": "", "title": "Rapport interne"},
                {
                    "doi": "10.48550/arxiv.1706.03762",
                    "isbn": "",
                    "title": "Attention Is All You Need",
                },
            ],
        )


@without_other_sources
@with_mocked_crossref
class ImportBibliographyFileViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("bob")
        self.client.force_login(self.user)

    def post(self, name, content):
        upload = SimpleUploadedFile(name, content)
        return self.client.post(reverse("corpus_import"), {"file": upload}, follow=True)

    def test_bibtex_file_is_imported_and_entries_without_identifier_listed(
        self, fetch, fetch_works
    ):
        pub = with_crossref(Publication.objects.create(doi="10.1000/known"), {"message": {}})
        content = (
            "@article{a, doi = {10.1000/known}}\n"
            "@techreport{b, title = {Rapport interne}}\n"
            "@misc{c, year = {2020}}\n"
        )
        response = self.post("zotero.bib", content.encode())
        self.assertContains(response, "1 publication(s) ajoutée(s), 0 déjà dans votre corpus")
        self.assertContains(
            response,
            "2 entrée(s) ignorée(s), sans DOI, identifiant arXiv ni ISBN valide : "
            "« Rapport interne », une entrée sans titre.",
        )
        self.assertTrue(UserPublication.objects.filter(user=self.user, publication=pub).exists())

    def test_ris_file_in_latin1(self, fetch, fetch_works):
        content = "TY  - JOUR\nTI  - Étude\nDO  - 10.1000/known\nER  - \n".encode("latin-1")
        with_crossref(Publication.objects.create(doi="10.1000/known"), {"message": {}})
        self.assertContains(self.post("export.ris", content), "1 publication(s) ajoutée(s)")

    def test_long_list_of_ignored_entries_is_cut(self, fetch, fetch_works):
        content = "".join(f"@misc{{k{i}, title = {{Titre {i}}}}}\n" for i in range(12))
        self.assertContains(self.post("long.bib", content.encode()), "« Titre 9 » et 2 autre(s).")
