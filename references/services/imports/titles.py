import html
import re

# JATS or MathML elements (<i>, <sub>, <scp>, <mml:math>…), not a lone "<" in the text.
TAG_PATTERN = re.compile(r"</?[A-Za-z][\w:.-]*(?:\s[^<>]*)?/?>")
SPACES_PATTERN = re.compile(r"\s+")
# Some publishers escape their markup twice (IEEE: "&amp;lt;sub&amp;gt;", #263).
MAX_UNESCAPES = 3


def clean_title(raw):
    """
    Return a title as plain text: HTML entities decoded ("R&amp;D" becomes "R&D"),
    then markup removed, spaces collapsed. Entities are decoded until none is left, so
    that markup escaped twice by the publisher is removed too. LaTeX is kept as is.
    """
    if not raw:
        return ""
    text = raw
    for _ in range(MAX_UNESCAPES):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    return SPACES_PATTERN.sub(" ", TAG_PATTERN.sub("", text)).strip()
