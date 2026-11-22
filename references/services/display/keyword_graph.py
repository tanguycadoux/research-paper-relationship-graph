"""
Map of the keywords of a corpus (#418), in the manner of VOSviewer: one node per keyword,
one edge per pair of keywords that appear in the same publication. Nothing is asked of
any source: the keywords and the topics are in the answers of OpenAlex already kept in
the base (ExternalRecord.data).

- Keywords (`keywords`): written by OpenAlex from the title and the abstract, with
  synonyms (« HL-LHC », « High-Luminosity LHC »), left as they are (#418). Topics
  (`topics`): a coarser view, from a fixed list of OpenAlex, without synonyms.
- Size of a node: the number of publications of the corpus that carry the term.
  Weight of an edge: the number of publications that carry both.
- A threshold keeps the terms carried by at least that many publications; the edges link
  kept terms only. By default, the lowest threshold that keeps at most MOST_TERMS terms
  (#468). A term is named by its display name, the same in the graph and in the
  filter of « Mon corpus » that a double click opens (?keyword=, ?topic=).
- The publications without an answer from OpenAlex (no DOI, or unknown to OpenAlex)
  cannot appear: the page says how many.

Three queries whatever the size of the corpus: the terms of the answers (only the field
needed, extracted by the database), the size of the corpus, and the publications that
carry a kept term.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations

from django.urls import reverse
from django.utils.http import urlencode

from ...models import ExternalRecord, Publication
from ..corpus import tags

# The default threshold is the lowest that keeps at most this many terms (#468): beyond,
# the map is a tangle whose names cover each other. On the user's corpus (26
# publications), it is 2 for the keywords (29 kept; 117 with 1, as #418 had chosen) and 1
# for the topics (12); on the corpus of the benchmark (217 publications), 6 for the
# keywords (44 kept, where 2 kept 169 and 1 227 links) and 2 for the topics (26).
MOST_TERMS = 50
# The choices of the threshold go at least this far, and up to the default threshold.
MAX_MINIMUM = 10


@dataclass(frozen=True)
class Terms:
    """A kind of term of the OpenAlex answers: keywords, or topics."""

    field: str  # in the OpenAlex answer, and the kind in the URL (?kind=)
    param: str  # the filter of « Mon corpus » (?keyword=, ?topic=)
    label: str  # the choice of the page
    singular: str
    plural: str


KEYWORDS = Terms("keywords", "keyword", "Mots-clés", "mot-clé", "mots-clés")
TOPICS = Terms("topics", "topic", "Thèmes", "thème", "thèmes")
KINDS = {terms.field: terms for terms in (KEYWORDS, TOPICS)}


def requested_kind(query):
    """The kind of term asked in ?kind=, keywords by default."""
    return KINDS.get(query.get("kind", ""), KEYWORDS)


def requested_minimum(query):
    """The threshold asked in ?min=, from 1; None otherwise: the default of the corpus."""
    value = query.get("min", "")
    if value.isdigit() and int(value) >= 1:
        return int(value)
    return None


def kept_count(counts, minimum):
    """The number of terms carried by at least minimum publications."""
    return sum(1 for count in counts.values() if count >= minimum)


def default_minimum(counts):
    """The lowest threshold that keeps at most MOST_TERMS terms (#468)."""
    minimum = 1
    while kept_count(counts, minimum) > MOST_TERMS:
        minimum += 1
    return minimum


def term_names(entries):
    """The display names of the terms of an answer, each once."""
    return {entry["display_name"] for entry in entries or [] if entry.get("display_name")}


def terms_by_publication(publications, terms):
    """
    {publication id: set of term names} for the publications that OpenAlex answered, and
    the details of the topics, {name: « field › subfield »}.
    """
    rows = ExternalRecord.objects.filter(
        source=ExternalRecord.Source.OPENALEX, publication__in=publications
    ).values_list("publication_id", "data__id", f"data__{terms.field}")
    by_publication, details = {}, {}
    for publication_id, openalex_id, entries in rows:
        # An empty answer: OpenAlex does not know the publication.
        if not openalex_id:
            continue
        by_publication[publication_id] = term_names(entries)
        if terms is TOPICS:
            details.update(topic_details(entries))
    return by_publication, details


def topic_details(entries):
    return {
        entry["display_name"]: " › ".join(
            entry[level]["display_name"] for level in ("field", "subfield") if entry.get(level)
        )
        for entry in entries or []
        if entry.get("display_name")
    }


def carrying(publications, terms, name):
    """The publications that carry the term name, as a queryset: the filter of « Mon corpus »."""
    by_publication, _ = terms_by_publication(publications, terms)
    return publications.filter(pk__in=[pk for pk, names in by_publication.items() if name in names])


def highest_minimum(default):
    """The last choice of the threshold: MAX_MINIMUM, or the default when it is higher."""
    return max(MAX_MINIMUM, default)


def threshold_choices(counts, terms, default):
    """(threshold, label) from 1 to highest_minimum: « 2 publications (29 mots-clés) »."""
    choices = []
    for minimum in range(1, highest_minimum(default) + 1):
        kept = kept_count(counts, minimum)
        word = terms.singular if kept < 2 else terms.plural
        unit = "publication" if minimum == 1 else "publications"
        choices.append((minimum, f"{minimum} {unit} ({kept} {word})"))
    return choices


def co_occurrences(by_publication, kept):
    """{(name, name): number of publications that carry both}, between kept terms."""
    pairs = Counter()
    for names in by_publication.values():
        pairs.update(combinations(sorted(names & kept), 2))
    return pairs


def keyword_graph(user, tag="", terms=KEYWORDS, minimum=None):
    """
    The map of the terms of the user's corpus, or of a tag and its subtags: the
    Cytoscape elements, the publications listed by the card of a term, and what the
    page says around the graph (thresholds, publications left out). minimum: the
    threshold asked, brought back to the last choice; None for the default of this
    corpus (default_minimum).
    """
    corpus = tags.context_publications(user, tag)
    by_publication, details = terms_by_publication(corpus, terms)
    counts = Counter(name for names in by_publication.values() for name in names)
    default = default_minimum(counts)
    minimum = default if minimum is None else min(minimum, highest_minimum(default))
    kept = {name for name, count in counts.items() if count >= minimum}
    # The most carried first: at the centre of the starting spiral (keywords.js).
    order = sorted(kept, key=lambda name: (-counts[name], name.casefold()))
    ids = {name: f"t{index}" for index, name in enumerate(order)}
    carriers = defaultdict(list)
    for publication_id, names in sorted(by_publication.items()):
        for name in names & kept:
            carriers[name].append(publication_id)
    filter_url = corpus_filter_url(terms, tag)
    return {
        "nodes": [
            node_data(ids[name], name, carriers[name], details, filter_url) for name in order
        ],
        "edges": [
            edge_data(ids[first], ids[second], shared)
            for (first, second), shared in sorted(co_occurrences(by_publication, kept).items())
        ],
        "publications": listed_publications(carriers),
        "thresholds": threshold_choices(counts, terms, default),
        "minimum": minimum,
        "default_minimum": default,
        "unanswered": corpus.count() - len(by_publication),
        "without_terms": sum(1 for names in by_publication.values() if not names),
    }


def corpus_filter_url(terms, tag):
    """The URL of « Mon corpus » filtered on a term (and on the tag of the graph)."""

    def url(name):
        params = {terms.param: name, **({"tag": tag} if tag else {})}
        return f"{reverse('corpus')}?{urlencode(params)}"

    return url


def node_data(node_id, name, carriers, details, filter_url):
    return {
        "data": {
            "id": node_id,
            "label": name,
            # The field and the subfield of a topic, under its name on the card.
            "detail": details.get(name, ""),
            "publications": len(carriers),
            "publicationIds": carriers,
            # A double click opens « Mon corpus » filtered on the term (card.js).
            "url": filter_url(name),
        }
    }


def edge_data(source, target, shared):
    return {
        "data": {
            "id": f"{source}-{target}",
            "source": source,
            "target": target,
            "shared": shared,
        }
    }


def listed_publications(carriers):
    """{id: {label, year, url}} of the publications listed by the cards (keyword_selection.js)."""
    ids = {pk for listed in carriers.values() for pk in listed}
    publications = Publication.objects.filter(pk__in=ids).only(
        "pk", "title", "readable_title", "doi", "isbn", "publication_date"
    )
    return {
        str(pub.pk): {
            "label": str(pub),
            "year": pub.publication_date.year if pub.publication_date else None,
            "url": reverse("publication_detail", args=[pub.pk]),
        }
        for pub in publications
    }
