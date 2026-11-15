"""
Import of several publications at once, for the worker of the queue (#381): the steps of
import_publication, each one asking each source for all the publications of the batch,
in full batches, rather than one publication after the other with batches filled at
10-25 % (measured on 50 imports: 229 requests, about 35 when grouped). OpenAlex counts a
batch in a daily budget, a single lookup not: a single DOI is still asked alone.

An error on one publication fails its item only; the others go on.
"""

import logging
from dataclasses import dataclass

from django.db import transaction

from ...models import Author, Publication
from ..sources.external_records import Source, has_metadata, has_record, store_record
from . import enrichment, importer
from .enrichment import complete_ancestors, complete_cited_of_with_openalex
from .importer import ensure_arxiv_bibliography, import_cited_of
from .orcid_names import complete_names
from .parser import parse_publication
from .preprints import is_arxiv, published_version
from .published_versions import suggest_published_versions
from .written_identifiers import link_references, references_to_link

logger = logging.getLogger(__name__)

UNKNOWN = "DOI inconnu de Crossref et de DataCite, ou service injoignable."


@dataclass
class Item:
    """A publication of the batch: imported (result) or failed (error)."""

    pub: Publication
    with_references: bool
    result: Publication | None = None
    error: str = ""


def import_publications(items):
    """import_publication for each Item, step by step for all of them; return items."""
    fetch_metadata([item for item in items if not has_metadata(item.pub)])
    each(alive(items), become_published_version)
    fetch_openalex([item.pub for item in alive(items)])
    each(alive(items), parse)
    imported = [item.pub for item in alive(items)]
    complete_names(Author.objects.filter(publications__in=imported).distinct())
    sources = [item.pub for item in alive(items) if item.with_references]
    if sources:
        import_cited_of(sources)
        link_references(references_to_link(sources))
        complete_cited_of_with_openalex(sources)
    cited = Publication.objects.filter(citations__source__in=sources).distinct()
    suggest_published_versions([*imported, *cited])
    for item in alive(items):
        item.result = item.pub
    return items


def alive(items):
    return [item for item in items if not item.error]


def each(items, step):
    """A step for each item; an error fails the item, not the batch."""
    for item in items:
        try:
            step(item)
        except Exception as error:  # kept with the request; the other items go on
            logger.exception("Import par lot : échec pour %s", item.pub.doi)
            item.error = f"{type(error).__name__} : {error}"


def answers(dois, single, batch):
    """{doi: json or None}: a single DOI alone, several in batches."""
    if len(dois) == 1:
        return {dois[0]: single(dois[0])}
    return batch(dois) if dois else {}


def fetch_metadata(items):
    """Crossref for all, then DataCite for those Crossref does not know (ensure_metadata)."""
    by_doi = {item.pub.doi: item for item in items}
    missing = list(by_doi)
    # Through importer and enrichment, where the import asks the sources (and the tests
    # mock them).
    for source, single, batch in (
        (Source.CROSSREF, importer.fetch_crossref_json, importer.fetch_crossref_works),
        (Source.DATACITE, importer.fetch_datacite_json, importer.fetch_datacite_works),
    ):
        found = {doi: data for doi, data in answers(missing, single, batch).items() if data}
        with transaction.atomic():
            for doi, data in found.items():
                store_record(by_doi[doi].pub, source, data)
        missing = [doi for doi in missing if doi not in found]
    for doi in missing:
        by_doi[doi].error = UNKNOWN


def become_published_version(item):
    """An arXiv preprint that declares its published version is replaced by it (#227)."""
    item.pub = published_version(item.pub)
    if item.with_references and is_arxiv(item.pub.doi):
        ensure_arxiv_bibliography(item.pub)


def fetch_openalex(pubs):
    """The OpenAlex works of the publications that have none (complete_with_openalex)."""
    targets = {pub.doi: pub for pub in pubs if pub.doi and not has_record(pub, Source.OPENALEX)}
    works = answers(list(targets), enrichment.fetch_openalex_work, enrichment.fetch_openalex_works)
    found = {doi: work for doi, work in works.items() if work}
    for doi, work in found.items():
        store_record(targets[doi], Source.OPENALEX, work)
    complete_ancestors(list(found.values()))


def parse(item):
    with transaction.atomic():
        parse_publication(item.pub, parse_references=item.with_references)
