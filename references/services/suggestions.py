"""
Suggestions by co-citation (#162): the publications that several publications of a
context cite, the context being the corpus of a user or one of their tags with its
descendants. If four of my articles cite the same one, it is likely central to my
subject. Computed from the base alone, on the identified references only.

In a tag, a suggestion may already be in the corpus under another tag: it stays,
marked, so that an article of the subject is not missed (it may lack the tag).
"""

from collections import defaultdict

from django.db.models import Count

from ..models import CitedReference, Publication
from . import tags
from .publication_table import corpus_ids, with_first_author

MIN_CITING = 2


def context_publications(user, tag=""):
    """The publications of the user's corpus, or only those with the tag or a descendant."""
    if tag:
        return Publication.objects.filter(tags.tagged(user, tag))
    return Publication.objects.filter(userpublication__user=user)


def co_cited(user, tag=""):
    """
    The publications outside the context cited by at least MIN_CITING of its
    publications, the most cited first, annotated with citing_count.
    """
    sources = context_publications(user, tag).values("pk")
    # The count follows the filter: only the citations from the context are counted.
    suggestions = (
        Publication.objects.filter(citations__source__in=sources)
        .exclude(pk__in=sources)
        .annotate(citing_count=Count("citations__source", distinct=True))
        .filter(citing_count__gte=MIN_CITING)
    )
    return with_first_author(suggestions).order_by(
        "-citing_count", "-publication_date", "title", "pk"
    )


def describe(user, publications, tag=""):
    """
    Set on each suggestion of a page: citing, the publications of the context that
    cite it, newest first; in_corpus and my_tags, when it is already in the corpus.
    """
    citing = defaultdict(list)
    refs = (
        CitedReference.objects.filter(
            target__in=publications, source__in=context_publications(user, tag)
        )
        .select_related("source")
        .order_by("-source__publication_date", "source__title", "source_id")
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


def references_to_identify(user, tag=""):
    """The cited references of the context not linked yet: they do not count."""
    return CitedReference.objects.filter(
        source__in=context_publications(user, tag), target__isnull=True, unidentifiable=False
    ).count()
