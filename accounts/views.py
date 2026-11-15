from django.contrib import messages
from django.contrib.auth import login
from django.urls import reverse_lazy
from django.views.generic import CreateView

from .forms import RegisterForm


class RegisterView(CreateView):
    """
    A new account, logged in at once and sent to the home page with a welcome (#329):
    a login form right after the registration did not even say the account existed.
    """

    form_class = RegisterForm
    template_name = "registration/register.html"
    success_url = reverse_lazy("index")

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(
            self.request,
            f"Bienvenue, {self.object.username} : votre compte est créé. Ajoutez une "
            "première publication à votre corpus par son DOI, son ISBN ou son identifiant arXiv.",
        )
        return response
