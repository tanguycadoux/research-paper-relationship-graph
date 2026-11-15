from .services.sources.api_log import api_context


class ApiLogContextMiddleware:
    """The requests to the external APIs made for a page say which one (#395)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        user_id = user.pk if user is not None and user.is_authenticated else None
        label = f"{request.method} {request.path}"
        with api_context("page", label, user=user_id):
            return self.get_response(request)
