"""
Tables sorted by a column (#115): ?sort=year ascending, ?sort=-year descending. The
sort stays in the URL, works without JavaScript and before the pagination: the whole
list is sorted, not the page shown.
"""

from dataclasses import dataclass

from django.db.models import F, OuterRef, Subquery, Value
from django.db.models.functions import Concat

from ..models import AuthorPublication
from .search import Normalized


@dataclass(frozen=True)
class Sort:
    column: str
    descending: bool

    @property
    def param(self):
        return f"-{self.column}" if self.descending else self.column


@dataclass(frozen=True)
class Column:
    expression: object
    # The direction of a first click: the most recent years first, names from A.
    descending_first: bool = False


class Sorting:
    """The sortable columns of a table, the ties broken always in the same order."""

    def __init__(self, columns, ties, default):
        self.columns = columns
        self.ties = ties
        self.default = default

    def read(self, value):
        """The sort asked by ?sort=, the default one if it names no column."""
        value = value or ""
        column = value.removeprefix("-")
        if column not in self.columns:
            return self.default
        return Sort(column, value.startswith("-"))

    def next_sort(self, current, column):
        """The sort of a click on a column header: the other direction if it is sorted."""
        if current.column == column:
            return Sort(column, not current.descending)
        return Sort(column, self.columns[column].descending_first)

    def apply(self, queryset, sort):
        expression = self.columns[sort.column].expression
        first = (
            expression.desc(nulls_last=True) if sort.descending else expression.asc(nulls_last=True)
        )
        # Down to the id: rows that compare equal must not move between pages.
        return queryset.order_by(first, *(tie.asc() for tie in self.ties), "pk")


def first_author_name():
    """Family name, then given name, of the first author: « Lovelace Ada »."""
    slots = AuthorPublication.objects.filter(publication=OuterRef("pk")).order_by("order")
    name = Normalized(Concat("author__last_name", Value(" "), "author__first_name"))
    return Subquery(slots.annotate(_name=name).values("_name")[:1])


PUBLICATIONS = Sorting(
    columns={
        "title": Column(Normalized(F("title"))),
        "author": Column(first_author_name()),
        "year": Column(F("publication_date"), descending_first=True),
    },
    ties=[Normalized(F("title"))],
    default=Sort("year", descending=True),
)

AUTHORS = Sorting(
    columns={
        "last_name": Column(Normalized(F("last_name"))),
        "first_name": Column(Normalized(F("first_name"))),
    },
    ties=[Normalized(F("last_name")), Normalized(F("first_name"))],
    default=Sort("last_name", descending=False),
)
