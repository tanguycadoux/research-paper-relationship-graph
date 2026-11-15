"""
The queue of retrievals (#378): adding a publication or importing a file, and the other
long actions (#380), leave the requests to the external sources to the fetch_worker
command, so that the page answers at once. Without a worker seen in the last
WORKER_TIMEOUT, the request does the work itself, as before: the development server
alone still works. What the worker does for each action: fetch_actions.py.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ...models import FetchRequest, FetchWorker
from ..display.wording import count
from ..sources.external_records import has_metadata
from . import fetch_actions
from .fetch_actions import FetchFailed

logger = logging.getLogger(__name__)

WORKER_TIMEOUT = timedelta(seconds=30)
Action = FetchRequest.Action
Status = FetchRequest.Status
# The actions about a publication of a corpus: those the toast counts (#379).
PUBLICATION_ACTIONS = (
    Action.IMPORT,
    Action.IMPORT_WITH_REFERENCES,
    Action.REFRESH,
    Action.PUBLISHED_VERSION,
)


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
    """Put the import of pub in the queue (#378); return the request."""
    action = Action.IMPORT_WITH_REFERENCES if with_references else Action.IMPORT
    return enqueue_action(action, user, publication=pub)


def enqueue_action(action, user, *, publication=None, author=None, identifier=""):
    """
    Put an action in the queue, or join the request already there for the same identifier
    and action (#380). The identifier defaults to that of the publication. Return the
    request.
    """
    identifier = identifier or publication_identifier(publication)
    with transaction.atomic():
        request, _ = FetchRequest.objects.get_or_create(
            identifier=identifier,
            action=action,
            status__in=FetchRequest.ACTIVE,
            defaults={"publication": publication, "author": author, "status": Status.PENDING},
        )
        if user is not None and user.is_authenticated:
            request.requesters.add(user)
    return request


def publication_identifier(pub):
    """Its DOI or ISBN; its pk without either, so that two never share a request."""
    return pub.doi or pub.isbn or f"publication:{pub.pk}"


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
    return fetch_actions.run(request)


def finish(request, status, *, error="", publication=None):
    """
    Update by pk: the request may have lost its publication meanwhile (a preprint
    merged into its published version), and must not be saved again with it.
    """
    changes = {"status": status, "finished_at": timezone.now(), "error": error}
    if publication is not None:
        changes["publication"] = publication
    FetchRequest.objects.filter(pk=request.pk).update(**changes)


# Progress of the requests of a user (#379)


@dataclass
class Progress:
    """The requests of a user since the oldest still active: a batch, for the toast."""

    start: datetime
    total: int
    done: int
    failed: int
    # Active requests of other users that pass before the first active one of the user.
    ahead: int
    active: bool
    # Publications whose request is still pending or running.
    publications: set = field(default_factory=set)


def progress(user, since=None):
    """
    The Progress of the requests of user, or None without any active. since is the start
    of the batch the page follows: kept while its first requests are done, and once none
    is active, it still gives its outcome.
    """
    mine = FetchRequest.objects.filter(requesters=user, action__in=PUBLICATION_ACTIONS)
    active = mine.filter(status__in=FetchRequest.ACTIVE).order_by("requested_at", "pk")
    first = active.first()
    if first is not None and since is not None and over_before(mine, since, first):
        since = None
    if first is None and since is None:
        return None
    # The batch followed keeps its start while its first requests are done.
    start = min(filter(None, (first and first.requested_at, since)))
    statuses = Counter(mine.filter(requested_at__gte=start).values_list("status", flat=True))
    return Progress(
        start=start,
        total=sum(statuses.values()),
        done=statuses[Status.DONE],
        failed=statuses[Status.FAILED],
        ahead=requests_ahead(first, user) if first else 0,
        active=first is not None,
        publications=set(active.values_list("publication_id", flat=True)),
    )


def over_before(mine, since, first):
    """Whether the batch started at since was over before first was asked: another batch."""
    earlier = mine.filter(requested_at__gte=since, requested_at__lt=first.requested_at)
    return not earlier.filter(
        Q(status__in=FetchRequest.ACTIVE) | Q(finished_at__gte=first.requested_at)
    ).exists()


def requests_ahead(request, user):
    before = Q(requested_at__lt=request.requested_at) | Q(
        requested_at=request.requested_at, pk__lt=request.pk
    )
    return (
        FetchRequest.objects.filter(before, status__in=FetchRequest.ACTIVE)
        .exclude(requesters=user)
        .count()
    )


def progress_text(state):
    """« 3 publications récupérées sur 12 · 2 demandes avant les vôtres »."""
    if not state.active:
        text = f"Récupération terminée : {count(state.done, 'publication récupérée')}"
    else:
        text = f"{count(state.done, 'publication récupérée')} sur {state.total}"
    if state.failed:
        text += f", {count(state.failed, 'échec')}"
    if state.active and state.ahead:
        text += f" · {count(state.ahead, 'demande')} avant les vôtres"
    return text + "."


SESSION_KEY = "fetch_batch"


def followed_batch(session):
    """The start of the batch the pages of this session follow, or None."""
    return parse_datetime(session.get(SESSION_KEY, "")) if SESSION_KEY in session else None


def follow_batch(session, state):
    """Remember an active batch; forget one that is over, once its outcome is shown."""
    if state.active:
        session[SESSION_KEY] = state.start.isoformat()
    else:
        session.pop(SESSION_KEY, None)


def publication_pending(pub):
    """Whether the data of pub is still to come from the queue (its page says so)."""
    return pub.fetch_requests.filter(status__in=FetchRequest.ACTIVE).exists()


def author_pending(author):
    """Whether the ORCID profile of author is still to come from the queue (#380)."""
    return author.fetch_requests.filter(status__in=FetchRequest.ACTIVE).exists()
