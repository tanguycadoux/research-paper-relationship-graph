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
