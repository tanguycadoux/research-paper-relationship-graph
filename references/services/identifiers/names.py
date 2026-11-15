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


def same_name_but_middle_initials(first, second):
    """
    The same whole words, one of them with initials the other lacks: 'Hannah R. Meredith'
    and 'Hannah Meredith', 'G. van der Werf' and 'G. R. van der Werf' (#317). Never two
    different initials: 'J. Smith' and 'A. Smith' are not the same person.
    """
    left, right = name_parts(first), name_parts(second)
    words = sorted(part for part in left if len(part) > 1)
    if not words or words != sorted(part for part in right if len(part) > 1):
        return False
    initials = [sorted(part for part in parts if len(part) == 1) for parts in (left, right)]
    fewer, more = sorted(initials, key=len)
    return all(fewer.count(initial) <= more.count(initial) for initial in fewer)


def same_words_up_to_initials(first, second):
    """
    Same words in any order, an initial standing for a whole word: 'E. Fernandez Mora'
    and 'Fernandez Mora, Elena'.
    """
    left, right = name_parts(first), name_parts(second)
    if len(left) != len(right):
        return False
    # Whole words first, so that an initial does not take the word another one matches.
    for part in sorted(left, key=len, reverse=True):
        match = next((word for word in right if word == part), None)
        if match is None:
            match = next((word for word in right if is_initial_of(part, word)), None)
        if match is None:
            return False
        right.remove(match)
    return True


def is_initial_of(part, word):
    short, long = sorted((part, word), key=len)
    return len(short) == 1 and long.startswith(short)
