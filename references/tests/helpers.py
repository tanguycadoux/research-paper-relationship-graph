from unittest.mock import patch

from references.services.external_records import Source, store_record


def with_crossref(pub, data):
    """Store a Crossref answer for pub, as the importer would."""
    store_record(pub, Source.CROSSREF, data)
    return pub


def with_openlibrary(pub, data):
    store_record(pub, Source.OPENLIBRARY, data)
    return pub


def crossref_record(pub):
    return pub.external_records.filter(source=Source.CROSSREF).first()


def without_openalex(target):
    """Mock OpenAlex as knowing no DOI (without adding arguments to the tests)."""
    target = patch("references.services.enrichment.fetch_openalex_work", new=lambda doi: None)(
        target
    )
    for module in ("enrichment", "published_versions"):
        target = patch(
            f"references.services.{module}.fetch_openalex_works",
            new=lambda dois: {doi: None for doi in dois},
        )(target)
    return target


def without_datacite(target):
    """Mock DataCite as knowing no DOI (without adding arguments to the tests)."""
    target = patch("references.services.importer.fetch_datacite_json", new=lambda doi: None)(target)
    return patch(
        "references.services.importer.fetch_datacite_works",
        new=lambda dois: {doi: None for doi in dois},
    )(target)


def without_orcid(target):
    """Mock the grouped ORCID search as knowing no ORCID."""
    return patch(
        "references.services.orcid_names.fetch_orcid_names",
        new=lambda orcids: dict.fromkeys(orcids),
    )(target)


def doi_org_answers(registered):
    """Mock doi.org as giving the same answer for every DOI: True, False, or None (#240)."""
    return patch(
        "references.services.doi_registration.registered_dois",
        new=lambda dois: dict.fromkeys(dois, registered),
    )


def without_doi_org(target):
    """Mock doi.org as unreachable: every DOI is accepted, without request."""
    return doi_org_answers(None)(target)


def without_other_sources(target):
    """
    Mock every source other than Crossref (DataCite, OpenAlex, ORCID, doi.org) as
    knowing nothing.
    """
    return without_doi_org(without_orcid(without_openalex(without_datacite(target))))


def without_candidate_search(target):
    """Mock the searches of the identification page as finding nothing (#160)."""
    for name in ("search_crossref", "search_datacite_title"):
        target = patch(f"references.services.candidates.{name}", new=lambda text: [])(target)
    return patch(
        "references.services.candidates.fetch_datacite_works",
        new=lambda dois: dict.fromkeys(dois),
    )(target)
