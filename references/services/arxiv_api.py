"""
Client of arXiv: the e-print (LaTeX sources) of a preprint, for its bibliography (#227).
arXiv asks for no more than one request every 3 seconds: an e-print is fetched once,
when a preprint enters a corpus, never in batch.
"""

from . import http
from .latex_bibliography import read_eprint

EPRINT_URL = "https://arxiv.org/e-print/{}"
# Sources with heavy figures can weigh tens of megabytes: beyond, given up.
MAX_EPRINT_BYTES = 30 * 1024 * 1024


def fetch_arxiv_eprint(arxiv_id):
    """What the e-print holds (latex_bibliography.read_eprint), or None if unreachable."""
    raw = http.get_bytes(
        EPRINT_URL.format(arxiv_id),
        service="arXiv",
        subject=f"e-print {arxiv_id}",
        max_bytes=MAX_EPRINT_BYTES,
    )
    return None if raw is None else read_eprint(raw)
