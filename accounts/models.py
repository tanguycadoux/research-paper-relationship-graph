from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """
    Project user model. Empty for now: defined from the start so that fields
    (or the login identifier) can be changed later without a painful migration.
    """
