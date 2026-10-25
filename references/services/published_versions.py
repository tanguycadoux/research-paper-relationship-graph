"""
Published version of an arXiv preprint found by OpenAlex (#227, step 3), when its
authors declare none. OpenAlex groups the versions of an article under one work, but
its grouping is automatic and sometimes wrong (copies of « Attention Is All You Need »
registered by a third party under 10.65215/…). So the version is only proposed, as a
conflict to decide on the « Conflits » page, after checks of our own on its Crossref
record: a publication type (never posted-content), a close title, the same first
author, and a year not before the preprint's.
"""

from ..models import MetadataConflict, Publication
from .conflicts import Kind, report_conflict, resolve
from .crossref_api import fetch_crossref_json, fetch_crossref_works
from .doi import normalize_doi
from .external_records import Source, store_record
from .names import name_parts
from .openalex_api import fetch_openalex_works, work_dois
from .preprints import (
    ARXIV_PREFIX,
    is_arxiv,
    is_published_version,
    replace_preprint,
    title_words,
)


def suggest_published_versions(publications):
    """
    Propose a published version for the arXiv preprints among publications that have
    an OpenAlex work and no proposal yet: one Crossref request per batch for all the
    DOIs to check. Return the number of conflicts reported.
    """
    candidates = {pub: candidate_dois(pub) for pub in preprints_to_check(publications)}
    candidates = {pub: dois for pub, dois in candidates.items() if dois}
    if not candidates:
        return 0
    works = fetch_crossref_works(sorted({doi for dois in candidates.values() for doi in dois}))
    reported = 0
    for pub, dois in candidates.items():
        version = next((works[doi] for doi in dois if verified(pub, works.get(doi))), None)
        if version is not None:
            report_version(pub, version)
            reported += 1
    return reported


def suggest_for_preprints_in_base():
    """
    suggest_published_versions for every arXiv preprint of the base. Their OpenAlex
    work is fetched again when missing: the batches stored as unknown the preprints
    that OpenAlex knows by their journal DOI. Return the number of conflicts reported.
    """
    preprints = list(Publication.objects.filter(doi__startswith=ARXIV_PREFIX))
    without_work = {
        pub.doi: pub
        for pub in preprints
        if not pub.external_records.filter(source=Source.OPENALEX, data__isnull=False).exists()
    }
    if without_work:
        for doi, work in fetch_openalex_works(list(without_work)).items():
            if work:
                store_record(without_work[doi], Source.OPENALEX, work)
    return suggest_published_versions(preprints)


def preprints_to_check(publications):
    already = MetadataConflict.objects.filter(kind=Kind.PUBLISHED_VERSION)
    return [
        pub
        for pub in publications
        if is_arxiv(pub.doi) and not already.filter(publication=pub).exists()
    ]


def candidate_dois(pub):
    """The DOIs of the OpenAlex work of pub that are not arXiv's, in OpenAlex's order."""
    record = pub.external_records.filter(source=Source.OPENALEX, data__isnull=False).first()
    if record is None:
        return []
    return [doi for doi in work_dois(record.data) if not is_arxiv(doi)]


def verified(pub, crossref_data):
    if not is_published_version(pub.title, crossref_data):
        return False
    message = crossref_data["message"]
    return same_first_author(pub, message) and not_before(pub, message)


def same_first_author(pub, message):
    slot = pub.authorpublication_set.select_related("author").order_by("order").first()
    family = (message.get("author") or [{}])[0].get("family", "")
    if slot is None or not family:
        return False
    return name_parts(slot.author.last_name) == name_parts(family)


def not_before(pub, message):
    year = crossref_year(message)
    if pub.publication_date is None or year is None:
        return False
    return year >= pub.publication_date.year


def crossref_year(message):
    for key in ("published", "issued", "published-print", "published-online"):
        parts = (message.get(key) or {}).get("date-parts") or [[None]]
        if parts[0] and parts[0][0]:
            return parts[0][0]
    return None


def report_version(pub, crossref_data):
    message = crossref_data["message"]
    title = (message.get("title") or [""])[0]
    report_conflict(
        Kind.PUBLISHED_VERSION,
        publication=pub,
        field="doi",
        current=pub.doi,
        proposed=normalize_doi(message["DOI"]),
        source=Source.OPENALEX,
        details={
            "title": title,
            "venue": (message.get("container-title") or [""])[0],
            "year": crossref_year(message),
            "same_title": title_words(title) == title_words(pub.title),
        },
    )


def accept_published_version(conflict, user):
    """
    « Prendre la valeur proposée »: the preprint is replaced by its published version,
    or merges into it if it is in the base; the caller imports it again. Return the
    publication, or None when Crossref did not answer: nothing is decided then.
    """
    crossref_data = fetch_crossref_json(conflict.proposed_value)
    if not crossref_data:
        return None
    pub = replace_preprint(conflict.publication, crossref_data)
    conflict.refresh_from_db()  # moved to the published version if the preprint merged
    resolve(conflict, MetadataConflict.Status.ACCEPTED, user)
    return pub


def open_proposal(pub):
    """The published version proposed for pub and not decided yet, or None."""
    return MetadataConflict.objects.filter(
        kind=Kind.PUBLISHED_VERSION, publication=pub, status=MetadataConflict.Status.OPEN
    ).first()


def proposal_message(pub):
    """What the page of a preprint says of its proposed published version ("" without)."""
    proposal = open_proposal(pub)
    if proposal is None:
        return ""
    details = proposal.details
    where = ", ".join(str(part) for part in (details.get("venue"), details.get("year")) if part)
    return (
        f"OpenAlex propose une version publiée de cette prépublication : "
        f"« {details.get('title') or proposal.proposed_value} »"
        f"{f' ({where})' if where else ''}, DOI {proposal.proposed_value}. "
        "Elle n'est pas appliquée tant que personne ne l'a confirmée."
    )
