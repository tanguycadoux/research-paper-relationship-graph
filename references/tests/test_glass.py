from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.base import Message
from django.template import Context, Template
from django.test import RequestFactory, TestCase

from references.templatetags.ui import GLASS_CLASSES, POPOVER_PANEL_CLASSES, message_toast
from references.tests.test_navigation import render_navigation


class FrostedGlassTests(TestCase):
    """What floats over the content is frosted glass (CONTRIBUTING, #333)."""

    def test_popovers(self):
        self.assertIn(GLASS_CLASSES, POPOVER_PANEL_CLASSES)
        self.assertNotIn("bg-white ", POPOVER_PANEL_CLASSES)

    def test_menus_of_the_navigation_on_a_small_screen(self):
        user = get_user_model().objects.create_user("ines")
        html = render_navigation("/", user)
        menus = html.split('<details name="navigation"')[1:]
        self.assertEqual(len(menus), 3)
        for menu in menus:
            self.assertIn(f'<ul class="{GLASS_CLASSES} absolute', menu)

    def test_toasts_are_translucent_and_blurred(self):
        for level in (messages.SUCCESS, messages.WARNING, messages.ERROR, messages.INFO):
            with self.subTest(level=level):
                classes = message_toast(Message(level, "Fait."))["classes"]
                self.assertIn("backdrop-blur-md", classes)
                self.assertRegex(classes, r"bg-\w+-50/\d+")

    def test_the_page_renders_a_glass_toast(self):
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        html = Template("{% load ui %}{% message_toast message %}").render(
            Context({"message": Message(messages.SUCCESS, "Ajoutée.")})
        )
        self.assertIn("bg-green-50/80", html)
        self.assertIn("Ajoutée.", html)
