"""
The requests « Récupérer les bibliographies » (#431): from a publication, the corpus or a
tag, the bibliographies up to level 2 or 3 (bibliography_levels.py), level by level
through the queue. The imports of a level are requests of the queue without requester:
they pass after those of the pages (fetch_queue.claim_next), and in the same batches
(#381). Once they are over, the worker forms the next level from the references they
identified (advance_all), until the depth asked or the cap of imports.
"""

import logging
from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from ...models import BibliographyItem, BibliographyRequest, FetchRequest, Publication
from ..corpus import tags
from ..display.wording import count
from . import bibliography_levels, fetch_queue
from .fetch_admin import CANCELLED
from .fetch_queue import publication_identifier

logger = logging.getLogger(__name__)
Scope = BibliographyRequest.Scope
Status = BibliographyRequest.Status
Action = FetchRequest.Action


@dataclass
class Start:
    """A starting point: its scope, the publication or the tag, and its publications."""

    scope: str
    publication: Publication | None = None
    tag: str = ""

    @property
    def key(self):
        if self.scope == Scope.PUBLICATION:
            return f"publication:{self.publication.pk}"
        return f"tag:{self.tag}" if self.scope == Scope.TAG else "corpus"

    def label(self):
        """« Mon corpus », « le tag Projet A » or « « Titre » »."""
        if self.scope == Scope.PUBLICATION:
            return f"« {self.publication} »"
        return f"le tag « {tags.label(self.tag)} »" if self.scope == Scope.TAG else "Mon corpus"

    def publication_pks(self, user):
        if self.scope == Scope.PUBLICATION:
            return [self.publication.pk] if self.publication else []
        return list(tags.context_publications(user, self.tag).values_list("pk", flat=True))


def start_of(request):
    """The Start of a BibliographyRequest."""
    return Start(request.scope, request.publication, request.tag)


def running(user, start):
    """The running request of user from start, or None."""
    return BibliographyRequest.objects.filter(
        user=user, start=start.key, status=Status.RUNNING
    ).first()


def ask(user, start, depth):
    """
    Ask for the bibliographies up to depth from start; return the request. A request
    already running from the same start is kept: a deeper depth raises it, so that one
    request only runs for each start.
    """
    with transaction.atomic():
        request = running(user, start)
        if request is None:
            request = create(user, start, depth)
        elif depth > request.depth:
            request.depth = depth
            request.save(update_fields=["depth"])
    advance(request)
    if request.status != Status.RUNNING:
        # Everything was already in the base: the page says it, not the toast.
        BibliographyRequest.objects.filter(pk=request.pk).update(notified=True)
    return request


def create(user, start, depth):
    try:
        with transaction.atomic():
            return BibliographyRequest.objects.create(
                user=user,
                scope=start.scope,
                publication=start.publication,
                tag=start.tag,
                start=start.key,
                depth=depth,
                limit=settings.BIBLIOGRAPHY_REQUEST_LIMIT,
            )
    except IntegrityError:  # the same request, asked twice at once
        return running(user, start)


# The levels, one after the other


def advance_all():
    """
    Advance every running request whose level is over: the worker calls it. A request
    that fails to advance is written in the log; the worker and the others go on.
    """
    for request in BibliographyRequest.objects.filter(status=Status.RUNNING):
        try:
            advance(request)
        except Exception:
            logger.exception("Échec de la demande de bibliographies %s", request.pk)


def advance(request):
    """
    While the level in the queue is over, form the next one, or end the request at its
    depth, or at the level where the cap left publications out. The worker and the page
    that asks may advance the same request at once: one of them only forms each level
    (next_level).
    """
    while request.status == Status.RUNNING and not level_active(request):
        if request.level >= request.depth or request.capped:
            finish(request, Status.DONE)
            return
        if not next_level(request):
            request.refresh_from_db()


def next_level(request):
    """
    Form the level after request.level, items and imports together; False when another
    process formed it, or stopped the request, meanwhile.
    """
    with transaction.atomic():
        claimed = BibliographyRequest.objects.filter(
            pk=request.pk, level=request.level, status=Status.RUNNING
        ).update(level=F("level") + 1)
        if not claimed:
            return False
        request.level += 1
        add_level(request)
        request.save(update_fields=["capped"])
    return True


def level_active(request):
    return request.items.filter(
        level=request.level, fetch_request__status__in=FetchRequest.ACTIVE
    ).exists()


def add_level(request):
    """The items of the next level, the imports among them in the queue, up to the cap."""
    if request.level == 1:
        cited = dict.fromkeys(start_of(request).publication_pks(request.user), 0)
    else:
        cited = bibliography_levels.cited_by(previous_level(request), visited(request))
    missing = bibliography_levels.to_import(cited)
    room = request.limit - imports(request).count()
    wanted = [pk for pk in cited if pk in missing]
    request.capped = len(wanted) > room
    kept = set(wanted[: max(room, 0)])
    fetches = enqueue_imports(kept)
    BibliographyItem.objects.bulk_create(
        BibliographyItem(
            request=request, publication_id=pk, level=request.level, fetch_request=fetches.get(pk)
        )
        for pk in cited
        if pk in kept or pk not in missing
    )


def previous_level(request):
    """The publications of the level before: those of its items, or where they ended."""
    items = request.items.filter(level=request.level - 1)
    pks = set(items.exclude(publication=None).values_list("publication", flat=True))
    ended = items.exclude(fetch_request__publication=None)
    return pks | set(ended.values_list("fetch_request__publication", flat=True))


