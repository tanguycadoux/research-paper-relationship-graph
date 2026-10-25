import gzip
import io
import tarfile
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from references.models import CitedReference, Publication
from references.services import http
from references.services.corpus import add_to_corpus
from references.services.external_records import Source, store_record
from references.services.importer import import_publication
from references.services.latex_bibliography import (
    clean_latex,
    read_eprint,
    references,
    written_identifier,
)
from references.services.metadata_formats import bibliography_source
from references.tests.helpers import without_openalex, without_orcid

ARXIV = "10.48550/arxiv.1706.03762"
INLINE_TEX = r"""
\documentclass{article}
\begin{document}
Text \cite{layernorm2016}.
\begin{thebibliography}{10}
\bibitem{layernorm2016}
Jimmy~Lei Ba, Jamie~Ryan Kiros, and Geoffrey~E Hinton.
\newblock Layer normalization.
\newblock {\em arXiv preprint arXiv:1607.06450}, 2016.

\bibitem{hochreiter1997}
Sepp Hochreiter and J{\"u}rgen Schmidhuber.
\newblock Long short-term memory.
\newblock {\em Neural computation}, 9(8):1735--1780, 1997.

\bibitem{neural_gpu}
\L{}ukasz Kaiser and Ilya Sutskever.
\newblock Neural {GPU}s learn algorithms.
\end{thebibliography}
After the bibliography.
\end{document}
"""
NATBIB_BBL = r"""
\begin{thebibliography}{2}
\providecommand{\natexlab}[1]{#1}
\bibitem[{Lenisa et~al.(2019)}]{lenisa}
\bibinfo{author}{P.~Lenisa} et al., \emph{Low-energy spin physics}, EPJ Techniques,
\url{https://doi.org/10.1140/epjti/s40485-019-0051-y}.
\bibitem[{Groening(2021)}]{groening}
L.~Groening, Phys. Rev. Accel. \& Beams {\bf 24}, 054201 (2021).
\end{thebibliography}
"""


