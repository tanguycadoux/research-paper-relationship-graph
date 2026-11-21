"""
Search of publications and authors (#153): one bar, free text and operators,

    auteur:Felice titre:"champ magnétique" année:2020..2024 doi:10.1109 note:aimant

Free text looks in the titles, the author names, the identifiers and the notes of the
user's own corpus (#283, #416), never in those of others; note: in those notes only.
A publication that a free word finds in the note alone says so (found_in_note).
Comparisons ignore
case and accents through normalized(), an SQL function registered on every SQLite
connection: SQLite's LIKE only folds ASCII, and has no unaccent.
"""

import re
import shlex
import unicodedata
from dataclasses import dataclass, field

from django.db.models import (
    BooleanField,
    Case,
    Exists,
    F,
    Func,
    OuterRef,
    Q,
    TextField,
    Value,
    When,
)
from django.db.models.functions import Concat

from ...models import Author, AuthorPublication, UserPublication

# Operator, as typed (accents optional), to the field it fills.
OPERATORS = {
    "auteur": "authors",
    "titre": "titles",
    "annee": "years",
    "doi": "identifiers",
    "isbn": "identifiers",
    "note": "notes",
}
YEARS = re.compile(r"^(\d{4})?(\.\.)?(\d{4})?$")


def normalize(text):
    """Lower case, without accents: « Élodie » and « elodie » compare equal."""
    if text is None:
        return None
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def register_functions(sender, connection, **kwargs):
    """On connection_created: normalized() in SQL, the same function as in Python."""
    if connection.vendor == "sqlite":
        connection.connection.create_function("normalized", 1, normalize, deterministic=True)


class Normalized(Func):
    function = "normalized"
    output_field = TextField()


@dataclass
class Query:
    terms: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    identifiers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    year_from: int | None = None
    year_to: int | None = None
    errors: list[str] = field(default_factory=list)

    def __bool__(self):
        return bool(
            self.terms
            or self.authors
            or self.titles
            or self.identifiers
            or self.notes
            or self.has_years
        )

    @property
    def has_years(self):
        return self.year_from is not None or self.year_to is not None

    @property
    def about_publications_only(self):
        """Titles, years, identifiers or notes asked: authors would answer another question."""
        return bool(self.titles or self.identifiers or self.notes or self.has_years)


def tokens(text):
    """Words, a quoted phrase kept whole (« titre:"champ magnétique" »)."""
    try:
        return shlex.split(text)
    except ValueError:  # An unclosed quote: read the quotes as plain characters.
        return text.split()


def parse(text):
    query = Query()
    for token in tokens(text or ""):
        name, colon, value = token.partition(":")
        target = OPERATORS.get(normalize(name)) if colon else None
        if target is None:
            # Not an operator: plain text, colon included (« Re:thinking »).
            query.terms.append(token)
        elif not value:
            continue
        elif target == "years":
            read_years(query, value)
        else:
            getattr(query, target).append(value)
    return query


def read_years(query, value):
    """2020, 2020..2024, 2020.. or ..2024."""
    match = YEARS.match(value)
    start, dots, end = match.groups() if match else (None, None, None)
    if not match or not (start or end) or (start and end and not dots):
        query.errors.append(f"année:{value} : écrire 2020, 2020..2024, 2020.. ou ..2024.")
        return
    query.year_from = int(start) if start else None
    query.year_to = int(end) if end else None
    if not dots:
        query.year_to = query.year_from
    if query.year_from and query.year_to and query.year_from > query.year_to:
        query.year_from, query.year_to = query.year_to, query.year_from


def contains(expression, text):
    """expression, normalized, contains text, normalized."""
    return Q(**{f"{expression}__contains": normalize(text)})


def full_name(prefix=""):
    return Normalized(Concat(f"{prefix}first_name", Value(" "), f"{prefix}last_name"))


def author_named(words):
    """Publications with one author whose name holds every word (« Ada Love »)."""
    slots = AuthorPublication.objects.filter(publication=OuterRef("pk")).alias(
        _name=full_name("author__")
    )
    for word in words:
        slots = slots.filter(contains("_name", word))
    return Exists(slots)


def noted(user, text):
    """Publications whose note, in the corpus of user, contains text."""
    entries = UserPublication.objects.filter(user=user, publication=OuterRef("pk")).alias(
        _note=Normalized(F("note"))
    )
    return Exists(entries.filter(contains("_note", text)))


def term_found(term):
    """Publications whose title, an author name or an identifier holds term."""
    return (
        contains("_title", term)
        | author_named([term])
        | contains("_doi", term)
        | Q(isbn__contains=term.replace("-", ""))
    )


def filter_terms(publications, terms, user):
    """
    The publications holding every free word, in their fields or the note of user, and
    found_in_note when one of the words is in that note only (#416).
    """
    if not terms:
        return publications
    if user is None or not user.is_authenticated:
        for term in terms:
            publications = publications.filter(term_found(term))
        return publications
    in_note_only = Q()
    for term in terms:
        publications = publications.filter(term_found(term) | noted(user, term))
        in_note_only |= ~term_found(term) & noted(user, term)
    return publications.annotate(
        found_in_note=Case(
            When(in_note_only, then=Value(True)), default=Value(False), output_field=BooleanField()
        )
    )


def filter_publications(publications, query, user=None):
    """
    The publications matching every part of the query; the notes asked are those of
    user, none for a visitor.
    """
    publications = publications.alias(
        _title=Normalized(F("readable_title")), _doi=Normalized(F("doi"))
    )
    publications = filter_terms(publications, query.terms, user)
    # A quoted title is a phrase: its words in that order.
    for title in query.titles:
        publications = publications.filter(contains("_title", title))
    for name in query.authors:
        publications = publications.filter(author_named(name.split()))
    for identifier in query.identifiers:
        publications = publications.filter(
            contains("_doi", identifier) | Q(isbn__contains=identifier.replace("-", ""))
        )
    for note in query.notes:
        if user is None or not user.is_authenticated:
            return publications.none()
        publications = publications.filter(noted(user, note))
    if query.year_from is not None:
        publications = publications.filter(publication_date__year__gte=query.year_from)
    if query.year_to is not None:
        publications = publications.filter(publication_date__year__lte=query.year_to)
    return publications


def search_authors(query):
    """Authors whose name holds every free word and every author: word, or their ORCID."""
    if query.about_publications_only:
        return Author.objects.none()
    authors = Author.objects.alias(_name=full_name())
    for word in [*query.terms, *(w for name in query.authors for w in name.split())]:
        authors = authors.filter(contains("_name", word) | Q(orcid=word))
    return authors
