"""
Export of a user's corpus, and import of such an export: as JSON (identifiers
only, the shared corrections stay in the database) or as BibTeX (export only).
"""

import re
import unicodedata
from dataclasses import dataclass, field

from django.utils import timezone

from ..models import Publication, UserPublication
from .corpus import add_identified, find_or_create
from .external_records import Source, records_by_source

EXPORT_FORMAT = "research-paper-relationship-graph/corpus"
EXPORT_VERSION = 1


def corpus_publications(user):
    return Publication.objects.filter(userpublication__user=user).order_by("title")


def exportable(publications):
    """Publications that can be imported again: those with a DOI or an ISBN."""
    return [pub for pub in publications if pub.doi or pub.isbn]


# JSON


def export_corpus(user):
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exported_at": timezone.now().isoformat(),
        "publications": [
            {"doi": pub.doi, "isbn": pub.isbn, "title": pub.title}
            for pub in exportable(corpus_publications(user))
        ],
    }


class InvalidExport(ValueError):
    pass


@dataclass
class ImportReport:
    added: list = field(default_factory=list)
    already_there: list = field(default_factory=list)
    without_metadata: list = field(default_factory=list)
    ignored: int = 0


def import_corpus(user, data):
    """
    Add the publications of an export to the corpus of user. Only publications
    without stored metadata are fetched from the external sources.
    """
    entries = export_entries(data)
    report = ImportReport()
    in_corpus = set(UserPublication.objects.filter(user=user).values_list("publication", flat=True))
    for entry in entries:
        pub = find_or_create(entry.get("doi"), entry.get("isbn"))
        if pub is None:
            report.ignored += 1
        elif pub.pk in in_corpus:
            report.already_there.append(pub)
        else:
            in_corpus.add(pub.pk)
            imported = add_identified(user, pub)
            # The publication imported may be the published version of a preprint (#227).
            if imported:
                report.added.append(imported)
            else:
                report.without_metadata.append(pub)
    return report


def export_entries(data):
    if not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT:
        raise InvalidExport("Ce fichier n'est pas un export de corpus de cette application.")
    if data.get("version") != EXPORT_VERSION:
        raise InvalidExport(f"Version d'export non prise en charge : {data.get('version')}.")
    entries = data.get("publications")
    if not isinstance(entries, list):
        raise InvalidExport("L'export ne contient pas de liste de publications.")
    return [entry for entry in entries if isinstance(entry, dict)]


# BibTeX

ENTRY_TYPES = {
    "journal-article": "article",
    "proceedings-article": "inproceedings",
    "book": "book",
    "monograph": "book",
    "book-chapter": "incollection",
}
VENUE_FIELDS = {"article": "journal", "inproceedings": "booktitle", "incollection": "booktitle"}
MATH_PATTERN = re.compile(r"(\$[^$]*\$)")
SPECIAL_CHARACTERS = re.compile(r"([&%#_])")


def corpus_bibtex(user):
    keys = set()
    publications = exportable(
        corpus_publications(user).prefetch_related("authorpublication_set__author")
    )
    return "\n".join(bibtex_entry(pub, keys) for pub in publications)


def bibtex_entry(pub, keys):
    crossref = (records_by_source(pub).get(Source.CROSSREF) or {}).get("message", {})
    entry_type = ENTRY_TYPES.get(crossref.get("type"), "book" if pub.isbn else "misc")
    fields = {
        "title": "{" + bibtex_escape(pub.title) + "}",
        "author": " and ".join(bibtex_name(author) for author in ordered_authors(pub)),
        "year": str(pub.publication_date.year) if pub.publication_date else "",
        "doi": pub.doi,
        "isbn": pub.isbn,
    }
    venue = next(iter(crossref.get("container-title", [])), "")
    if entry_type in VENUE_FIELDS:
        fields[VENUE_FIELDS[entry_type]] = bibtex_escape(venue)
    lines = [f"@{entry_type}{{{citation_key(pub, keys)},"]
    lines += [f"  {name} = {{{value}}}," for name, value in fields.items() if value]
    return "\n".join(lines) + "\n}\n"


def ordered_authors(pub):
    slots = sorted(pub.authorpublication_set.all(), key=lambda slot: slot.order)
    return list(dict.fromkeys(slot.author for slot in slots))


def bibtex_name(author):
    if author.first_name:
        return f"{author.last_name}, {author.first_name}"
    return author.last_name


def bibtex_escape(text):
    """Escape the special characters outside $…$: LaTeX in titles is kept as is."""
    parts = MATH_PATTERN.split(text)
    return "".join(
        part if MATH_PATTERN.fullmatch(part) else SPECIAL_CHARACTERS.sub(r"\\\1", part)
        for part in parts
    )


def citation_key(pub, keys):
    """Last name of the first author and year, made unique with a letter: lovelace1843a."""
    authors = ordered_authors(pub)
    name = authors[0].last_name if authors else (pub.title.split() or ["ref"])[0]
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z]", "", ascii_name.lower()) or "ref"
    base += str(pub.publication_date.year) if pub.publication_date else ""
    key, suffix = base, ord("a")
    while key in keys:
        key, suffix = f"{base}{chr(suffix)}", suffix + 1
    keys.add(key)
    return key
