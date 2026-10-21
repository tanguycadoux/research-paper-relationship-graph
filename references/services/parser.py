from datetime import date

from references.models import Author, AuthorPublication, Publication, PublicationReference

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
    """
    authors_data = message.get("author", [])
    if not authors_data:
        return

    AuthorPublication.objects.filter(publication=pub).delete()

    for index, author_json in enumerate(authors_data):
        first_name = author_json.get("given", "")
        last_name = author_json.get("family", "")
        orcid = author_json.get("ORCID", "").replace("https://orcid.org/", "").strip()

        author, _ = Author.objects.get_or_create(
            orcid=orcid,
            first_name=first_name,
            last_name=last_name,
        )

        AuthorPublication.objects.create(publication=pub, author=author, order=index)


def parse_references_list(pub, message):
    """
    Extract the cited references and create the PublicationReference links.
    """
    refs_data = message.get("reference", [])
    if not refs_data:
        return

    PublicationReference.objects.filter(source=pub).delete()

    for ref in refs_data:
        doi = ref.get("DOI", "")
        title = ref.get("article-title", "")
        ref_key_str = ref.get("key", "")

        try:
            ref_key = int(ref_key_str.lstrip("ref"))
        except ValueError:
            ref_key = 0

        normalized_doi = normalize_doi(doi)
        if is_valid_doi(normalized_doi):
            target_pub, _ = Publication.objects.get_or_create(
                doi=normalized_doi,
                defaults={
                    "title": title,
                    "parse_references": False,
                },
            )
        else:
            target_pub = Publication.objects.create(
                doi="",
                title=title,
                parse_references=False,
            )

        PublicationReference.objects.update_or_create(
            source=pub, target=target_pub, defaults={"ref_key": ref_key}
        )
