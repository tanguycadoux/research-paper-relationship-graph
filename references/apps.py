from django.apps import AppConfig


class ReferencesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "references"

    def ready(self):
        # Imported for its side effect: connects the post_save receivers.
        from . import signals  # noqa: F401