def tar_gz(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class ReadEprintTests(SimpleTestCase):
    """The bibliography of a preprint, read in its LaTeX sources (#227)."""

    def test_inline_bibliography(self):
        data = read_eprint(tar_gz({"ms.tex": INLINE_TEX, "fig.png": "x"}))
        self.assertEqual((data["source"], data["format"]), ("tar", "inline"))
        self.assertEqual(
            [e["key"] for e in data["entries"]], ["layernorm2016", "hochreiter1997", "neural_gpu"]
        )
        # The text after the environment is not part of the last entry.
        self.assertNotIn("After", data["entries"][-1]["text"])

    def test_bbl_comes_first_and_labels_are_skipped(self):
        data = read_eprint(tar_gz({"main.tex": INLINE_TEX, "main.bbl": NATBIB_BBL}))
        self.assertEqual(data["format"], "bbl")
        self.assertEqual([e["key"] for e in data["entries"]], ["lenisa", "groening"])

    def test_single_gzipped_file(self):
        data = read_eprint(gzip.compress(INLINE_TEX.encode()))
        self.assertEqual((data["source"], len(data["entries"])), ("gz", 3))

    def test_pdf_only(self):
        self.assertEqual(
            read_eprint(b"%PDF-1.5 ..."), {"source": "pdf", "format": "none", "entries": []}
        )

    def test_sources_without_bibliography(self):
        data = read_eprint(tar_gz({"ms.tex": r"\begin{document}No references.\end{document}"}))
        self.assertEqual((data["format"], data["entries"]), ("none", []))

    def test_clean_text(self):
        refs = references(read_eprint(tar_gz({"ms.tex": INLINE_TEX})))
        self.assertEqual(
            refs[0]["unstructured"],
            "Jimmy Lei Ba, Jamie Ryan Kiros, and Geoffrey E Hinton. Layer normalization. "
            "arXiv preprint arXiv:1607.06450, 2016.",
        )
        self.assertIn("Jürgen Schmidhuber", refs[1]["unstructured"])
        self.assertIn("9(8):1735–1780", refs[1]["unstructured"])
        self.assertTrue(refs[2]["unstructured"].startswith("Łukasz Kaiser"))
        self.assertIn("Neural GPUs learn", refs[2]["unstructured"])
        self.assertEqual(
            clean_latex(r"\bibinfo{author}{\bibfnamefont{E.}~\bibnamefont{Cisbani}}, \& al"),
            "E. Cisbani, & al.",
        )

    def test_only_written_identifiers(self):
        refs = references(read_eprint(tar_gz({"ms.tex": INLINE_TEX, "ms.bbl": NATBIB_BBL})))
        self.assertEqual(refs[0]["DOI"], "10.1140/epjti/s40485-019-0051-y")
        # A journal and a volume are no identifier: left to identify.
        self.assertNotIn("DOI", refs[1])

    def test_written_identifier(self):
        self.assertEqual(
            written_identifier("CoRR, abs/1409.0473, 2014"), "10.48550/arxiv.1409.0473"
        )
        self.assertEqual(
            written_identifier("arXiv:hep-th/9901001"), "10.48550/arxiv.hep-th/9901001"
        )
        self.assertEqual(
            written_identifier(r"doi:10.1103/PhysRevAccelBeams.24.054201."),
            ("10.1103/physrevaccelbeams.24.054201"),
        )
        self.assertEqual(written_identifier("Phys. Rev. 24, 054201 (2021)"), "")


@patch("references.services.http._get_session")
class GetBytesTests(SimpleTestCase):
    def response(self, chunks):
        return Mock(status_code=200, headers={}, iter_content=Mock(return_value=iter(chunks)))

    def test_file(self, get_session):
        get_session.return_value.get.return_value = self.response([b"ab", b"cd"])
        with self.assertLogs("references.services", level="INFO"):
            self.assertEqual(
                http.get_bytes("u", service="arXiv", subject="x", max_bytes=10), b"abcd"
            )
        self.assertTrue(get_session.return_value.get.call_args.kwargs["stream"])

    def test_too_large_is_given_up(self, get_session):
        get_session.return_value.get.return_value = self.response([b"abcd", b"efgh"])
        with self.assertLogs("references.services", level="WARNING"):
            self.assertIsNone(http.get_bytes("u", service="arXiv", subject="x", max_bytes=6))

    def test_cut_connection(self, get_session):
        response = self.response([])
        response.iter_content.side_effect = requests.ConnectionError("cut")
        get_session.return_value.get.return_value = response
        with self.assertLogs("references.services", level="WARNING"):
            self.assertIsNone(http.get_bytes("u", service="arXiv", subject="x", max_bytes=6))


def datacite_preprint():
    return {
        "data": {
            "attributes": {
                "titles": [{"title": "Attention Is All You Need"}],
                "publicationYear": 2017,
                "creators": [{"givenName": "Ashish", "familyName": "Vaswani"}],
                "relatedIdentifiers": [],
            }
        }
    }


@without_orcid
@without_openalex
class ImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")

    def setUp(self):
        self.eprint = Mock(return_value=read_eprint(tar_gz({"ms.tex": INLINE_TEX})))
        patches = [
            patch("references.services.importer.fetch_crossref_json", new=lambda doi: None),
            patch(
                "references.services.importer.fetch_datacite_json",
                new=lambda doi: datacite_preprint() if doi == ARXIV else None,
            ),
            patch("references.services.importer.fetch_arxiv_eprint", new=self.eprint),
            patch(
                "references.services.importer.fetch_crossref_works",
                new=lambda dois: dict.fromkeys(dois),
            ),
            patch(
                "references.services.importer.fetch_datacite_works",
                new=lambda dois: dict.fromkeys(dois),
            ),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_preprint_of_a_corpus_gets_its_bibliography(self):
        pub = add_to_corpus(self.user, Publication.objects.create(doi=ARXIV))
        self.eprint.assert_called_once_with("1706.03762")
        refs = list(CitedReference.objects.filter(source=pub).order_by("position"))
        self.assertEqual(len(refs), 3)
        self.assertEqual(refs[0].target.doi, "10.48550/arxiv.1607.06450")
        self.assertIsNone(refs[1].target)  # to identify
        self.assertIn("Jürgen", refs[1].unstructured)

    def test_fetched_once(self):
        pub = add_to_corpus(self.user, Publication.objects.create(doi=ARXIV))
        add_to_corpus(get_user_model().objects.create_user("bob"), pub)
        self.eprint.assert_called_once()

    def test_not_fetched_outside_any_corpus(self):
        import_publication(Publication.objects.create(doi=ARXIV))
        self.eprint.assert_not_called()


class DetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user("alice")

    def page(self, eprint=None):
        pub = Publication.objects.create(doi=ARXIV, title="Attention Is All You Need")
        store_record(pub, Source.DATACITE, datacite_preprint())
        if eprint is not None:
            store_record(pub, Source.ARXIV, eprint)
        self.client.force_login(self.user)
        return self.client.get(reverse("publication_detail", args=[pub.pk]))

    def test_not_fetched_yet_can_be_imported(self):
        response = self.page()
        self.assertContains(response, "se trouve dans ses sources LaTeX")
        self.assertContains(response, "Importer ses références")

    def test_pdf_only(self):
        response = self.page({"source": "pdf", "format": "none", "entries": []})
        self.assertContains(response, "Bibliographie indisponible")
        self.assertNotContains(response, "Importer ses références")

    def test_bibliography_source(self):
        pub = Publication.objects.create(doi=ARXIV)
        store_record(pub, Source.DATACITE, datacite_preprint())
        self.assertEqual(bibliography_source(pub), Source.DATACITE)
        store_record(pub, Source.ARXIV, read_eprint(tar_gz({"ms.tex": INLINE_TEX})))
        self.assertEqual(bibliography_source(pub), Source.ARXIV)

    def test_no_bibliography_in_the_sources(self):
        response = self.page({"source": "tar", "format": "none", "entries": []})
        self.assertContains(response, "Bibliographie introuvable")
