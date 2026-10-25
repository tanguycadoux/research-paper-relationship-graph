"""
Information already present in the stored Crossref answer of a publication,
displayed without any new request: venue, citation count, funders (named after
OpenAlex when it knows them), licenses and subjects. The abstract comes from
Crossref, or else from OpenAlex.
"""

import html
import re
from urllib.parse import urlsplit

from .external_records import Source, records_by_source

JATS_TITLE = re.compile(r"<jats:title>.*?</jats:title>", re.DOTALL)
JATS_PARAGRAPH = re.compile(r"</?jats:p[^>]*>")
TAG = re.compile(r"<[^>]+>")
SPACES = re.compile(r"\s+")
SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([.,;:!?)])")

# Beyond this length, the abstract is folded (#157).
LONG_ABSTRACT = 800

CREATIVE_COMMONS = re.compile(
    r"creativecommons\.org/(?:licenses|publicdomain)/([a-z-]+)/(\d+(?:\.\d+)?)", re.IGNORECASE
)
STM_POLICY = re.compile(r"doi\.org/10\.15223/policy-(\d+)", re.IGNORECASE)
# Licenses of publishers, by URL without its scheme.
PUBLISHER_LICENSES = {
    "ieeexplore.ieee.org/Xplorehelp/downloads/license-information/IEEE.html": (
        "Licence de l'éditeur IEEE"
    ),
    "ieeexplore.ieee.org/Xplorehelp/downloads/license-information/USG.html": (
        "Œuvre du gouvernement des États-Unis (IEEE)"
    ),
    "iopscience.iop.org/info/page/text-and-data-mining": "Fouille de textes autorisée (IOP)",
}
# Version of the work a Crossref license applies to.
LICENSE_VERSIONS = {
    "vor": "version publiée",
    "am": "manuscrit accepté",
    "tdm": "fouille de textes",
    "stm-asf": "partage d'articles",
}


def crossref_details(pub):
    """Displayable details of the Crossref answer, or None if Crossref does not know pub."""
    records = records_by_source(pub)
    message = (records.get(Source.CROSSREF) or {}).get("message")
    if not message:
        return None
    openalex_funders = (records.get(Source.OPENALEX) or {}).get("funders") or []
    return {
        "venue": clean_text(next(iter(message.get("container-title", [])), "")),
        "citation_count": message.get("is-referenced-by-count"),
        "subjects": [clean_text(subject) for subject in message.get("subject", [])],
        "funders": funder_labels(message.get("funder", []), openalex_funders),
        "licenses": license_labels(message.get("license", [])),
    }


def publication_abstract(pub):
    """
    {"paragraphs", "source", "long"} of the abstract given by Crossref, or else by
    OpenAlex (#157); None when neither gives one.
    """
    records = records_by_source(pub)
    message = (records.get(Source.CROSSREF) or {}).get("message") or {}
    paragraphs, source = abstract_paragraphs(message.get("abstract", "")), "Crossref"
    if not paragraphs:
        work = records.get(Source.OPENALEX) or {}
        text = inverted_index_text(work.get("abstract_inverted_index"))
        paragraphs, source = [text] if text else [], "OpenAlex"
    if not paragraphs:
        return None
    long = sum(len(paragraph) for paragraph in paragraphs) > LONG_ABSTRACT
    return {"paragraphs": paragraphs, "source": source, "long": long}


def inverted_index_text(inverted_index):
    """OpenAlex gives the abstract as {word: [positions]}: put the words back in order."""
    if not inverted_index:
        return ""
    words = {position: word for word, positions in inverted_index.items() for position in positions}
    return clean_text(" ".join(words[position] for position in sorted(words)))


def license_labels(licenses):
    """{"url", "label", "versions"} of each license, versions being those it applies to."""
    versions = {}
    for lic in licenses:
        kinds = versions.setdefault(lic["URL"], [])
        version = LICENSE_VERSIONS.get(lic.get("content-version"))
        if version and version not in kinds:
            kinds.append(version)
    return [
        {"url": url, "label": license_label(url), "versions": ", ".join(kinds)}
        for url, kinds in versions.items()
    ]


def license_label(url):
    """'CC BY 4.0', a known publisher license, or else the site that publishes it."""
    if match := CREATIVE_COMMONS.search(url):
        kind, version = match.groups()
        name = "CC0" if kind.lower() == "zero" else "CC " + kind.upper()
        return f"{name} {version}"
    if match := STM_POLICY.search(url):
        return f"Politique de partage STM n° {int(match.group(1))}"
    parts = urlsplit(url)
    known = PUBLISHER_LICENSES.get(parts.netloc + parts.path)
    return known or f"Licence publiée par {parts.netloc or url}"


def funder_labels(funders, openalex_funders=()):
    """
    One label per funder. Publishers sometimes deposit a funder in damaged forms
    (« french “Agence… », « Agence … de 308 la Recherche »). Identified funders are
    the reference: Crossref entries with a DOI (Open Funder Registry), then those of
    OpenAlex. They take in the other Crossref entries that share one of their award
    numbers or contain their name; the remaining entries are merged by name.
    """
    identified = {}  # comparable name: (name, awards)
    for funder in funders:
        if funder.get("DOI"):
            name = clean_text(funder.get("name", ""))
            identified.setdefault(comparable_name(name), (name, []))[1].extend(
                funder.get("award", [])
            )
    for funder in openalex_funders:
        name = clean_text(funder.get("display_name") or "")
        identified.setdefault(comparable_name(name), (name, []))
    others = {}  # comparable name: (name, awards)
    for funder in funders:
        if funder.get("DOI"):
            continue
        awards = funder.get("award", [])
        reference = matching_identified(identified.values(), funder.get("name", ""), awards)
        if reference is None:
            name = clean_text(funder.get("name", ""))
            reference = others.setdefault(comparable_name(name), (name, []))
        reference[1].extend(awards)
    return [
        funder_label(name, awards)
        for name, awards in [*identified.values(), *others.values()]
        if name
    ]


def matching_identified(identified, name, awards):
    """The identified funder sharing an award number, or whose name is in name (whole words)."""
    words = f" {comparable_name(clean_text(name))} "
    for reference in identified:
        reference_name, reference_awards = reference
        reference_words = comparable_name(reference_name)
        if set(awards) & set(reference_awards) or (
            reference_words and f" {reference_words} " in words
        ):
            return reference
    return None


def comparable_name(name):
    """Lowercase words of letters only: « Agence de 308 la » gives « agence de la »."""
    return " ".join("".join(c if c.isalpha() else " " for c in name.casefold()).split())


def funder_label(name, awards):
    awards = ", ".join(dict.fromkeys(awards))
    return f"{name} ({awards})" if awards else name


def abstract_paragraphs(jats):
    """Paragraphs of a JATS abstract as plain text, without its 'Abstract' title."""
    text = JATS_TITLE.sub("", jats)
    return [clean_text(part) for part in JATS_PARAGRAPH.split(text) if clean_text(part)]


def clean_text(text):
    """Remove tags and HTML entities ('&#x201C;'), collapse spaces."""
    text = SPACES.sub(" ", html.unescape(TAG.sub(" ", text))).strip()
    return SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
