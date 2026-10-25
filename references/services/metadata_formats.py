"""
Conversion of the answers of each source to a single message format, the one of
Crossref, which the parser reads.
"""

from .external_records import Source, records_by_source
from .latex_bibliography import references as latex_references

# When several sources know a publication, the first one is used.
PRIORITY = [Source.CROSSREF, Source.DATACITE, Source.OPENLIBRARY]


def metadata_message(pub):
    """
    Message of the preferred source that knows the publication, or None. Without a
    bibliography there, an arXiv preprint takes the one of its LaTeX sources (#227).
    """
    records = records_by_source(pub)
    source = preferred_source(records)
    if source is None:
        return None
    message = CONVERTERS[source](records[source])
    if takes_latex_references(message, records):
        message["reference"] = latex_references(records[Source.ARXIV])
    return message


def bibliography_source(pub):
    """Source the bibliography of the publication comes from, or None."""
    records = records_by_source(pub)
    source = preferred_source(records)
    if source is None:
        return None
    if takes_latex_references(CONVERTERS[source](records[source]), records):
        return Source.ARXIV
    return source


def preferred_source(records):
    return next((source for source in PRIORITY if source in records), None)


def takes_latex_references(message, records):
    return not message.get("reference") and Source.ARXIV in records


def crossref_message(data):
    return data.get("message", {})


def datacite_message(data):
    """Express a DataCite record like a Crossref message."""
    attributes = data.get("data", {}).get("attributes", {})
    titles = [t["title"] for t in attributes.get("titles", []) if t.get("title")]
    return {
        "title": titles[:1],
        "issued": {"date-parts": [datacite_date_parts(attributes)]},
        "author": [datacite_author(creator) for creator in attributes.get("creators", [])],
        "reference": datacite_references(attributes),
    }


def datacite_date_parts(attributes):
    """Full issue date when DataCite gives one, otherwise the publication year."""
    for date in attributes.get("dates", []):
        parts = str(date.get("date", "")).split("-")
        if date.get("dateType") == "Issued" and all(p.isdigit() for p in parts):
            return [int(p) for p in parts[:3]]
    year = str(attributes.get("publicationYear", ""))
    return [int(year)] if year.isdigit() else []


def datacite_author(creator):
    orcids = [
        identifier.get("nameIdentifier", "")
        for identifier in creator.get("nameIdentifiers", [])
        if identifier.get("nameIdentifierScheme") == "ORCID"
    ]
    author = datacite_name(creator)
    if orcids:
        author["ORCID"] = orcids[0]
    return author


def datacite_name(creator):
    """
    Given and family names of a creator. Some records only give the full name,
    which DataCite writes "Family, Given" for a person: "Chautard,Frederic" (#159).
    An organization keeps its name whole, as family name.
    """
    given = creator.get("givenName", "")
    family = creator.get("familyName", "")
    name = creator.get("name", "")
    if given or family:
        return {"given": given, "family": family or name}
    if creator.get("nameType") != "Organizational" and name.count(",") == 1:
        family, _, given = name.partition(",")
        return {"given": given.strip(), "family": family.strip()}
    return {"given": "", "family": name}


def datacite_references(attributes):
    """DOIs that the record declares as references (relationType References or Cites)."""
    return [
        {"key": f"datacite-{index}", "DOI": related["relatedIdentifier"]}
        for index, related in enumerate(attributes.get("relatedIdentifiers", []))
        if related.get("relationType") in ("References", "Cites")
        and related.get("relatedIdentifierType") == "DOI"
    ]


def openlibrary_message(doc):
    """Express an Open Library search result like a Crossref message."""
    title = ": ".join(part for part in (doc.get("title"), doc.get("subtitle")) if part)
    year = doc.get("first_publish_year")
    return {
        "title": [title] if title else [],
        "issued": {"date-parts": [[year]]} if year else {},
        "author": [split_full_name(name) for name in doc.get("author_name", [])],
    }


def split_full_name(name):
    """'Ian Goodfellow' -> given 'Ian', family 'Goodfellow' (no ORCID in Open Library)."""
    given, _, family = name.strip().rpartition(" ")
    return {"given": given, "family": family}


CONVERTERS = {
    Source.CROSSREF: crossref_message,
    Source.DATACITE: datacite_message,
    Source.OPENLIBRARY: openlibrary_message,
}
