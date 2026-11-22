"""
The levels of a citation graph (#451), after the definition of #431: level 1 is the
publications linked to the start (its references, and on the graph of a publication
those citing it), level 2 the publications linked to level 1, both ways: their references
and the publications citing them. Only what is in the base is shown: no request.

The whole graph goes to level 2 with ?niveau=2 (graph_variants.LEVEL); one publication
of level 1 is developed alone with ?developper=<pk>, or reduced at level 2 with
?reduire=<pk>, the rest of the graph as it is. Level 2 at most for now.
"""

from dataclasses import dataclass, field

from django.urls import reverse
from django.utils.http import urlencode

from ..imports import bibliography_levels
from .graph_variants import LEVEL

DEVELOPED = "developper"
REDUCED = "reduire"
# The publication to select once the page is loaded: the one just developed or reduced.
SELECTED = "noeud"
# The params of a choice of a publication, forgotten when the level of the graph changes.
NODE_PARAMS = (DEVELOPED, REDUCED, SELECTED)


def pks(value):
    """The publication ids of a comma-separated list, the others left out."""
    return frozenset(int(part) for part in value.split(",") if part.strip().isdigit())


@dataclass(frozen=True)
class Expansion:
    """How far the graph goes: its level, and the publications developed or reduced."""

    level: int = 1
    developed: frozenset = field(default_factory=frozenset)
    reduced: frozenset = field(default_factory=frozenset)

    @classmethod
    def of(cls, query):
        return cls(
            level=int(LEVEL.chosen(query)),
            developed=pks(query.get(DEVELOPED, "")),
            reduced=pks(query.get(REDUCED, "")),
        )

    def expanded(self, level_one):
        """The publications of level 1 whose neighbours are shown."""
        chosen = set(level_one) if self.level >= 2 else self.developed & set(level_one)
        return chosen - self.reduced

    def toggle_query(self, query, pk, expanded):
        """
        The query string that develops the publication pk, or reduces it when expanded,
        and selects it once the page is loaded; the other params are kept.
        """
        params = query.copy()
        # At level 2 every publication is developed but those reduced; at level 1, none
        # but those developed.
        name, chosen = (REDUCED, self.reduced) if self.level >= 2 else (DEVELOPED, self.developed)
        adds = expanded == (self.level >= 2)
        chosen = chosen | {pk} if adds else chosen - {pk}
        if chosen:
            params[name] = ",".join(str(item) for item in sorted(chosen))
        else:
            params.pop(name, None)
        params[SELECTED] = str(pk)
        return params.urlencode()


def levels_of(source_ids, level_one):
    """{pk: level}: 0 for the start, 1 for level_one; the others are of level 2."""
    levels = dict.fromkeys(level_one, 1)
    levels.update(dict.fromkeys(source_ids, 0))
    return levels


def missing_bibliographies(graph):
    """
    The bibliographies the shown levels lack, as [(level, count)] for the levels with
    some: those of the start for level 1, those of the developed publications of level 1
    for level 2. Counted by bibliography_levels.to_import (#431): with a DOI, without any
    reference in the base, and with something to read at the sources.
    """
    by_level = {0: [], 1: []}
    for node in graph["nodes"]:
        data = node["data"]
        if data["level"] == 0 or data.get("expanded"):
            by_level[data["level"]].append(int(data["id"]))
    missing = [
        (level + 1, len(bibliography_levels.to_import(ids)))
        for level, ids in by_level.items()
        if ids
    ]
    return [(level, count) for level, count in missing if count]


def bibliography_request_url(publication=None, tag=""):
    """« Récupérer les bibliographies… » (#431) from the same start, up to level 2."""
    params = {"depth": 2}
    if publication is not None:
        params["publication"] = publication.pk
    elif tag:
        params["tag"] = tag
    return f"{reverse('bibliography_request')}?{urlencode(params)}"
