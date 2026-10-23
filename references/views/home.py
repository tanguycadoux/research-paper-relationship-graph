from django.shortcuts import render

from ..services import dashboard


def index(request):
    """A dashboard for a logged-in user, a presentation for a visitor (#151)."""
    context = {"base": dashboard.base_figures()}
    if request.user.is_authenticated:
        context["corpus"] = dashboard.corpus_figures(request.user)
        context["to_do"] = dashboard.to_do(request.user)
    return render(request, "references/index.html", context)
