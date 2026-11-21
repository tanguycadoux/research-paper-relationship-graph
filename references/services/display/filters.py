"""
Filters in the column headers of a table (#115), as in a spreadsheet: a text that the
column contains, a range of years, a choice. Each filter reads its own URL parameters
(?title=magnet&year_from=2018), so that the sort, the pages and the other filters keep
it. Server side, before the pagination, like the sort.
"""

import re
from dataclasses import dataclass, field

from django.db.models import Exists, F, OuterRef, Q
from django.utils.http import urlencode

from ...models import CitedReference, Publication, UserPublication
from ..corpus import tags
from ..corpus.entries import with_reading_status
from . import keyword_graph
from .search import Normalized, author_named, contains, noted

YEAR = re.compile(r"^\d{4}$")


class TextFilter:
    """The column contains a text, case and accents ignored."""

    kind = "text"

    def __init__(self, param, apply):
        self.param = param
        self.params = (param,)
        self.filter_queryset = apply

    def read(self, data, errors):
        return data.get(self.param, "").strip() or None

    def apply(self, queryset, value):
        return self.filter_queryset(queryset, value)

    def describe(self, value):
        return f"contient « {value} »"


class YearsFilter:
    """Publication years from, to, or between."""

    kind = "years"
    params = ("year_from", "year_to")

    def read(self, data, errors):
        years = []
        for param in self.params:
            value = data.get(param, "").strip()
            if value and not YEAR.match(value):
                errors.append(f"Année : « {value} » n'est pas une année (quatre chiffres).")
                value = ""
            years.append(int(value) if value else None)
        start, end = years
        if start and end and start > end:
            start, end = end, start
        return (start, end) if start or end else None

    def apply(self, queryset, value):
        start, end = value
        if start:
            queryset = queryset.filter(publication_date__year__gte=start)
        if end:
            queryset = queryset.filter(publication_date__year__lte=end)
        return queryset

    def describe(self, value):
        start, end = value
        if start and end:
            return str(start) if start == end else f"de {start} à {end}"
        return f"depuis {start}" if start else f"jusqu'à {end}"


class ChoiceFilter:
    """One of a few choices: with a DOI, without an ORCID…"""

    kind = "choice"

    def __init__(self, param, choices):
        self.param = param
        self.params = (param,)
        # value: (label, condition)
        self.choices = choices

    def read(self, data, errors):
        value = data.get(self.param, "")
        return value if value in self.choices else None

    def apply(self, queryset, value):
        return queryset.filter(self.choices[value][1])

    def describe(self, value):
        return self.choices[value][0].lower()


class TagFilter:
    """
    A tag of the user's corpus, its descendants included (#130). No column: the tag
    badges and the list of tags of my references set it.
    """

    kind = "tag"
    params = ("tag",)

    def __init__(self, user):
        self.user = user

    def read(self, data, errors):
        return data.get("tag", "").strip() or None

    def apply(self, queryset, value):
        return queryset.filter(tags.tagged(self.user, value))

    def describe(self, value):
        return f"« {tags.label(value)} »"


class ToIdentifyFilter:
    """
    Publications with references to identify (#276), ?to_identify=1. No column: the
    « À identifier » link of the navigation sets it.
    """

    kind = "flag"
    params = ("to_identify",)

    def read(self, data, errors):
        return True if data.get("to_identify") == "1" else None

    def apply(self, queryset, value):
        return queryset.filter(
            Exists(CitedReference.objects.to_identify().filter(source=OuterRef("pk")))
        )

    def describe(self, value):
        return "à identifier"


class TermFilter:
    """
    A keyword or a topic of the OpenAlex answers (#418), ?keyword= or ?topic=. No column:
    a double click on the map of the keywords sets it.
    """

    kind = "term"

    def __init__(self, terms):
        self.terms = terms
        self.params = (terms.param,)

    def read(self, data, errors):
        return data.get(self.terms.param, "").strip() or None

    def apply(self, queryset, value):
        return keyword_graph.carrying(queryset, self.terms, value)

    def describe(self, value):
        return f"« {value} »"


