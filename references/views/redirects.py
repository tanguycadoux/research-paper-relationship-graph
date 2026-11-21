"""
Back to the page that sent a form (#295): its `next` field, if it is a page of this
site, else a fallback.
"""

from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme


def safe_next(request, next_url):
    """next_url if it is a page of this site, else ""."""
    allowed = url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()})
    return next_url if next_url and allowed else ""


def redirect_to_next(request, fallback, **kwargs):
    """Redirect to the POST `next` field, or to the view fallback (with kwargs)."""
    next_url = safe_next(request, request.POST.get("next", ""))
    return redirect(next_url) if next_url else redirect(fallback, **kwargs)
