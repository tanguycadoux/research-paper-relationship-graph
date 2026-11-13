import re

NON_ISBN_CHARACTERS = re.compile(r"[^0-9X]")


def normalize_isbn(raw):
    """
    Return the canonical form of an ISBN: digits only, ISBN-13. A valid ISBN-10 is
    converted; anything else is only cleaned (validate with is_valid_isbn).
    """
    isbn = NON_ISBN_CHARACTERS.sub("", (raw or "").upper())
    if len(isbn) == 10 and is_valid_isbn10(isbn):
        return isbn10_to_isbn13(isbn)
    return isbn


def is_valid_isbn(isbn):
    """Check a normalized ISBN-13 (length and check digit)."""
    return len(isbn) == 13 and isbn.isdigit() and isbn13_check_digit(isbn[:12]) == isbn[12]


def is_valid_isbn10(isbn):
    if not (isbn[:9].isdigit() and (isbn[9].isdigit() or isbn[9] == "X")):
        return False
    values = [int(c) for c in isbn[:9]] + [10 if isbn[9] == "X" else int(isbn[9])]
    return sum((10 - i) * v for i, v in enumerate(values)) % 11 == 0


def isbn10_to_isbn13(isbn10):
    body = "978" + isbn10[:9]
    return body + isbn13_check_digit(body)


def isbn13_check_digit(first12):
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(first12))
    return str((10 - total % 10) % 10)