class NoteFilter:
    """
    My note (#443): ?note=aimant, the note contains the text (case and accents ignored,
    as in the search), or ?has_note=1 / 0, with a note or without. No column: the field
    above the table sets it.
    """

    kind = "note"
    params = ("note", "has_note")

    def __init__(self, user):
        self.user = user

    def read(self, data, errors):
        text = data.get("note", "").strip()
        if text:
            return text
        return {"1": True, "0": False}.get(data.get("has_note", ""))

    def apply(self, queryset, value):
        if isinstance(value, str):
            return queryset.filter(noted(self.user, value))
        with_note = UserPublication.objects.filter(
            user=self.user, publication=OuterRef("pk")
        ).exclude(note="")
        return queryset.filter(Exists(with_note) if value else ~Exists(with_note))

    def describe(self, value):
        if isinstance(value, str):
            return f"contient « {value} »"
        return "renseignée" if value else "absente"


@dataclass
class ActiveFilters:
    values: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    def __bool__(self):
        return bool(self.values)


class Filters:
    """The filterable columns of a table: column → (label, filter)."""

    def __init__(self, columns):
        self.columns = columns

    def read(self, data):
        active = ActiveFilters()
        for column, (_, column_filter) in self.columns.items():
            value = column_filter.read(data, active.errors)
            if value is not None:
                active.values[column] = value
        return active

    def apply(self, queryset, active):
        for column, value in active.values.items():
            queryset = self.columns[column][1].apply(queryset, value)
        return queryset


def title_contains(publications, text):
    return publications.alias(_title=Normalized(F("readable_title"))).filter(
        contains("_title", text)
    )


def author_contains(publications, text):
    return publications.filter(author_named(text.split()))


def name_contains(field_name):
    def apply(authors, text):
        alias = f"_{field_name}"
        return authors.alias(**{alias: Normalized(F(field_name))}).filter(contains(alias, text))

    return apply


PUBLICATIONS = Filters(
    {
        "title": ("Titre", TextFilter("title", title_contains)),
        "author": ("Auteurs", TextFilter("author", author_contains)),
        "identifier": (
            "Identifiant",
            ChoiceFilter(
                "identifier",
                {
                    "doi": ("Avec DOI", ~Q(doi="")),
                    "isbn": ("Avec ISBN", ~Q(isbn="")),
                    "none": ("Sans identifiant", Q(doi="", isbn="")),
                },
            ),
        ),
        "year": ("Année", YearsFilter()),
    }
)

# My references: the reading status, annotated by corpus.with_reading_status (#164).
CORPUS = Filters(
    PUBLICATIONS.columns
    | {
        "status": (
            "Lecture",
            ChoiceFilter(
                "status",
                {
                    **{
                        value: (label, Q(reading_status=value))
                        for value, label in UserPublication.ReadingStatus.choices
                    },
                    "none": ("Sans statut", Q(reading_status="")),
                },
            ),
        )
    }
)


def corpus_filters(user):
    """
    My corpus: the columns of CORPUS, the tags of the user, the references to identify,
    the notes of the user.
    """
    return Filters(
        CORPUS.columns
        | {
            "tag": ("Tag", TagFilter(user)),
            "to_identify": ("Références", ToIdentifyFilter()),
            "keyword": ("Mot-clé", TermFilter(keyword_graph.KEYWORDS)),
            "topic": ("Thème", TermFilter(keyword_graph.TOPICS)),
            "note": ("Note", NoteFilter(user)),
        }
    )


@dataclass
class CorpusSelection:
    """The publications of a corpus that the filters of « Mon corpus » keep (#285)."""

    filters: Filters
    active: ActiveFilters
    publications: object  # a queryset, annotated with the reading status
    # The URL parameters of the active filters, without the sort and the page.
    query: str = ""


def filtered_corpus(user, data):
    """
    The corpus of user filtered as the URL parameters data say, on every page: the table
    of « Mon corpus » and its exports read it alike, so that an export holds the
    publications shown.
    """
    columns = corpus_filters(user)
    active = columns.read(data)
    listed = with_reading_status(Publication.objects.filter(userpublication__user=user), user)
    return CorpusSelection(
        columns, active, columns.apply(listed, active), filter_query(columns, active, data)
    )


def filter_query(columns, active, data):
    params = {
        param: data[param]
        for column in active.values
        for param in columns.columns[column][1].params
        if data.get(param, "").strip()
    }
    return urlencode(params)


AUTHORS = Filters(
    {
        "last_name": ("Nom", TextFilter("last_name", name_contains("last_name"))),
        "first_name": ("Prénom", TextFilter("first_name", name_contains("first_name"))),
        "orcid": (
            "ORCID",
            ChoiceFilter(
                "orcid",
                {"with": ("Avec ORCID", ~Q(orcid="")), "without": ("Sans ORCID", Q(orcid=""))},
            ),
        ),
    }
)
