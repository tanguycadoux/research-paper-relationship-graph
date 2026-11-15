"""
The administration of the queue of retrievals (#382): what waits, runs, was done or
failed, the state of the worker, and the two corrections an administrator may make,
retrying a failed request and cancelling a pending one.
"""

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone

from ...models import FetchRequest, FetchWorker
from . import fetch_queue

Status = FetchRequest.Status
# The requests done, and the failed ones, shown on the page: the most recent.
RECENT = 50


@dataclass
class QueueOverview:
    pending: list
    running: list
    done: list
    failed: list
    # For each action waited for: action, count, and « Importer : 3 ».
    pending_by_action: list
    worker_seen_at: object
    worker_alive: bool

    @property
    def stalled(self):
        """Requests wait, but no worker takes them: they wait for a page that does them."""
        return bool(self.pending) and not self.worker_alive


def requests_with(status):
    return (
        FetchRequest.objects.filter(status=status)
        .select_related("publication")
        .prefetch_related("requesters")
    )


def overview():
    """The state of the queue, for the administration page."""
    worker = FetchWorker.objects.order_by("-seen_at").first()
    return QueueOverview(
        pending=list(requests_with(Status.PENDING)),
        running=list(requests_with(Status.RUNNING)),
        done=list(requests_with(Status.DONE).order_by("-finished_at", "-pk")[:RECENT]),
        failed=list(requests_with(Status.FAILED).order_by("-finished_at", "-pk")[:RECENT]),
        pending_by_action=pending_by_action(),
        worker_seen_at=worker.seen_at if worker else None,
        worker_alive=fetch_queue.worker_alive(),
    )


def pending_by_action():
    labels = dict(FetchRequest.Action.choices)
    counts = (
        FetchRequest.objects.filter(status=Status.PENDING)
        .values_list("action")
        .annotate(Count("pk"))
        .order_by("action")
    )
    return [
        {"action": action, "count": number, "text": f"{labels.get(action, action)} : {number}"}
        for action, number in counts
    ]


class NotRetried(Exception):
    """A request that cannot go back to the queue: the message says why."""


def active_twin(request):
    """The active request for the same publication (or identifier) and action, if any."""
    twins = FetchRequest.objects.filter(action=request.action, status__in=FetchRequest.ACTIVE)
    if request.publication_id is not None:
        twins = twins.filter(publication_id=request.publication_id)
    else:
        twins = twins.filter(publication=None, identifier=request.identifier)
    return twins.exclude(pk=request.pk).first()


def retry(request):
    """
    Put a failed request back in the queue, at its end. Refused when an active request
    already does the same work: one active request per publication and action.
    """
    if request.status != Status.FAILED:
        raise NotRetried("Seule une demande échouée peut être relancée.")
    if active_twin(request) is not None:
        raise NotRetried(
            "Une demande identique est déjà en file : celle-ci n'est pas relancée en double."
        )
    try:
        with transaction.atomic():
            updated = FetchRequest.objects.filter(pk=request.pk, status=Status.FAILED).update(
                status=Status.PENDING,
                requested_at=timezone.now(),
                started_at=None,
                finished_at=None,
                error="",
            )
    except IntegrityError as error:  # a twin entered the queue meanwhile
        raise NotRetried(
            "Une demande identique est déjà en file : celle-ci n'est pas relancée en double."
        ) from error
    if not updated:
        raise NotRetried("Cette demande a changé entre-temps : rechargez la page.")


CANCELLED = "Annulée par {user}."


def cancel(request, user):
    """
    Take a pending request out of the queue. It is kept as failed, with who cancelled it,
    so that its requesters see what became of it and it can be retried.
    """
    return bool(
        FetchRequest.objects.filter(pk=request.pk, status=Status.PENDING).update(
            status=Status.FAILED,
            finished_at=timezone.now(),
            error=CANCELLED.format(user=user),
        )
    )
