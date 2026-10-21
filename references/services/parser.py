from datetime import date

from references.models import Author, AuthorPublication, CitedReference, Publication

from .doi import is_valid_doi, normalize_doi


def parse_publication(pub, parse_references=True):
    """
    Fill a Publication from its stored Crossref JSON.
    """
    json_data = pub.crossref_json
    if not json_data:
        return

    message = json_data.get("message", {})

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
    authors = [resolve_author(*name) for name in names]

    AuthorPublication.objects.filter(publication=pub).delete()
    for index, ((given, family, orcid), author) in enumerate(zip(names, authors, strict=True)):
        AuthorPublication.objects.create(
            publication=pub,
            author=author,
            order=index,
            published_given_name=given,
            published_family_name=family,
            published_orcid=orcid,
        )


def published_name(author_json):
    """
    Return (given name, family name, ORCID) of a Crossref author entry.
    Organizations only have a "name", used as family name.
    """
    given = author_json.get("given", "").strip()
    family = (author_json.get("family") or author_json.get("name", "")).strip()
    orcid = author_json.get("ORCID", "").strip().rsplit("/", 1)[-1]
    return given, family, orcid


def resolve_author(given, family, orcid):
    """
    Find the canonical author of a published name, or create it. A name already
    resolved once (possibly by a manual merge) is resolved the same way again.
    """
    if orcid:
        author = Author.objects.filter(orcid=orcid).first()
        if author:
            return author
    previous = (
        AuthorPublication.objects.filter(
            published_given_name=given, published_family_name=family, published_orcid=orcid
        )
        .select_related("author")
        .first()
    )
    if previous:
        return previous.author
    author = Author.objects.filter(first_name=given, last_name=family, orcid=orcid).first()
    return author or Author.objects.create(first_name=given, last_name=family, orcid=orcid)


def parse_references_list(pub, message):
    """
    Store the bibliography of the publication as CitedReference entries, resolved
    to a Publication when the cited DOI is known.
    """
    CitedReference.objects.filter(source=pub).delete()
    for position, ref in enumerate(message.get("reference", [])):
        doi = normalize_doi(ref.get("DOI", ""))
        CitedReference.objects.create(
            source=pub,
            target=resolve_cited_publication(doi, ref),
            position=position,
            key=ref.get("key", ""),
            doi=doi,
            unstructured=ref.get("unstructured", ""),
            raw=ref,
        )


def resolve_cited_publication(doi, ref):
    """
    Return the Publication of a cited DOI, creating it if needed.
    Without a valid DOI, the reference stays unresolved (no empty Publication).
    """
    if not is_valid_doi(doi):
        return None
    target, _ = Publication.objects.get_or_create(
        doi=doi,
        defaults={"title": ref.get("article-title", ""), "parse_references": False},
    )
    return target