def visited(request):
    return set(request.items.exclude(publication=None).values_list("publication", flat=True))


def imports(request):
    return request.items.exclude(fetch_request=None)


def enqueue_imports(pks):
    """
    {pk: FetchRequest} importing each publication with its bibliography, without
    requester: a request already active for one is joined (enqueue_action).
    """
    pubs = {pub.pk: pub for pub in Publication.objects.filter(pk__in=pks)}
    identifiers = {publication_identifier(pub): pk for pk, pub in pubs.items()}
    action = Action.IMPORT_WITH_REFERENCES
    FetchRequest.objects.bulk_create(
        (
            FetchRequest(publication=pubs[pk], identifier=identifier, action=action)
            for identifier, pk in identifiers.items()
        ),
        ignore_conflicts=True,
    )
    active = FetchRequest.objects.filter(
        identifier__in=identifiers, action=action, status__in=FetchRequest.ACTIVE
    )
    return {identifiers[fetch.identifier]: fetch for fetch in active}


def finish(request, status):
    """End a running request; False when it had already ended (stopped meanwhile)."""
    now = timezone.now()
    ended = BibliographyRequest.objects.filter(pk=request.pk, status=Status.RUNNING).update(
        status=status, finished_at=now
    )
    if not ended:
        request.refresh_from_db()
        return False
    request.status, request.finished_at = status, now
    return True


def stop(request, user):
    """
    Stop a running request: its pending imports that nothing else waits for are
    cancelled, as on the page of the queue (#382); those running end.
    """
    if not finish(request, Status.STOPPED):
        return False
    others = BibliographyItem.objects.filter(
        request__status=Status.RUNNING, fetch_request__isnull=False
    ).values("fetch_request")
    FetchRequest.objects.filter(
        bibliography_items__request=request, status=FetchRequest.Status.PENDING, requesters=None
    ).exclude(pk__in=others).update(
        status=FetchRequest.Status.FAILED,
        finished_at=timezone.now(),
        error=CANCELLED.format(user=user),
    )
    return True


# Progress, for the toast of the queue and the page of a request


@dataclass
class LevelProgress:
    level: int
    total: int
    done: int
    failed: int


def level_progress(request, level=None):
    """The imports of a level of request (its current one by default): done, failed."""
    level = request.level if level is None else level
    statuses = list(
        imports(request).filter(level=level).values_list("fetch_request__status", flat=True)
    )
    return LevelProgress(
        level=level,
        total=len(statuses),
        done=statuses.count(FetchRequest.Status.DONE),
        failed=statuses.count(FetchRequest.Status.FAILED),
    )


def imported_count(request):
    return imports(request).filter(fetch_request__status=FetchRequest.Status.DONE).count()


def progress_text(request):
    """« Niveau 2 : 34 publications récupérées sur 70. », or how the request ended."""
    if request.status == Status.RUNNING:
        state = level_progress(request)
        text = f"Niveau {state.level} : {count(state.done, 'publication récupérée')}"
        text += f" sur {state.total}"
        if state.failed:
            text += f", {count(state.failed, 'échec')}"
        return text + "."
    imported = count(imported_count(request), "publication récupérée")
    if request.status == Status.STOPPED:
        return f"Récupération des bibliographies arrêtée : {imported}."
    if request.capped:
        cap = count(request.limit, "publication")
        return f"Plafond de {cap} atteint au niveau {request.level} : {imported}."
    return f"Bibliographies récupérées jusqu'au niveau {request.depth} : {imported}."


def toast(user):
    """
    (texts, active): the running requests of user, and those that ended since the last
    toast, which it says once.
    """
    requests = list(
        BibliographyRequest.objects.filter(user=user).exclude(notified=True).order_by("pk")
    )
    texts = [progress_text(request) for request in requests]
    ended = [request.pk for request in requests if request.status != Status.RUNNING]
    BibliographyRequest.objects.filter(pk__in=ended).update(notified=True)
    return texts, len(ended) < len(requests)


def combined_toast(user, state):
    """
    The toast of the queue: the text and activity of the batch of requests of user (a
    fetch_queue.Progress, or None), then those of their requests of bibliographies, and
    whether one of these runs. None when there is nothing to say.
    """
    texts, active = toast(user)
    # The toast links to the requests while one runs: « Arrêter » is there.
    bibliographies = active
    if state is not None:
        texts.insert(0, fetch_queue.progress_text(state))
        active = active or state.active
    if not texts:
        return None
    return {"text": " ".join(texts), "active": active, "bibliographies": bibliographies}


def asked_text(request):
    """What the page says once a request is asked, or raised to a deeper depth."""
    text = (
        f"Récupération des bibliographies de {start_of(request).label()} "
        f"jusqu'au niveau {request.depth} en file."
    )
    if request.status == Status.DONE:
        return f"{progress_text(request)} Tout était déjà en base."
    if not fetch_queue.worker_alive():
        text += " Elle commencera quand le worker de la file tournera."
    return text


def describe(request):
    """A request for the pages: its start, its state in words, and whether it can stop."""
    return {
        "request": request,
        "label": start_of(request).label(),
        "text": progress_text(request),
        "running": request.status == Status.RUNNING,
    }
