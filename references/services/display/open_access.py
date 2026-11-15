"""
« Lire l'article » (#284): the best open access version of a publication, as the
stored OpenAlex answer gives it (best_oa_location), without any new request. An arXiv
preprint, or a published version that replaced one, always has the PDF of arXiv.
"""

from ..imports.preprints import arxiv_id, is_arxiv
from ..sources.external_records import Source

ARXIV_PDF_URL = "https://arxiv.org/pdf/{}"
SUBMITTED_VERSION = "submittedVersion"
VERSION_LABELS = {
    "publishedVersion": "version publiée",
    "acceptedVersion": "version acceptée",
    SUBMITTED_VERSION: "version soumise",
}


def open_access_link(pub):
    """{"url", "label"} of the version to read, or None when none is open."""
    url, version = openalex_location(pub) or arxiv_location(pub) or (None, None)
    if not url:
        return None
    return {"url": url, "label": link_label(version)}


def openalex_location(pub):
    """(url, version) of the best open access location given by OpenAlex, or None."""
    record = pub.external_records.filter(source=Source.OPENALEX, data__isnull=False).first()
    location = (record.data if record else {}).get("best_oa_location") or {}
    # The PDF to read the article, else the page that gives it.
    url = location.get("pdf_url") or location.get("landing_page_url")
    if not url or location.get("is_oa") is False:
        return None
    return url, location.get("version")


def arxiv_location(pub):
    """(PDF url, submitted version) of the arXiv preprint of pub, or None."""
    doi = next((doi for doi in (pub.doi, pub.preprint_doi) if doi and is_arxiv(doi)), None)
    return (ARXIV_PDF_URL.format(arxiv_id(doi)), SUBMITTED_VERSION) if doi else None


def link_label(version):
    """« Lire l'article (accès libre, version publiée) », the version only when known."""
    kind = ", ".join(filter(None, ["accès libre", VERSION_LABELS.get(version)]))
    return f"Lire l'article ({kind})"
