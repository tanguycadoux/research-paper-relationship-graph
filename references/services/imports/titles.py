import html
import re

# JATS or MathML elements (<i>, <sub>, <scp>, <mml:math>…), not a lone "<" in the text.
TAG_PATTERN = re.compile(r"</?[A-Za-z][\w:.-]*(?:\s[^<>]*)?/?>")
SPACES_PATTERN = re.compile(r"\s+")


def clean_title(raw):
    """
    Return a title as plain text: markup removed, HTML entities decoded ("R&amp;D"
    becomes "R&D"), spaces collapsed. LaTeX is kept as is.
    """
    if not raw:
        return ""
    text = html.unescape(TAG_PATTERN.sub("", raw))
    return SPACES_PATTERN.sub(" ", text).strip()
