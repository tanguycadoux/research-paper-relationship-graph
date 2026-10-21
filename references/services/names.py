"""Normalization of person names, shared by duplicate detection and affiliations."""

import re
import unicodedata

NAME_SEPARATORS = re.compile(r"[^\w]+")


def normalized(text):
    """Lower case, without accents."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def name_parts(name):
    """'Jean-Luc  Flambard' -> ['jean', 'luc', 'flambard']."""
    return [part for part in NAME_SEPARATORS.split(normalized(name)) if part]


def same_person_name(first, second):
    """Same words in any order: 'Thomas Thuillier' and 'Thuillier, Thomas'."""
    return sorted(name_parts(first)) == sorted(name_parts(second))
