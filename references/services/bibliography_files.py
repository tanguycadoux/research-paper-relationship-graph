"""
Entries of a bibliography file exported by a reference manager (Zotero, JabRef,
Google Scholar…), as BibTeX or RIS (#165). Only the identifiers are read: the DOI,
else the arXiv identifier (the DOI 10.48550/arXiv.…), else the first valid ISBN.
The title only names an entry that has none; the rest comes from the sources.

The parsing is tolerant, without macros nor string expansion: an entry that cannot
be read gives no identifier rather than an error.
"""

import re

from .doi import is_valid_doi, normalize_doi
from .isbn import is_valid_isbn, normalize_isbn
from .latex_bibliography import clean_latex, written_identifier

ENTRY_START = re.compile(r"@\s*(\w+)\s*([{(])")
FIELD_NAME = re.compile(r"[\s,]*([\w\-:.]+)\s*=\s*")
BARE_VALUE = re.compile(r"[^,#}\s]+")
SEPARATOR = re.compile(r"\s*#\s*")
SKIPPED_TYPES = {"comment", "string", "preamble"}
BARE_ARXIV_ID = re.compile(
    r"(?:arXiv\s*:\s*)?(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", re.IGNORECASE
)
# Fields where an identifier may be written in passing (an arXiv reference in the
# journal field, a DOI in the URL or the note).
BIBTEX_OTHER_FIELDS = ("url", "journal", "note", "number", "howpublished")
RIS_LINE = re.compile(r"^([A-Z][A-Z0-9])  -\s?(.*)$")
RIS_TITLES = ("TI", "T1", "BT", "CT")
RIS_OTHER_FIELDS = ("UR", "JO", "T2", "N1", "M3")


def file_entries(text):
    """The entries of a BibTeX or RIS file, as {doi, isbn, title}, told apart by the content."""
    if re.search(r"^TY  -", text, re.MULTILINE):
        return ris_entries(text)
    return bibtex_entries(text)


def entry(title, dois=(), eprints=(), isbns=(), others=()):
    doi = (
        first_doi(dois)
        or arxiv_doi(eprints)
        or written_identifier(" ".join(value for value in others if value))
    )
    return {"doi": doi, "isbn": "" if doi else first_isbn(isbns), "title": title}


def first_doi(values):
    for value in values:
        doi = normalize_doi(value.replace("\\_", "_"))
        if is_valid_doi(doi):
            return doi
    return ""


def arxiv_doi(values):
    for value in values:
        match = BARE_ARXIV_ID.fullmatch(value.strip())
        if match:
            return normalize_doi(f"10.48550/arXiv.{match.group(1)}")
    return ""


def first_isbn(values):
    """The first valid ISBN of the fields, which may hold several (`978…; 978…`)."""
    for value in values:
        for part in re.split(r"[,;/]", value):
            for candidate in (part, *part.split()):
                isbn = normalize_isbn(candidate)
                if is_valid_isbn(isbn):
                    return isbn
    return ""


# BibTeX


def bibtex_entries(text):
    entries = []
    position = 0
    while start := ENTRY_START.search(text, position):
        end = closing(text, start.end(), ")" if start.group(2) == "(" else "}")
        position = end + 1
        if start.group(1).lower() not in SKIPPED_TYPES:
            fields = bibtex_fields(text[start.end() : end])
            archive = fields.get("archiveprefix", "").lower()
            entries.append(
                entry(
                    clean_latex(fields.get("title", "")).rstrip("."),
                    dois=[fields.get("doi", "")],
                    eprints=[fields.get("eprint", "")] if archive in ("", "arxiv") else [],
                    isbns=[fields.get("isbn", "")],
                    others=[fields.get(name, "") for name in BIBTEX_OTHER_FIELDS],
                )
            )
    return entries


def closing(text, start, end_char):
    """The position of the character closing an entry opened just before start."""
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if text[index - 1] == "\\":
            continue
        if char == "{":
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
        elif char == end_char and depth == 0:
            return index
    return len(text)


def bibtex_fields(body):
    """The fields of an entry body (`key, name = value, …`), names in lowercase."""
    fields = {}
    position = body.find(",") + 1
    if not position:
        return fields
    while name := FIELD_NAME.match(body, position):
        value, position = bibtex_value(body, name.end())
        if position == name.end():
            break
        fields[name.group(1).lower()] = value
    return fields


def bibtex_value(body, position):
    """A value and the position after it: braced, quoted or bare parts joined by #."""
    parts = []
    while position < len(body):
        char = body[position]
        if char == "{":
            end = closing(body, position + 1, "}")
            parts.append(body[position + 1 : end])
        elif char == '"':
            end = closing(body, position + 1, '"')
            parts.append(body[position + 1 : end])
        else:
            bare = BARE_VALUE.match(body, position)
            if not bare:
                break
            end = bare.end() - 1
            parts.append(bare.group(0))
        position = end + 1
        separator = SEPARATOR.match(body, position)
        if not separator:
            break
        position = separator.end()
    return "".join(parts).strip(), position


# RIS


def ris_entries(text):
    entries = []
    fields = None
    for line in text.splitlines():
        match = RIS_LINE.match(line.lstrip("﻿"))
        if not match:
            continue
        tag, value = match.group(1), match.group(2).strip()
        if tag == "TY":
            fields = {}
        elif tag == "ER" and fields is not None:
            entries.append(ris_entry(fields))
            fields = None
        elif fields is not None:
            fields.setdefault(tag, []).append(value)
    return entries


def ris_entry(fields):
    title = next((fields[tag][0] for tag in RIS_TITLES if tag in fields), "")
    return entry(
        title,
        dois=fields.get("DO", []),
        isbns=fields.get("SN", []),
        others=[value for tag in RIS_OTHER_FIELDS for value in fields.get(tag, [])],
    )
