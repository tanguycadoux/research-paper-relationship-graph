"""
The queue of retrievals (#378): adding a publication or importing a file leaves the
requests to the external sources to the fetch_worker command, so that the page answers
at once. Without a worker seen in the last WORKER_TIMEOUT, the request does the work
itself, as before: the development server alone still works.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ...models import FetchRequest, FetchWorker
from ..sources.external_records import has_metadata
from .books import import_queued_book
from .importer import import_publication

logger = logging.getLogger(__name__)

WORKER_TIMEOUT = timedelta(seconds=30)
Action = FetchRequest.Action
Status = FetchRequest.Status


class FetchFailed(Exception):
    """A retrieval that could not be done: its message is kept with the request."""


def worker_alive():
    """Whether a fetch_worker command signalled itself recently."""
    return FetchWorker.objects.filter(seen_at__gte=timezone.now() - WORKER_TIMEOUT).exists()


def signal_alive():
    FetchWorker.objects.update_or_create(pk=1, defaults={"seen_at": timezone.now()})


def signal_stopped():
    """A worker that stops says so: the next requests are synchronous at once."""
    FetchWorker.objects.all().delete()


def needs_fetch(pub):
    """A publication with a DOI is always imported; a book without, only once."""
    return bool(pub.doi) or not has_metadata(pub)


def enqueue(pub, user, *, with_references):
    """
    Put the retrieval of pub in the queue, or join the request already there for the same
    publication and action. Return the request.
    """
    action = Action.IMPORT_WITH_REFERENCES if with_references else Action.IMPORT
    with transaction.atomic():
        request, _ = FetchRequest.objects.get_or_create(
            publication=pub,
            action=action,
            status__in=FetchRequest.ACTIVE,
            defaults={"identifier": pub.doi or pub.isbn, "status": Status.PENDING},
        )
        if user is not None:
            request.requesters.add(user)
    return request


def recover_interrupted():
    """Requests left running by a worker that was stopped go back to the queue."""
    return FetchRequest.objects.filter(status=Status.RUNNING).update(
        status=Status.PENDING, started_at=None
    )


def claim_next():
    """The oldest pending request, now running; None when the queue is empty."""
    while pk := FetchRequest.objects.filter(status=Status.PENDING).values_list("pk").first():
        claimed = FetchRequest.objects.filter(pk=pk[0], status=Status.PENDING).update(
            status=Status.RUNNING, started_at=timezone.now()
        )
        if claimed:
            return FetchRequest.objects.get(pk=pk[0])
    return None


def process(request):
    """Do a request, and keep its outcome: the publication imported, or the error."""
    try:
        pub = fetched(request)
    except FetchFailed as error:
        finish(request, Status.FAILED, error=str(error))
    except Exception as error:  # the error is kept with the request; the worker goes on
        logger.exception("Échec de la demande %s", request.pk)
        finish(request, Status.FAILED, error=f"{type(error).__name__} : {error}")
    else:
        finish(request, Status.DONE, publication=pub)


def fetched(request):
    pub = request.publication
    if pub is None:
        raise FetchFailed("La publication n'existe plus.")
    if not pub.doi:
        pub = import_queued_book(pub)
        if pub is None:
            raise FetchFailed("ISBN inconnu de Crossref et d'Open Library, ou service injoignable.")
        if not pub.doi:
            return pub
    imported = import_publication(
        pub, with_references=request.action == Action.IMPORT_WITH_REFERENCES
    )
    if imported is None:
        raise FetchFailed("DOI inconnu de Crossref et de DataCite, ou service injoignable.")
    return imported


def finish(request, status, *, error="", publication=None):
    """
    Update by pk: the request may have lost its publication meanwhile (a preprint
    merged into its published version), and must not be saved again with it.
    """
    changes = {"status": status, "finished_at": timezone.now(), "error": error}
    if publication is not None:
        changes["publication"] = publication
    FetchRequest.objects.filter(pk=request.pk).update(**changes)
