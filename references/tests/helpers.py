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
    return patch(
        "references.services.enrichment.fetch_openalex_works",
        new=lambda dois: {doi: None for doi in dois},
    )(target)


def without_datacite(target):
    """Mock DataCite as knowing no DOI (without adding arguments to the tests)."""
    target = patch("references.services.importer.fetch_datacite_json", new=lambda doi: None)(target)
    return patch(
        "references.services.importer.fetch_datacite_works",
        new=lambda dois: {doi: None for doi in dois},
    )(target)


def without_other_sources(target):
    """Mock every source other than Crossref (DataCite, OpenAlex) as knowing nothing."""
    return without_openalex(without_datacite(target))
