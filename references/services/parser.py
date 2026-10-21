from datetime import date

from references.models import AuthorPublication, CitedReference, Publication

from .author_resolution import resolve_authors
from .doi import is_valid_doi, normalize_doi
from .metadata_formats import metadata_message
from .orcid import normalize_orcid


def parse_publication(pub, parse_references=True):
    """
    Fill a Publication from the stored answer of its preferred source.
    """
    message = metadata_message(pub)
    if message is None:
        return

    parse_title(pub, message)
    parse_publication_date(pub, message)
    parse_authors(pub, message)

    if parse_references:
        parse_references_list(pub, message)

    pub.save()


def parse_title(pub, message):
    """
    Extract the title.
    """
    titles = message.get("title", [])
    if titles and isinstance(titles, list):
        pub.title = titles[0].strip()


def parse_publication_date(pub, message):
    """
    Extract the publication date (missing month or day default to 1).
    """
    issued = message.get("issued", {})
    date_parts = issued.get("date-parts", [])

    if not date_parts:
        return

    parts = date_parts[0]

    year = parts[0] if len(parts) > 0 else None
    month = parts[1] if len(parts) > 1 else 1
    day = parts[2] if len(parts) > 2 else 1

    if year:
        try:
            pub.publication_date = date(year, month, day)
        except ValueError:
            pass


def parse_authors(pub, message):
    """
    Extract the authors and link them to the publication, in order.
    The published names are kept; the canonical author is resolved from them.
    """
    authors_data = message.get("author", [])
    if not authors_data:
        return

    # Resolve before deleting the current slots: they record previous resolutions.
    names = [published_name(author_json) for author_json in authors_data]
    authors = resolve_authors(names)

    AuthorPublication.objects.filter(publication=pub).delete()
    AuthorPublication.objects.bulk_create(
        AuthorPublication(
            publication=pub,
            author=author,
            order=index,
            published_given_name=given,
            published_family_name=family,
            published_orcid=orcid,
        )
        for index, ((given, family, orcid), author) in enumerate(zip(names, authors, strict=True))
    )


def published_name(author_json):
    """
    Return (given name, family name, ORCID) of a Crossref author entry.
    Organizations only have a "name", used as family name.
    """
    given = author_json.get("given", "").strip()
    family = (author_json.get("family") or author_json.get("name", "")).strip()
    orcid = normalize_orcid(author_json.get("ORCID", ""))
    return given, family, orcid


def parse_references_list(pub, message):
    """
    Store the bibliography of the publication as CitedReference entries, resolved
    to a Publication when the cited DOI is known. Manual identifications made on a
    previous import are kept, and take precedence over Crossref.
    """
    refs = message.get("reference", [])
    dois = [normalize_doi(ref.get("DOI", "")) for ref in refs]
    targets = cited_publications(dois, refs)
    manual = manual_resolutions(pub)

    CitedReference.objects.filter(source=pub).delete()
    CitedReference.objects.bulk_create(
        with_manual_resolution(
            CitedReference(
                source=pub,
                target=targets.get(doi),
                position=position,
                key=ref.get("key", ""),
                doi=doi,
                unstructured=ref.get("unstructured", ""),
                raw=ref,
            ),
            manual,
        )
        for position, (ref, doi) in enumerate(zip(refs, dois, strict=True))
    )


def reference_identity(ref):
    """Crossref key of a reference, or its position when it has no key."""
    return ("key", ref.key) if ref.key else ("position", ref.position)


def manual_resolutions(pub):
    references = CitedReference.objects.filter(source=pub, resolved_manually=True)
    return {reference_identity(ref): ref for ref in references}


def with_manual_resolution(ref, manual):
    previous = manual.get(reference_identity(ref))
    if previous:
        ref.target_id = previous.target_id
        ref.resolved_manually = True
        ref.resolved_by_id = previous.resolved_by_id
        ref.resolved_at = previous.resolved_at
    return ref


def cited_publications(dois, refs):
    """
    Return {doi: Publication} for the valid cited DOIs, creating the missing ones.
    Without a valid DOI, a reference stays unresolved (no empty Publication).
    """
    titles = {doi: ref.get("article-title", "") for doi, ref in zip(dois, refs, strict=True)}
    valid = {doi for doi in dois if is_valid_doi(doi)}
    existing = {pub.doi: pub for pub in Publication.objects.filter(doi__in=valid)}
    missing = [Publication(doi=doi, title=titles[doi]) for doi in valid - existing.keys()]
    Publication.objects.bulk_create(missing)
    return existing | {pub.doi: pub for pub in missing}
