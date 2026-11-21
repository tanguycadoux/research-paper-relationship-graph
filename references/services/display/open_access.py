"""
« Lire l'article » (#284): the best open access version of a publication, as the
stored OpenAlex answer gives it (best_oa_location), without any new request. An arXiv
preprint, or a published version that replaced one, always has the PDF of arXiv.
The licence of the OpenAlex version follows the link (#442); the licence of an arXiv PDF
is not stored, so it shows none.
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
CREATIVE_COMMONS_URL = "https://creativecommons.org/licenses/{}/4.0/"
CC0_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
CREATIVE_COMMONS = {"by", "by-sa", "by-nd", "by-nc", "by-nc-sa", "by-nc-nd"}
# OpenAlex licences other than cc-by…, in a short form (#442). Unknown ones show nothing.
OTHER_LICENCES = {
    "cc0": ("CC0", CC0_URL),
    "public-domain": ("domaine public", None),
    "pd": ("domaine public", None),
    "publisher-specific-oa": ("licence de l'éditeur", None),
    "other-oa": ("autre licence libre", None),
}


def open_access_link(pub):
    """
    {"url", "label", "licence"} of the version to read, or None when none is open;
    licence is {"label", "url"} or None.
    """
    url, version, licence = openalex_location(pub) or arxiv_location(pub) or (None,) * 3
    if not url:
        return None
    return {"url": url, "label": link_label(version), "licence": licence_of(licence)}


def openalex_location(pub):
    """(url, version, licence) of the best open access location of OpenAlex, or None."""
    record = pub.external_records.filter(source=Source.OPENALEX, data__isnull=False).first()
    location = (record.data if record else {}).get("best_oa_location") or {}
    # The PDF to read the article, else the page that gives it.
    url = location.get("pdf_url") or location.get("landing_page_url")
    if not url or location.get("is_oa") is False:
        return None
    return url, location.get("version"), location.get("license")


def arxiv_location(pub):
    """(PDF url, submitted version, no licence) of the arXiv preprint of pub, or None."""
    doi = next((doi for doi in (pub.doi, pub.preprint_doi) if doi and is_arxiv(doi)), None)
    return (ARXIV_PDF_URL.format(arxiv_id(doi)), SUBMITTED_VERSION, None) if doi else None


def link_label(version):
    """« Lire l'article (accès libre, version publiée) », the version only when known."""
    kind = ", ".join(filter(None, ["accès libre", VERSION_LABELS.get(version)]))
    return f"Lire l'article ({kind})"


def licence_of(code):
    """
    {"label", "url"} of an OpenAlex licence code: « CC BY-NC-ND » and its text for a
    Creative Commons licence, a short label without url for the others, or None.
    """
    code = (code or "").strip().lower()
    kind = code.removeprefix("cc-")
    if code.startswith("cc-") and kind in CREATIVE_COMMONS:
        return {"label": f"CC {kind.upper()}", "url": CREATIVE_COMMONS_URL.format(kind)}
    label, url = OTHER_LICENCES.get(code, (None, None))
    return {"label": label, "url": url} if label else None
