from django.apps import AppConfig
from django.db.backends.signals import connection_created


class ReferencesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "references"

    def ready(self):
        from .services.search import register_functions

        # normalized() in SQL, for the search (#153).
        connection_created.connect(register_functions, dispatch_uid="search_functions")
