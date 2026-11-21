"""Words of the messages, agreed with a number (#346)."""


def count(number, singular, plural=None):
    """
    « 1 publication ajoutée », « 3 publications ajoutées »: 0 and 1 take the singular,
    in French. The plural adds an s to each word, unless given (« qui citent »).
    """
    if number > 1:
        words = plural or " ".join(f"{word}s" for word in singular.split())
    else:
        words = singular
    return f"{number} {words}"


def suffix(number, suffixes="s"):
    """
    The ending of a word agreed with number, as Django's pluralize but in French: 0 and
    1 take the singular (#411). « s » or « nt » alone is the plural ending; « a,ont »
    gives both.
    """
    singular, _, plural = suffixes.rpartition(",")
    return plural if number > 1 else singular
