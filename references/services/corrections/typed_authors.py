"""
The authors of a publication typed by hand when a reference is identified without
identifier (#259), in signing order: authors already in the base, chosen by their id,
and new authors written « Nom, Prénom ».

One author per line, the same text with or without JavaScript:

    Goodfellow, Ian      a new author (the first name is optional)
    #42                  the author 42 of the base, chosen in the suggestions

A new author is created as typed, never matched to an existing one: the probable
duplicates are left to « Doublons probables ».
"""

import re
from dataclasses import dataclass

from django.db.models import Count

from ...models import Author, AuthorPublication
from ..display.search import Normalized, normalize, parse, search_authors
from ..identifiers.names import readable_case

EXISTING = re.compile(r"^#(\d+)$")
# Initials before a family name, as Crossref gives some cited authors: « J.-M. Lagniel ».
INITIALS = re.compile(r"^(?:\w{1,2}\.-?)+$")
NAME_LENGTH = 255
SUGGESTION_LIMIT = 10
MIN_SEARCH_LENGTH = 2
PROPOSAL_LIMIT = 5


@dataclass
class TypedAuthor:
    """An author slot to create: an author of the base, or a new name."""

    family: str
    given: str = ""
    author: Author | None = None

    @property
    def line(self):
        if self.author is not None:
            return f"#{self.author.pk}"
        return f"{self.family}, {self.given}" if self.given else self.family


class AuthorLineError(ValueError):
    pass


def parse_lines(text):
    """The authors of the text, in order; AuthorLineError on the first wrong line."""
    lines = [" ".join(line.split()) for line in (text or "").splitlines()]
    typed = [parse_line(line) for line in lines if line]
    existing = [entry.author.pk for entry in typed if entry.author is not None]
    if len(existing) != len(set(existing)):
        raise AuthorLineError("Un même auteur est choisi deux fois.")
    return typed


def parse_line(line):
    match = EXISTING.match(line)
    if match:
        return existing_author(int(match.group(1)))
    family, comma, given = (part.strip() for part in line.partition(","))
    if not family or "," in given:
        raise AuthorLineError(f"« {line} » : écrivez « Nom, Prénom » (prénom facultatif).")
    if len(family) > NAME_LENGTH or len(given) > NAME_LENGTH:
        raise AuthorLineError(f"« {line} » : nom trop long.")
    return TypedAuthor(family=family, given=given)


def existing_author(pk):
    author = Author.objects.filter(pk=pk).first()
    if author is None:
        raise AuthorLineError(f"L'auteur n° {pk} n'existe pas (ou plus) dans la base.")
    return TypedAuthor(family=author.last_name, given=author.first_name, author=author)


def create_slots(pub, typed):
    """
    The author slots of a new publication, in the order typed: a new author is created
    as typed, an author of the base is linked and never modified.
    """
    AuthorPublication.objects.bulk_create(
        AuthorPublication(
            publication=pub,
            author=entry.author
            or Author.objects.create(last_name=entry.family, first_name=entry.given),
            order=index,
            published_given_name=entry.given,
            published_family_name=entry.family,
        )
        for index, entry in enumerate(typed)
    )


def suggestions(text, limit=SUGGESTION_LIMIT):
    """Authors of the base for a text typed in the search field: name or ORCID."""
    # « Dupont, Jean », as a new author is typed, searches Dupont and Jean.
    text = " ".join((text or "").replace(",", " ").split())
    if len(text) < MIN_SEARCH_LENGTH:
        return []
    found = search_authors(parse(text))
    return described(found, limit)


def described(authors, limit):
    authors = authors.annotate(publication_count=Count("publications", distinct=True)).order_by(
        "-publication_count", "last_name", "first_name", "pk"
    )[:limit]
    return [describe(author) for author in authors]


def describe(author):
    return {
        "id": author.pk,
        "name": str(author) or "(sans nom)",
        "orcid": author.orcid,
        "publications": getattr(author, "publication_count", None),
    }


# Prefill (#259): the first author Crossref gives for the cited work, often only a
# family name (« Ackermann »), sometimes with initials (« P. Dolégiéviez ») or all in
# lower case (« rochepault »).


def cited_first_author(ref):
    """(family, given) of the first author of the reference, or None."""
    text = " ".join(str(ref.raw.get("author") or "").split())
    if not text:
        return None
    if "," in text:
        family, _, given = (part.strip() for part in text.partition(","))
    else:
        words = text.split()
        initials = [word for word in words if INITIALS.match(word)]
        family = " ".join(word for word in words if word not in initials)
        given = " ".join(initials)
    family = readable_case(family)
    return (family, given) if family else None


def matching_authors(family, given):
    """Authors of the base with this family name, and these initials if given."""
    authors = Author.objects.alias(_family=Normalized("last_name")).filter(
        _family=normalize(family)
    )
    if given:
        authors = authors.filter(first_name__istartswith=given[0])
    return described(authors, PROPOSAL_LIMIT)


def proposal(ref):
    """
    The first author to propose for the reference: its name as a line, and the authors
    of the base that may be them. None when the reference names no author.
    """
    cited = cited_first_author(ref)
    if cited is None:
        return None
    family, given = cited
    return {
        "line": TypedAuthor(family=family, given=given).line,
        "matches": matching_authors(family, given),
    }


def editor_entries(text):
    """
    The authors of the text, for the script that shows them as a list: a wrong line is
    kept as written, the form says what is wrong with it.
    """
    lines = [" ".join(line.split()) for line in (text or "").splitlines()]
    return [editor_entry(line) for line in lines if line]


def editor_entry(line):
    try:
        entry = parse_line(line)
    except AuthorLineError:
        return {"id": None, "name": line, "line": line}
    if entry.author is not None:
        return {**describe(entry.author), "line": entry.line}
    return {"id": None, "name": entry.line, "line": entry.line}
