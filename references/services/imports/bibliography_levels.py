"""
The levels of the bibliographies around a starting point (#431), read in the base
without any request: level 1 is the bibliography of the start, level 2 those of the
publications it cites, level 3 those of the publications these cite. A level is known
exactly once the bibliographies of the level before are in the base; beyond, it is
estimated by the average number of identified references of a bibliography.

The cost of a level is its imports: the publications whose bibliography is still to come
from the sources. One costs about one request and 0.8 s through the queue, in batches
(#381: 50 imports, 41 s, 46 requests).
"""

from dataclasses import dataclass

from django.conf import settings
from django.db.models import Count, Exists, OuterRef, Q

from ...models import CitedReference, ExternalRecord, Publication
from ..sources.external_records import Source
from .preprints import ARXIV_PREFIX

DEPTHS = (2, 3)
MAX_DEPTH = max(DEPTHS)
SECONDS_PER_IMPORT = 0.8
REQUESTS_PER_IMPORT = 1


def needs_bibliography():
    """
    The condition on a publication whose bibliography is still to fetch: with a DOI,
    without any reference in the base, and either never asked to the sources (one was
    unreachable) or known with a bibliography to read: a list of references at Crossref,
    a DataCite record (its related identifiers), or an arXiv preprint whose LaTeX sources
    were never read (#227). Unknown to the sources, or without references at Crossref,
    it has nothing to give: importing it again would not change anything.
    """
    records = ExternalRecord.objects.filter(publication=OuterRef("pk"))
    known = records.filter(data__isnull=False)
    readable = (
        Exists(known.filter(source=Source.CROSSREF, data__message__has_key="reference"))
        | Exists(known.filter(source=Source.DATACITE))
        | (Q(doi__istartswith=ARXIV_PREFIX) & ~Exists(records.filter(source=Source.ARXIV)))
    )
    has_bibliography = Exists(CitedReference.objects.filter(source=OuterRef("pk")))
    return ~Q(doi="") & ~has_bibliography & (~Exists(records) | (Exists(known) & readable))


def to_import(pks):
    """The pks among pks whose bibliography is still to fetch."""
    return set(
        Publication.objects.filter(needs_bibliography(), pk__in=pks).values_list("pk", flat=True)
    )


def cited_by(pks, excluded):
    """
    The publications that the bibliographies of pks identify, outside excluded, the most
    cited by pks first: {pk: number of citations}, in that order.
    """
    cited = (
        CitedReference.objects.filter(source__in=pks)
        .exclude(target=None)
        .exclude(target__in=excluded)
        .values("target")
        .annotate(cites=Count("source", distinct=True))
        .order_by("-cites", "target")
    )
    return {row["target"]: row["cites"] for row in cited}


def average_references():
    """The average number of identified references of a bibliography of the base."""
    identified = CitedReference.objects.exclude(target=None)
    sources = identified.values("source").distinct().count()
    return identified.count() / sources if sources else 0


@dataclass
class Level:
    number: int
    # The publications whose bibliography forms the level, and those still to fetch.
    publications: int
    imports: int
    exact: bool


@dataclass
class Estimate:
    """What a request up to each depth would import, and its cost."""

    levels: list
    average: float
    limit: int

    def choice(self, depth):
        """The imports up to depth (capped), their requests and minutes, and the cap."""
        wanted = sum(level.imports for level in self.levels[:depth])
        imports = min(wanted, self.limit)
        return {
            "depth": depth,
            "imports": imports,
            "capped": wanted > self.limit,
            "exact": all(level.exact for level in self.levels[:depth]),
            "requests": round(imports * REQUESTS_PER_IMPORT),
            "minutes": duration_minutes(imports),
        }

    @property
    def choices(self):
        return [self.choice(depth) for depth in DEPTHS]


def duration_minutes(imports):
    """The duration of imports, in whole minutes, at least one when there is any."""
    seconds = imports * SECONDS_PER_IMPORT
    return max(1, round(seconds / 60)) if imports else 0


def estimate(start_pks, depth=MAX_DEPTH):
    """
    The levels 1 to depth from the publications start_pks. Each level counts its
    publications and its imports exactly as long as the level before is in the base; the
    bibliographies still to fetch bring about average publications each, all assumed to
    be imported (an upper bound: some are already in the base).
    """
    average = average_references()
    members, visited, guessed = set(start_pks), set(start_pks), 0
    levels = []
    for number in range(1, depth + 1):
        missing = to_import(members)
        levels.append(Level(number, len(members) + guessed, len(missing) + guessed, not guessed))
        guessed = round((len(missing) + guessed) * average)
        members = set(cited_by(members - missing, visited))
        visited |= members
    return Estimate(levels, average, settings.BIBLIOGRAPHY_REQUEST_LIMIT)
