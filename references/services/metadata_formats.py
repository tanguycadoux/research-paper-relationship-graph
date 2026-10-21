"""
Conversion of the answers of each source to a single message format, the one of
Crossref, which the parser reads.
"""

from .external_records import Source, records_by_source

# When several sources know a publication, the first one is used.
PRIORITY = [Source.CROSSREF, Source.OPENLIBRARY]


def metadata_message(pub):
    """Message of the preferred source that knows the publication, or None."""
    records = records_by_source(pub)
    for source in PRIORITY:
        if source in records:
            return CONVERTERS[source](records[source])
    return None


def crossref_message(data):
    return data.get("message", {})


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
    Source.OPENLIBRARY: openlibrary_message,
}
