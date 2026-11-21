"""
The context of the page of a publication, section by section (#297): its corpus entry,
its description, its authors, its references, the publications that cite it, and the bars
of bulk actions. The view adds it to its own, with the form of the note.
"""

from ...models import CitedReference, Publication, UserPublication
from ..corpus import tags
from ..corrections.identification import is_to_identify
from ..discovery import incoming_citations
from ..imports import fetch_queue
from ..imports.jacow import is_jacow
from ..imports.organizations import numbered_affiliations
from ..imports.preprints import BIBLIOGRAPHY_NOT_FETCHED, arxiv_bibliography
from ..imports.published_versions import proposal_message
from ..sources.external_records import metadata_status
from .citations import publication_citations
from .open_access import open_access_link
from .publication_details import crossref_details, publication_abstract
from .publication_table import corpus_ids, for_publication_table, references_available

# Long lists folded (#269): a LIGO article has 1 012 authors, « Hallmarks of Cancer »
# 247 references; the page was 9 000 to 13 600 px high.
AUTHORS_SHOWN = 20
REFERENCES_SHOWN = 100


def page_context(request, pub):
    """Everything the page of a publication shows, for the user of the request."""
    cited_references = pub.cited_references.select_related("target")
    context = queue_context(request, pub) | corpus_context(request.user, pub)
    context |= references_context(request.user, pub, cited_references)
    context |= citing_context(pub)
    context |= incoming_citations_context(request, pub)
    context |= status_context(pub)
    context |= description_context(pub)
    context |= long_lists_context(request, pub, cited_references)
    context |= bulk_actions_context(request, cited_references)
    return context


def queue_context(request, pub):
    """Its data still to come from the queue: the page says so, and reloads once done (#379)."""
    if request.user.is_authenticated and fetch_queue.publication_pending(pub):
        return {"fetch_pending_publication": pub.pk}
    return {}


def corpus_context(user, pub):
    """The publications of the user's corpus, and the entry of this one if it is part of it."""
    user_pub_ids = corpus_ids(user)
    context = {"user_pub_ids": user_pub_ids, "belongs_to_user": pub.pk in user_pub_ids}
    if not context["belongs_to_user"]:
        return context
    entry = UserPublication.objects.get(user=user, publication=pub)
    return context | {
        "corpus_entry": entry,
        "reading_status": entry.reading_status,
        "reading_statuses": UserPublication.ReadingStatus.choices,
        "entry_tags": entry.tags.all(),
        "known_tags": tags.suggested_paths(user),
    }


def references_context(user, pub, cited_references):
    """Its bibliography: what can be imported, and how many references wait for the user."""
    available = references_available(pub)
    bibliography = arxiv_bibliography(pub)
    to_identify = [ref for ref in cited_references if is_to_identify(ref)]
    return {
        "cited_references": cited_references,
        "references_available": available,
        "arxiv_bibliography": bibliography,
        # The bibliography of a preprint is fetched by the same action (#227).
        "can_import_references": (
            user.is_authenticated
            and not cited_references
            and (available or bibliography == BIBLIOGRAPHY_NOT_FETCHED)
        ),
        "references_to_identify": len(to_identify),
        # Those the source does not describe: the article alone says what they are (#273).
        "references_undescribed": sum(1 for ref in to_identify if not ref.is_described),
        # Start of « Identifier en série » (#242).
        "first_to_identify": min(to_identify, key=lambda ref: ref.position, default=None),
        "references_unidentifiable": sum(1 for ref in cited_references if ref.unidentifiable),
    }


def citing_context(pub):
    """Only publications whose bibliography was imported (those of a corpus) can cite it."""
    citing = Publication.objects.filter(
        pk__in=CitedReference.objects.filter(target=pub).values("source")
    )
    return {
        "citing_publications": for_publication_table(citing).order_by(
            "-publication_date", "readable_title"
        )
    }


def incoming_citations_context(request, pub):
    """Beyond the base, according to OpenAlex, once someone asked (#163)."""
    citations = getattr(pub, "incoming_citations", None)
    order = request.GET.get("citants", "")
    order = order if order in incoming_citations.ORDERS else "citees"
    return {
        "incoming_citations": citations,
        "citing_order": order,
        "citing_orders": incoming_citations.ORDERS,
        "citing_works": (
            incoming_citations.citing_works(citations, request.user, order) if citations else []
        ),
    }


def status_context(pub):
    """What the page warns about: missing metadata, a published version, the author order."""
    return {
        "metadata_status": metadata_status(pub),
        "version_proposal": proposal_message(pub),
        "uncertain_author_order": is_jacow(pub.doi),
    }


def description_context(pub):
    """What the page shows of the publication itself, read from the stored responses."""
    return {
        "details": crossref_details(pub),
        "abstract": publication_abstract(pub),
        "citations": publication_citations(pub),
        "open_access": open_access_link(pub),
    }


def long_lists_context(request, pub, cited_references):
    """
    The authors (the first 20 and the last one, with the affiliations of these only)
    and the references (the first 100) shown, unless ?auteurs=tous or
    ?references=toutes asks for all of them; and the links that unfold them.
    """
    slots = list(
        pub.authorpublication_set.select_related("author")
        .prefetch_related("organizations__ancestors")
        .order_by("order")
    )
    all_authors = request.GET.get("auteurs") == "tous" or len(slots) <= AUTHORS_SHOWN + 1
    shown = slots if all_authors else [*slots[:AUTHORS_SHOWN], slots[-1]]
    all_references = request.GET.get("references") == "toutes"
    references = list(cited_references)
    return {
        "authors": numbered_affiliations(shown),
        "author_total": len(slots),
        "authors_hidden": len(slots) - len(shown),
        "authors_shown": AUTHORS_SHOWN,
        "all_authors_url": query_with(request, auteurs="tous") + "#authors-title",
        "shown_references": references if all_references else references[:REFERENCES_SHOWN],
        "references_hidden": 0 if all_references else max(len(references) - REFERENCES_SHOWN, 0),
        "all_references_url": query_with(request, references="toutes") + "#references-title",
    }


def query_with(request, **params):
    query = request.GET.copy()
    for key, value in params.items():
        query[key] = value
    return f"?{query.urlencode()}"


def bulk_actions_context(request, cited_references):
    """
    The bars of bulk actions of the references and « Cité par » (#408), for a user
    signed in: only identified references can be checked, so their bar needs one.
    """
    if not request.user.is_authenticated:
        return {}
    return {
        "references_checkable": any(ref.target_id for ref in cited_references),
        "reading_statuses": UserPublication.ReadingStatus.choices,
        "tag_max_length": tags.MAX_LENGTH,
        "bulk_tags": tags.suggested_paths(request.user),
    }
