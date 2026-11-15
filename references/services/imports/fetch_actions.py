"""
What the fetch_worker command does for each action of the queue (#378, #380). A handler
returns the publication the request ends on (None when it is about something else), or
raises FetchFailed with what the page of the queue says.
"""

from ...models import FetchRequest, MetadataConflict
from .books import import_queued_book
from .importer import import_publication

Action = FetchRequest.Action


class FetchFailed(Exception):
    """A retrieval that could not be done: its message is kept with the request."""


def run(request):
    return HANDLERS[request.action](request)


def publication_of(request):
    if request.publication is None:
        raise FetchFailed("La publication n'existe plus.")
    return request.publication


def imported(request):
    """Import a publication added to a corpus (#378): its book first, without DOI."""
    pub = publication_of(request)
    if not pub.doi:
        pub = import_queued_book(pub)
        if pub is None:
            raise FetchFailed("ISBN inconnu de Crossref et d'Open Library, ou service injoignable.")
        if not pub.doi:
            return pub
    result = import_publication(
        pub, with_references=request.action == Action.IMPORT_WITH_REFERENCES
    )
    if result is None:
        raise FetchFailed("DOI inconnu de Crossref et de DataCite, ou service injoignable.")
    return result


def refreshed(request):
    """« Rafraîchir les métadonnées »: the sources asked again."""
    pub = publication_of(request)
    result = import_publication(pub, with_references=pub.parse_references, force_fetch=True)
    if result is None:
        raise FetchFailed("Les sources n'ont pas répondu, ou ne connaissent pas cet identifiant.")
    return result


def citing_works(request):
    """The works that cite a publication according to OpenAlex (#163)."""
    from ..discovery import incoming_citations

    pub = publication_of(request)
    try:
        incoming_citations.fetch(pub)
    except incoming_citations.IncomingCitationsError as error:
        raise FetchFailed(str(error)) from error
    return pub


def published_version(request):
    """The preprint replaced by its published version (#227), as its requester decided."""
    from .published_versions import accept_published_version

    pub = publication_of(request)
    conflict = MetadataConflict.objects.filter(
        kind=MetadataConflict.Kind.PUBLISHED_VERSION,
        publication=pub,
        status=MetadataConflict.Status.OPEN,
        proposed_value=request.identifier,
    ).first()
    if conflict is None:
        raise FetchFailed("Cette version publiée n'est plus proposée : rien n'a changé.")
    result = accept_published_version(conflict, request.requesters.first())
    if result is None:
        raise FetchFailed("Crossref n'a pas répondu : rien n'a changé, réessayez plus tard.")
    return import_publication(result, with_references=result.parse_references) or result


def orcid_profile(request):
    """The public ORCID record of an author, asked from their page (#59)."""
    from .orcid_profile import refresh_orcid_record

    author = request.author
    if author is None or not author.orcid:
        raise FetchFailed("L'auteur n'existe plus, ou n'a plus d'ORCID.")
    if not refresh_orcid_record(author):
        raise FetchFailed("ORCID n'a pas répondu ou ne connaît pas cet identifiant.")


def graph_image(request):
    """The image of a graph too large for the page (#328): its kind is the identifier."""
    from ..display import graph_images

    image = graph_images.generate(request.identifier)
    if image.status == image.Status.FAILED:
        raise FetchFailed(image.error)


HANDLERS = {
    Action.IMPORT: imported,
    Action.IMPORT_WITH_REFERENCES: imported,
    Action.REFRESH: refreshed,
    Action.INCOMING_CITATIONS: citing_works,
    Action.PUBLISHED_VERSION: published_version,
    Action.ORCID_PROFILE: orcid_profile,
    Action.GRAPH_IMAGE: graph_image,
}
