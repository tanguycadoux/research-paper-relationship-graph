"""
Importance of a publication in the citation graph (#432): its PageRank, computed by
igraph on the identified citations. A publication cited by publications that are
themselves cited weighs more than one cited by as many unknown ones.

Two scopes, compared on the base of the user in the pull request of #432:

- SCOPE_BASE, the whole base: the importance for everything the base knows, the same
  for every user, kept in the cache of Django until the citations change;
- SCOPE_CONTEXT, the subgraph of the context (corpus or tag) and of the publications
  it cites: the importance for the subject, computed at each request.

SCOPE says which one the suggestions use; the other one stays a constant away.
"""

import igraph
from django.core.cache import cache
from django.db.models import Count, F, Max, Q, Sum

from ...models import CitedReference
from ..corpus.tags import context_publications

SCOPE_BASE = "base"
SCOPE_CONTEXT = "context"
SCOPE = SCOPE_BASE

# The usual damping factor: a reader follows a reference 85 times out of 100.
DAMPING = 0.85
# Long enough for a base that does not change; the signature makes it exact anyway.
CACHE_SECONDS = 24 * 3600


def pagerank(edges):
    """{publication id: PageRank} of the directed graph of (citing, cited) edges."""
    nodes = sorted({pk for edge in edges for pk in edge})
    if not nodes:
        return {}
    index = {pk: position for position, pk in enumerate(nodes)}
    graph = igraph.Graph(
        n=len(nodes), edges=[(index[a], index[b]) for a, b in edges], directed=True
    )
    return dict(zip(nodes, graph.pagerank(damping=DAMPING), strict=True))


def citation_edges(filter_q=None):
    """The (citing, cited) pairs of identified citations, once each, without loops."""
    refs = CitedReference.objects.filter(target__isnull=False).exclude(target=F("source"))
    if filter_q is not None:
        refs = refs.filter(filter_q)
    return set(refs.values_list("source_id", "target_id"))


def signature():
    """A summary of the identified citations: another one, and the cached ranks are old."""
    summary = CitedReference.objects.filter(target__isnull=False).aggregate(
        count=Count("pk"), last=Max("pk"), sources=Sum("source_id"), targets=Sum("target_id")
    )
    return ":".join(str(summary[key] or 0) for key in ("count", "last", "sources", "targets"))


def base_ranks():
    """The PageRank of the whole base, from the cache while the citations are the same."""
    key = f"pagerank:base:{signature()}"
    return cache.get_or_set(key, lambda: pagerank(citation_edges()), CACHE_SECONDS)


def context_ranks(user, tag=""):
    """The PageRank of the subgraph of the context and of the publications it cites."""
    sources = context_publications(user, tag).values("pk")
    cited = CitedReference.objects.filter(source__in=sources, target__isnull=False).values(
        "target_id"
    )
    inside = (Q(source__in=sources) | Q(source__in=cited)) & (
        Q(target__in=sources) | Q(target__in=cited)
    )
    return pagerank(citation_edges(inside))


def ranks(user, tag="", scope=None):
    """{publication id: PageRank} in the scope used by the suggestions."""
    if (scope or SCOPE) == SCOPE_CONTEXT:
        return context_ranks(user, tag)
    return base_ranks()
