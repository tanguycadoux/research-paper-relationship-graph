from django.db import transaction

from ..models import Author, Publication
from .arxiv_api import fetch_arxiv_eprint
from .crossref_api import fetch_crossref_json, fetch_crossref_works
from .datacite_api import fetch_datacite_json, fetch_datacite_works
from .enrichment import complete_cited_with_openalex, complete_with_openalex
from .external_records import Source, has_metadata, has_record, store_record
from .orcid_names import complete_names
from .parser import parse_publication
from .preprints import arxiv_id, is_arxiv, published_version, replace_cited_preprints


def import_publication(pub, *, with_references=False, force_fetch=False):
    """
    Make sure the publication has its metadata, then parse it, and complete it
    with OpenAlex, and the names of its authors with ORCID. With references, the
    cited publications are imported too, without their own references (the names
    of their authors are left to the complete_orcid_names command). An arXiv
    preprint that declares its published version is replaced by it (#227).

    Return the publication imported: pub, or the published version already in the
    base that the preprint merged into. None if the metadata could not be retrieved.
    """
    if not ensure_metadata(pub, force_fetch=force_fetch):
        return None
    pub = published_version(pub)
    if with_references and is_arxiv(pub.doi):
        ensure_arxiv_bibliography(pub, force_fetch=force_fetch)
    complete_with_openalex(pub, force_fetch=force_fetch)
    with transaction.atomic():
        parse_publication(pub, parse_references=with_references)
    complete_names(Author.objects.filter(publications=pub).distinct())
    if with_references:
        import_cited_publications(pub)
        complete_cited_with_openalex(pub)
    return pub


def ensure_metadata(pub, force_fetch=False):
    """
    Fetch the metadata of a publication unless some is already stored: stored
    data is never fetched again without an explicit refresh.
    """
    if has_metadata(pub) and not force_fetch:
        return True
    for source, fetch in doi_sources():
        json_data = fetch(pub.doi)
        if json_data:
            store_record(pub, source, json_data)
            return True
    return False


def ensure_arxiv_bibliography(pub, force_fetch=False):
    """
    The LaTeX sources of a preprint without published version, read once for its
    bibliography (#227); only when its references are wanted.
    """
    if has_record(pub, Source.ARXIV) and not force_fetch:
        return
    data = fetch_arxiv_eprint(arxiv_id(pub.doi))
    if data is not None:
        store_record(pub, Source.ARXIV, data)


def doi_sources():
    """
    A DOI is registered by one agency: Crossref for most articles, DataCite for
    conference proceedings (JACoW…), Zenodo deposits and datasets.
    """
    return [(Source.CROSSREF, fetch_crossref_json), (Source.DATACITE, fetch_datacite_json)]


def import_cited_publications(pub):
    """
    Import the cited publications never fetched: one Crossref request per batch
    of DOIs, then one DataCite request per batch for the DOIs Crossref does not
    know. A DOI unknown to both is stored as such, so that later imports do not
    request it again (an explicit action can still retry it). Cited arXiv preprints
    that declare their published version are replaced by it.
    """
    targets = {target.doi: target for target in unfetched_cited_publications(pub)}
    if not targets:
        return
    answers = fetch_cited_works(list(targets))
    with transaction.atomic():
        for doi, records in answers.items():
            store_cited_work(targets[doi], records)
    preprints = [targets[doi] for doi, records in answers.items() if Source.DATACITE in records]
    for published in replace_cited_preprints(preprints):
        with transaction.atomic():
            parse_publication(published, parse_references=False)


def fetch_cited_works(dois):
    """
    Return {doi: {source: json or None}} for the DOIs whose answer is complete:
    found in Crossref, or answered by DataCite after Crossref did not know them.
    """
    crossref = fetch_crossref_works(dois)
    unknown = [doi for doi, data in crossref.items() if data is None]
    datacite = fetch_datacite_works(unknown) if unknown else {}
    answers = {doi: {Source.CROSSREF: data} for doi, data in crossref.items() if data}
    for doi, data in datacite.items():
        answers[doi] = {Source.CROSSREF: None, Source.DATACITE: data}
    return answers


def store_cited_work(pub, records):
    for source, data in records.items():
        store_record(pub, source, data)
    if any(data is not None for data in records.values()):
        parse_publication(pub, parse_references=False)


def unfetched_cited_publications(pub):
    """Publications cited by pub, with a DOI, that Crossref was never asked about."""
    return (
        Publication.objects.filter(citations__source=pub)
        .exclude(doi="")
        .exclude(external_records__source=Source.CROSSREF)
        .distinct()
    )
