"""
Interface components: {% load ui %}, then

    {% button "Fusionner" %}
    {% button "Supprimer" variant="danger" icon="delete" %}
    {% button "Fermer" icon="close" icon_only=True type="button" %}
    {% button "Se déconnecter" icon="logout" compact=True %}   (icon only on a small screen)
    {% button "Voir la fiche" url=… variant="secondary" %}   (a link: <a href>)
    {% badge "12 à identifier" variant="warning" %}
    {% tag_indent item.depth nested=True %}   (the padding of a tag in a tree of tags)
    {% alert "Import terminé." variant="success" %}
    {% card title="Informations" %}…{% endcard %}
    {% icon "delete" class="size-5" %}
    {% external_link "https://doi.org/"|add:pub.doi pub.doi class="break-all" %}
    {% pagination page_obj %}   (below a list in pages, its URL parameters kept)
    {% column_header "Année" "year" %}   (a <th>, sortable and filterable if the view says so)
    {% filter_summary %}   (the active filters of the table, each removable)
    publication{{ n|pluralize_fr }}   (pluralize, 0 and 1 in the singular, #411)

One library, split by subject (#297): components (button, badge, alert, card, tag_indent),
icons (icon, external_link), glass (popovers, toasts), tables (pagination, column
headers, sort and filters), forms (field, form_errors) and text (pluralize_fr).
The Tailwind classes of each variant are written in full in these modules, once:
Tailwind finds them by scanning them.
"""

from . import components, forms, glass, icons, tables, text
from .components import BADGE_VARIANTS, BUTTON_VARIANTS
from .glass import GLASS_CLASSES, POPOVER_PANEL_CLASSES, TOAST_VARIANTS, message_toast
from .library import register
from .tables import page_url

__all__ = [
    "BADGE_VARIANTS",
    "BUTTON_VARIANTS",
    "GLASS_CLASSES",
    "POPOVER_PANEL_CLASSES",
    "TOAST_VARIANTS",
    "components",
    "forms",
    "glass",
    "icons",
    "message_toast",
    "page_url",
    "register",
    "tables",
    "text",
]
