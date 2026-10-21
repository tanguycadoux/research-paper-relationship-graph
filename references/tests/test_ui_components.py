from unittest.mock import Mock, patch

from django.core.management import CommandError, call_command
from django.template import Context, Template, TemplateSyntaxError
from django.test import SimpleTestCase

from references.services import icons
from references.templatetags.ui import (
    BADGE_VARIANTS,
    BUTTON_VARIANTS,
)


def render(source, **context):
    return Template("{% load ui %}" + source).render(Context(context))


class IconTests(SimpleTestCase):
    def test_icon_is_inlined_and_hidden_from_screen_readers(self):
        html = render('{% icon "delete" %}')
        self.assertIn('viewBox="0 -960 960 960"', html)
        self.assertIn('aria-hidden="true"', html)
        self.assertIn('fill="currentColor"', html)
        self.assertIn("<path d=", html)

    def test_class_replaces_the_default_size(self):
        self.assertIn(
            'class="size-6 text-red-700"', render('{% icon "delete" class="size-6 text-red-700" %}')
        )

    def test_missing_icon_tells_how_to_add_it(self):
        with self.assertRaisesMessage(
            TemplateSyntaxError, "python manage.py add_icon no_such_icon"
        ):
            render('{% icon "no_such_icon" %}')

    def test_names_cannot_leave_the_icons_folder(self):
        with self.assertRaises(TemplateSyntaxError):
            render('{% icon "../templates/base" %}')


class ButtonTests(SimpleTestCase):
    def test_every_variant_renders(self):
        for variant, classes in BUTTON_VARIANTS.items():
            with self.subTest(variant=variant):
                html = render('{% button "Fusionner" variant=v %}', v=variant)
                self.assertIn('<button type="submit"', html)
                self.assertIn(classes, html)
                self.assertIn("Fusionner", html)

    def test_default_variant_is_primary(self):
        self.assertIn(BUTTON_VARIANTS["primary"], render('{% button "Fusionner" %}'))

    def test_icon_with_label(self):
        html = render('{% button "Supprimer" variant="danger" icon="delete" %}')
        self.assertIn("<svg", html)
        self.assertIn("Supprimer", html)
        self.assertNotIn("aria-label", html)

    def test_icon_only_button_keeps_an_accessible_label(self):
        html = render('{% button "Fermer" icon="close" icon_only=True type="button" %}')
        self.assertIn('type="button"', html)
        self.assertIn('aria-label="Fermer"', html)
        self.assertNotIn(">\n    Fermer", html)

    def test_formaction_name_and_value(self):
        html = render('{% button "Garder" formaction="/x/" name="choice" value="keep" %}')
        self.assertIn('formaction="/x/"', html)
        self.assertIn('name="choice" value="keep"', html)

    def test_label_is_escaped(self):
        self.assertIn("&lt;b&gt;", render("{% button label %}", label="<b>"))

    def test_mistakes_are_reported(self):
        for source in (
            '{% button "X" variant="rouge" %}',
            '{% button "" %}',
            '{% button "X" icon_only=True %}',
            '{% button "X" colour="red" %}',
            '{% button "X" url="/a/" type="button" %}',
            '{% button "X" url="/a/" formaction="/b/" %}',
        ):
            with self.subTest(source=source), self.assertRaises(TemplateSyntaxError):
                render(source)

    def test_with_a_url_the_button_is_a_link(self):
        html = render('{% button "Voir la fiche" url="/authors/1/" variant="secondary" %}')
        self.assertIn('<a href="/authors/1/"', html)
        self.assertIn(BUTTON_VARIANTS["secondary"], html)
        self.assertNotIn("<button", html)

    def test_icon_only_link_keeps_an_accessible_label(self):
        html = render('{% button "Modifier" url="/x/" icon="edit" icon_only=True %}')
        self.assertIn('aria-label="Modifier"', html)


class OtherComponentsTests(SimpleTestCase):
    def test_badge_variants(self):
        for variant, classes in BADGE_VARIANTS.items():
            with self.subTest(variant=variant):
                html = render('{% badge "12 à identifier" variant=v %}', v=variant)
                self.assertIn('<span class="', html)
                self.assertIn(classes, html)

    def test_alert_role_depends_on_the_variant(self):
        self.assertIn('role="alert"', render('{% alert "Échec" variant="danger" %}'))
        html = render('{% alert "Import terminé." variant="success" %}')
        self.assertIn('role="status"', html)
        self.assertIn("<svg", html)

    def test_card_wraps_its_content_under_a_heading(self):
        html = render(
            '{% card title="Informations" level=3 %}<p>{{ text }}</p>{% endcard %}', text="<i>"
        )
        self.assertIn('<section class="', html)
        self.assertIn(">Informations</h3>", html)
        self.assertIn("<p>&lt;i&gt;</p>", html)

    def test_card_heading_level_stays_below_the_page_title(self):
        with self.assertRaises(TemplateSyntaxError):
            render('{% card title="X" level=1 %}{% endcard %}')


class AddIconCommandTests(SimpleTestCase):
    def setUp(self):
        self.addCleanup(icons.icon_parts.cache_clear)

    def test_downloads_the_svg(self):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960"><path d="M0"/></svg>'
        )
        with (
            patch.object(icons, "ICONS_DIR") as folder,
            patch.object(
                icons.requests, "get", return_value=Mock(status_code=200, text=svg)
            ) as get,
        ):
            call_command("add_icon", "star", stdout=Mock())
        self.assertIn("/star/materialsymbolsoutlined/star_24px.svg", get.call_args.args[0])
        folder.__truediv__.return_value.write_text.assert_called_once_with(svg, encoding="utf-8")

    def test_unknown_icon(self):
        with (
            patch.object(icons.requests, "get", return_value=Mock(status_code=404)),
            self.assertRaisesMessage(CommandError, "inconnue"),
        ):
            call_command("add_icon", "no_such_icon")

    def test_invalid_name_is_refused_before_any_request(self):
        with patch.object(icons.requests, "get") as get, self.assertRaises(CommandError):
            call_command("add_icon", "../x")
        get.assert_not_called()
