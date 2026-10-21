from . import http

OPENLIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
FIELDS = "key,title,subtitle,author_name,first_publish_year,publish_year,publisher,isbn"


def fetch_openlibrary_book(isbn):
    """
    Return the Open Library search result for an ISBN (title, authors, years…),
    or None if the book is unknown or cannot be retrieved. One request.
    """
    data = http.get_json(
        OPENLIBRARY_SEARCH_URL,
        params={"isbn": isbn, "fields": FIELDS, "limit": 1},
        service="Open Library",
        subject=f"ISBN {isbn}",
    )
    docs = data.get("docs", []) if data else []
    return docs[0] if docs else None
