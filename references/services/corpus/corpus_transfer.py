"""
Export of a user's corpus, and import of such an export: as JSON (identifiers
only, the shared corrections stay in the database) or as BibTeX. The import also
reads the BibTeX and RIS files of reference managers (bibliography_files).
"""

import re
import unicodedata
from dataclasses import dataclass, field

from django.utils import timezone

from ...models import Publication, UserPublication
from ..identifiers.doi import is_valid_doi, normalize_doi
from ..sources.doi_registration import unregistered_dois
from ..sources.external_records import Source, records_by_source
from .entries import add_identified, find_or_create, queue_identified, with_reading_status
from .tags import InvalidTag, tag_entry, tags_by_publication

EXPORT_FORMAT = "research-paper-relationship-graph/corpus"
# Version 2 adds the reading status (#164) and the tags (#130), version 3 the note
# (#283), as optional keys: versions 1 and 2 still import.
EXPORT_VERSION = 3
IMPORTED_VERSIONS = (1, 2, 3)


def corpus_publications(user, selected=None):
    """
    The corpus of user, by title; only the publications of selected if given (a queryset
    of publications: those the filters of « Mon corpus » show, #285). Whatever selected
    holds, nothing outside the corpus of user is exported.
    """
    publications = Publication.objects.filter(userpublication__user=user).order_by("title")
    if selected is not None:
        publications = publications.filter(pk__in=selected.values("pk"))
    return publications


def exportable(publications):
    """Publications that can be imported again: those with a DOI or an ISBN."""
    return [pub for pub in publications if pub.doi or pub.isbn]


def notes_by_publication(user):
    """The notes of the corpus of user (#283): publication id → note, the empty ones left out."""
    entries = UserPublication.objects.filter(user=user).exclude(note="")
    return dict(entries.values_list("publication_id", "note"))


# JSON


def export_corpus(user, selected=None):
    publications = exportable(with_reading_status(corpus_publications(user, selected), user))
    tags = tags_by_publication(user, publications)
    notes = notes_by_publication(user)
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exported_at": timezone.now().isoformat(),
        "publications": [
            {
                "doi": pub.doi,
                "isbn": pub.isbn,
                "title": pub.title,
                "status": pub.reading_status,
                "tags": [tag.name for tag in tags[pub.pk]],
                "note": notes.get(pub.pk, ""),
            }
            for pub in publications
        ],
    }


class InvalidExport(ValueError):
    pass


@dataclass
class ImportReport:
    added: list = field(default_factory=list)
    already_there: list = field(default_factory=list)
    without_metadata: list = field(default_factory=list)
    # Titles of the entries without a valid DOI or ISBN.
    ignored: list = field(default_factory=list)
    # Titles of the entries whose only identifier is a DOI unknown to doi.org (#240).
    unregistered: list = field(default_factory=list)
    # Added, their retrieval left to the queue (#378).
    queued: list = field(default_factory=list)


def import_corpus(user, data, default_status="", *, queued=False):
    """Add the publications of an export of this application to the corpus of user."""
    return import_entries(user, export_entries(data), default_status, queued=queued)


def import_entries(user, entries, default_status="", *, queued=False):
    """
    Add the publications of entries ({doi, isbn, title}, and status, tags and note from
    an export) to the corpus of user, the new ones with default_status when an entry has
    none: « à lire » leaves the bibliographies aside (#234). Only publications without
    stored metadata are fetched from the external sources. The status and the note of
    an entry never replace those the user wrote; its tags are added to those of the user. A DOI
    that doi.org does not know is dropped, the ISBN of the entry used instead if any.
    Queued, the publications are fetched by the fetch_worker command (#378).
    """
    report = ImportReport()
    in_corpus = set(UserPublication.objects.filter(user=user).values_list("publication", flat=True))
    dois = [entry_doi(entry) for entry in entries]
    unregistered = unregistered_dois([doi for doi in dois if is_valid_doi(doi)])
    for entry, doi in zip(entries, dois, strict=True):
        fake_doi = doi in unregistered
        pub = find_or_create("" if fake_doi else doi, entry.get("isbn"), queued=queued)
        file_status = entry.get("status")
        if file_status not in UserPublication.ReadingStatus.values:
            file_status = ""
        if pub is None:
            dropped = report.unregistered if fake_doi else report.ignored
            dropped.append(str(entry.get("title") or ""))
            continue
        if pub.pk in in_corpus:
            report.already_there.append(pub)
        else:
            in_corpus.add(pub.pk)
            add = add_queued if queued else add_now
            pub = add(user, pub, file_status or default_status, report)
        keep_status(user, pub, file_status)
        add_tags(user, pub, entry.get("tags"))
        keep_note(user, pub, entry.get("note"))
    return report


