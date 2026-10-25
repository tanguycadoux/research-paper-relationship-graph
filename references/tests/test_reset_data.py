from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from references.models import Author, CitedReference, Publication, Tag, UserPublication


@override_settings(DEBUG=True)
class ResetDataTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alice")
        pub = Publication.objects.create(doi="10.1000/a", title="A")
        CitedReference.objects.create(source=pub, position=0)
        Author.objects.create(first_name="Ada", last_name="Lovelace")
        UserPublication.objects.create(user=self.user, publication=pub)
        Tag.objects.create(user=self.user, name="Projet")

    def reset(self, *args, answer=None):
        out = StringIO()
        with patch("builtins.input", return_value=answer) as asked:
            call_command("reset_data", *args, stdout=out)
        return out.getvalue(), asked

    def assert_data_left(self, left):
        for model in (Publication, CitedReference, Author, UserPublication, Tag):
            self.assertEqual(model.objects.exists(), left, model.__name__)

    def test_everything_but_the_accounts_is_deleted(self):
        output, _ = self.reset(answer="oui")
        self.assert_data_left(False)
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertIn("Publication : 1", output)

    def test_any_other_answer_deletes_nothing(self):
        output, _ = self.reset(answer="o")
        self.assert_data_left(True)
        self.assertIn("rien n'a été effacé", output)

    def test_no_input_skips_the_confirmation(self):
        _, asked = self.reset("--no-input")
        asked.assert_not_called()
        self.assert_data_left(False)

    @override_settings(DEBUG=False)
    def test_refused_outside_debug(self):
        with self.assertRaises(CommandError):
            self.reset("--no-input")
        self.assert_data_left(True)
