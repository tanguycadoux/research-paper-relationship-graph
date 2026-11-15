from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime

from ..models import FetchRequest
from ..services.imports import fetch_queue


@login_required
def fetch_progress(request):
    """
    The state of the requests of the user, which the toast asks every few seconds (#379);
    with ?publication=, whether the data of that publication is still to come.
    """
    data = {"active": False, "text": ""}
    reloads = False
    # The page of a publication or of an author whose data is still to come (#379, #380).
    for target in ("publication", "author"):
        pk = request.GET.get(target, "")
        if pk.isdigit():
            data[f"{target}_pending"] = FetchRequest.objects.filter(
                **{f"{target}_id": int(pk)}, status__in=FetchRequest.ACTIVE
            ).exists()
            reloads = not data[f"{target}_pending"]
    since = parse_datetime(request.GET.get("since", "")) or fetch_queue.followed_batch(
        request.session
    )
    state = fetch_queue.progress(request.user, since=since)
    if state is not None:
        # The toast says how it went, and the next page need not say it again; unless
        # this page reloads now: it says it then.
        if not reloads:
            fetch_queue.follow_batch(request.session, state)
        data.update(
            active=state.active,
            text=fetch_queue.progress_text(state),
            since=state.start.isoformat(),
        )
    return JsonResponse(data)
