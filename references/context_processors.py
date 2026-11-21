from .services.imports import bibliography_requests, fetch_queue


def fetch_progress(request):
    """
    The toast of the requests in the queue, on every page (#379). The start of the batch
    is kept in the session: once it is over, the next page says how it went, once, with
    or without JavaScript.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    state = fetch_queue.progress(user, since=fetch_queue.followed_batch(request.session))
    if state is not None:
        fetch_queue.follow_batch(request.session, state)
    # The requests of bibliographies say their level in the same toast (#431).
    toast = bibliography_requests.combined_toast(user, state)
    if toast is None:
        return {}
    return {"fetch_progress": {**toast, "since": state.start if state else None}}
