"""
Suggestions by co-citation (#162): the publications that several publications of a
context cite, the context being the corpus of a user or one of their tags with its
descendants. If four of my articles cite the same one, it is likely central to my
subject. Computed from the base alone, on the identified references only.

In a tag, a suggestion may already be in the corpus under another tag: it stays,
marked, so that an article of the subject is not missed (it may lack the tag).

Sorted by the citing articles of the context, by the citations in the literature
(OpenAlex, else Crossref, as stored at the import: no request), by those citations per
year, or by the importance in the citation graph (PageRank, importance.py) (#432).
"""

from collections import defaultdict

from django.db.models import (
    Case,
    Count,
    F,
    FloatField,
    IntegerField,
    OuterRef,
    Subquery,
    Value,
    When,
)
from django.db.models.fields.json import KT
from django.db.models.functions import Cast, ExtractYear, Greatest
from django.utils import timezone

from ...models import CitedReference, ExternalRecord, Publication
from ..corpus import tags
from ..corpus.tags import context_publications
from ..display.publication_table import corpus_ids, with_first_author
from ..display.search import Normalized
from ..display.sorting import PUBLICATIONS, Column, Sort, Sorting
from . import importance

Source = ExternalRecord.Source

# Cited by one article of the context is enough: the sorts by the citations in the
# literature and by importance bring the strong ones up (#432). ?min=2 asks for more.
MIN_CITING = 1
MIN_CITING_CHOICES = (1, 2)

# Column of the PageRank: not an SQL expression, sorted in Python (sorted_suggestions).
IMPORTANCE = "importance"


def literature_citations():
    """
    The citations in the literature of a publication: cited_by_count of its OpenAlex
    answer, else is-referenced-by-count of its Crossref one; None when neither has it.
    The source and the date of the answer come with it.
    """
    count = Case(
        When(source=Source.OPENALEX, then=Cast(KT("data__cited_by_count"), IntegerField())),
        When(
            source=Source.CROSSREF,
            then=Cast(KT("data__message__is-referenced-by-count"), IntegerField()),
        ),
    )
    records = (
        ExternalRecord.objects.filter(publication=OuterRef("pk"), data__isnull=False)
        .annotate(count=count)
        .filter(count__isnull=False)
        .order_by(Case(When(source=Source.OPENALEX, then=Value(0)), default=Value(1)))
    )
    return {
        "cited_count": Subquery(records.values("count")[:1]),
        "cited_source": Subquery(records.values("source")[:1]),
        "cited_at": Subquery(records.values("fetched_at")[:1]),
    }


def citations_per_year():
    """The citations in the literature divided by the years since the publication, 1 at least."""
    years = Greatest(timezone.now().year - ExtractYear("publication_date"), Value(1))
    return Cast(F("cited_count"), FloatField()) / Cast(years, FloatField())


SUGGESTIONS = Sorting(
    columns=PUBLICATIONS.columns
    | {
        "citing": Column(F("citing_count"), descending_first=True),
        "cited": Column(F("cited_count"), descending_first=True),
        "per_year": Column(F("cited_per_year"), descending_first=True),
        # Sorted in Python: the expression only makes the header a link.
        IMPORTANCE: Column(F("citing_count"), descending_first=True),
    },
    # The most cited by the context, then the most recent: the order before #432.
    ties=[
        F("citing_count").desc(),
        F("publication_date").desc(nulls_last=True),
        Normalized(F("readable_title")),
    ],
    default=Sort("citing", descending=True),
)


def min_citing(value):
    """The minimum asked by ?min=, MIN_CITING if it is not one of the choices."""
    return int(value) if value in {str(choice) for choice in MIN_CITING_CHOICES} else MIN_CITING


def co_cited(user, tag="", minimum=MIN_CITING):
    """
    The publications outside the context cited by at least minimum of its
    publications, annotated with citing_count and their citations in the literature.
    """
    sources = context_publications(user, tag).values("pk")
    # The count follows the filter: only the citations from the context are counted.
    suggestions = (
        Publication.objects.filter(citations__source__in=sources)
        .exclude(pk__in=sources)
        .annotate(citing_count=Count("citations__source", distinct=True))
        .filter(citing_count__gte=minimum)
        .annotate(**literature_citations())
        .annotate(cited_per_year=citations_per_year())
    )
    return with_first_author(suggestions)


def sorted_suggestions(user, tag="", minimum=MIN_CITING, sort=SUGGESTIONS.default):
    """
    The suggestions in the order asked, and {publication id: PageRank} of each of them.
    By importance, the whole list is sorted in Python (a few hundred rows; sorted() is
    stable, so the ties keep the default order); otherwise in SQL.
    """
    suggestions = co_cited(user, tag, minimum)
    all_ranks = importance.ranks(user, tag)
    ranks = {pk: all_ranks.get(pk, 0.0) for pk in suggestions.values_list("pk", flat=True)}
    if sort.column != IMPORTANCE:
        return SUGGESTIONS.apply(suggestions, sort), ranks
    ordered = SUGGESTIONS.apply(suggestions, SUGGESTIONS.default)
    rows = sorted(ordered, key=lambda pub: ranks[pub.pk], reverse=sort.descending)
    return rows, ranks


def describe(user, publications, tag="", ranks=None):
    """
    Set on each suggestion of a page: citing, the publications of the context that
    cite it, newest first; in_corpus and my_tags, when it is already in the corpus;
    importance, its PageRank relative to the highest of the suggestions (0 to 100).
    """
    citing = defaultdict(list)
    refs = (
        CitedReference.objects.filter(
            target__in=publications, source__in=context_publications(user, tag)
        )
        .select_related("source")
        .order_by("-source__publication_date", "source__readable_title", "source_id")
    )
    for ref in refs:
        if ref.source not in citing[ref.target_id]:
            citing[ref.target_id].append(ref.source)
    in_corpus = corpus_ids(user)
    tags_by_publication = tags.tags_by_publication(user, publications)
    for pub in publications:
        pub.citing = citing[pub.pk]
        pub.in_corpus = pub.pk in in_corpus
        pub.my_tags = tags_by_publication[pub.pk]
    ranks = ranks or {}
    top = max(ranks.values(), default=0)
    for pub in publications:
        pub.importance = round(100 * ranks.get(pub.pk, 0) / top) if top else 0


def references_to_identify(user, tag=""):
    """The cited references of the context not linked yet: they do not count."""
    return (
        CitedReference.objects.to_identify()
        .filter(source__in=context_publications(user, tag))
        .count()
    )
