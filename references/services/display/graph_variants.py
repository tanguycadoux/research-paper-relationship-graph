"""
Variants of a citation graph chosen in the URL (#195, after #288): the page draws the
graph the way the query string says, and offers a link to each other way. Nothing is kept
on the server, so a variant can be shared, bookmarked and compared in two tabs.

A variant is declared once here; the page then shows its choices in the panel of the
graph, and graph/main.js reads the chosen values (graph_layout, as JSON). Other
parameters of the query string (a tag, #290) are kept by the links, and the forms of the
page keep the chosen variants (kept_params).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Variant:
    param: str  # in the query string, and the key read by graph/main.js
    label: str  # before its choices, in the panel
    choices: tuple  # (value, label), the default first

    @property
    def default(self):
        return self.choices[0][0]

    def chosen(self, query):
        value = query.get(self.param, "")
        return value if value in dict(self.choices) else self.default


# The timeline (x is the date), or a network laid out by Cytoscape's cose, without any
# time axis (#195).
VIEW = Variant(param="vue", label="Disposition", choices=(("frise", "Frise"), ("reseau", "Réseau")))

VARIANTS = (VIEW,)


def graph_layout(query):
    """The chosen value of every variant, {param: value}: what graph/main.js reads."""
    return {variant.param: variant.chosen(query) for variant in VARIANTS}


def kept_params(query):
    """The variants chosen other than by default, for the forms of the page to keep them."""
    return {
        variant.param: variant.chosen(query)
        for variant in VARIANTS
        if variant.chosen(query) != variant.default
    }


def variant_links(query):
    """
    The choices of each variant, each with the query string that selects it (other
    parameters kept) and whether it is the current one.
    """
    links = []
    for variant in VARIANTS:
        current = variant.chosen(query)
        options = []
        for value, label in variant.choices:
            params = query.copy()
            params[variant.param] = value
            options.append(
                {"label": label, "query": params.urlencode(), "current": value == current}
            )
        links.append({"label": variant.label, "options": options})
    return links
