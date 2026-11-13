"""
Material Symbols icons (Outlined, 24 px), stored as SVG files in static/icons/ and
inlined in the pages: no web font, so they work offline and never show their name
while loading.
"""

import re
from functools import cache
from pathlib import Path

import requests
from django.conf import settings

ICONS_DIR = Path(settings.BASE_DIR) / "static" / "icons"
SOURCE_URL = (
    "https://raw.githubusercontent.com/google/material-design-icons/master/symbols/web/"
    "{name}/materialsymbolsoutlined/{name}_24px.svg"
)
NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")
SVG_PATTERN = re.compile(r'<svg[^>]*viewBox="([^"]+)"[^>]*>(.*)</svg>', re.DOTALL)


class UnknownIcon(LookupError):
    pass


@cache
def icon_parts(name):
    """(viewBox, inner markup) of a stored icon."""
    path = ICONS_DIR / f"{name}.svg"
    if not NAME_PATTERN.match(name) or not path.exists():
        raise UnknownIcon(
            f"Icône inconnue : {name!r}. Ajoutez-la avec `python manage.py add_icon {name}`."
        )
    match = SVG_PATTERN.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise UnknownIcon(f"{path} n'est pas un SVG Material Symbols.")
    return match.groups()


def download_icon(name):
    """Download an icon from Google's repository into static/icons/. Return its path."""
    if not NAME_PATTERN.match(name):
        raise UnknownIcon(f"Nom d'icône invalide : {name!r} (minuscules, chiffres et _).")
    response = requests.get(SOURCE_URL.format(name=name), timeout=10)
    if response.status_code == 404:
        raise UnknownIcon(f"Icône inconnue de Material Symbols : {name!r}.")
    response.raise_for_status()
    if not SVG_PATTERN.search(response.text):
        raise UnknownIcon(f"La réponse pour {name!r} n'est pas un SVG.")
    path = ICONS_DIR / f"{name}.svg"
    path.write_text(response.text, encoding="utf-8")
    icon_parts.cache_clear()
    return path