def add_now(user, pub, status, report):
    """Add and fetch pub; return the publication added, maybe the published version (#227)."""
    imported = add_identified(user, pub, status)
    if imported:
        report.added.append(imported)
        return imported
    report.without_metadata.append(pub)
    return pub


def add_queued(user, pub, status, report):
    if queue_identified(user, pub, status):
        report.queued.append(pub)
    else:
        report.added.append(pub)
    return pub


def entry_doi(entry):
    return normalize_doi(str(entry.get("doi") or ""))


def add_tags(user, pub, names):
    entry = UserPublication.objects.filter(user=user, publication=pub).first()
    if entry is None or not isinstance(names, list):
        return
    for name in filter(lambda name: isinstance(name, str), names):
        try:
            tag_entry(entry, name)
        except InvalidTag:
            pass


def keep_status(user, pub, status):
    if status in UserPublication.ReadingStatus.values:
        UserPublication.objects.filter(user=user, publication=pub, reading_status="").update(
            reading_status=status
        )


def keep_note(user, pub, note):
    if isinstance(note, str) and note.strip():
        UserPublication.objects.filter(user=user, publication=pub, note="").update(
            note=note.strip()
        )


def export_entries(data):
    if not isinstance(data, dict) or data.get("format") != EXPORT_FORMAT:
        raise InvalidExport("Ce fichier n'est pas un export de corpus de cette application.")
    if data.get("version") not in IMPORTED_VERSIONS:
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


def corpus_bibtex(user, selected=None):
    keys = set()
    publications = exportable(corpus_publications(user, selected).with_author_slots())
    tags = tags_by_publication(user, publications)
    notes = notes_by_publication(user)
    return "\n".join(
        bibtex_entry(pub, keys, tags[pub.pk], notes.get(pub.pk, "")) for pub in publications
    )


def bibtex_entry(pub, keys, tags=(), note=""):
    crossref = (records_by_source(pub).get(Source.CROSSREF) or {}).get("message", {})
    entry_type = ENTRY_TYPES.get(crossref.get("type"), "book" if pub.isbn else "misc")
    fields = {
        "title": "{" + bibtex_escape(pub.title) + "}",
        "author": " and ".join(bibtex_name(author) for author in ordered_authors(pub)),
        "year": str(pub.publication_date.year) if pub.publication_date else "",
        "doi": pub.doi,
        "isbn": pub.isbn,
        # Zotero reads « Projet A/Groupe A » as one tag.
        "keywords": ", ".join(bibtex_escape(tag.name) for tag in tags),
        # annote, not note: the bibliography styles print note in the reference.
        "annote": bibtex_note(note),
    }
    venue = next(iter(crossref.get("container-title", [])), "")
    if entry_type in VENUE_FIELDS:
        fields[VENUE_FIELDS[entry_type]] = bibtex_escape(venue)
    lines = [f"@{entry_type}{{{citation_key(pub, keys)},"]
    lines += [f"  {name} = {{{value}}}," for name, value in fields.items() if value]
    return "\n".join(lines) + "\n}\n"


def ordered_authors(pub):
    """The authors of pub in signature order, once each (slots prefetched in order)."""
    return list(dict.fromkeys(slot.author for slot in pub.authorpublication_set.all()))


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


def bibtex_note(note):
    """The note, escaped; its braces dropped when unbalanced, which would end the field."""
    text = bibtex_escape(note.strip())
    depth = 0
    for character in text:
        depth += {"{": 1, "}": -1}.get(character, 0)
        if depth < 0:
            break
    return text if depth == 0 else text.replace("{", "").replace("}", "")


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
