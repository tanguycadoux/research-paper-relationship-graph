"""
Variants of the layout of a citation graph, chosen in the URL (#288): the page draws
the graph the way the query string says, and offers a link to each other way. Nothing is
kept on the server, so a variant can be shared, bookmarked and compared in two tabs.

A variant is declared once here; the page then shows its choices in the toolbar of the
graph, and graph/main.js reads the chosen values (graph_layout, as JSON). Other
parameters of the query string (a tag, #290) are kept by the links.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Variant:
    param: str  # in the query string, and the key read by graph/main.js
    label: str  # before its choices, in the toolbar
    choices: tuple  # (value, label), the default first
    applies: callable  # graph -> bool: the choice changes nothing otherwise

    @property
    def default(self):
        return self.choices[0][0]

    def chosen(self, query):
        value = query.get(self.param, "")
        return value if value in dict(self.choices) else self.default


def has_undated(graph):
    return any(not node["data"].get("date") for node in graph["nodes"])


# Publications without a date: the former column on the left of the timeline, or a band
# under it, near the publications they cite or that cite them. Both are kept for now, to
# compare them on real graphs (#288).
UNDATED = Variant(
    param="non_dates",
    label="Non datés",
    choices=(("gauche", "À gauche"), ("bande", "En bas")),
    applies=has_undated,
)

VARIANTS = (UNDATED,)


def graph_layout(query):
    """The chosen value of every variant, {param: value}: what graph/main.js reads."""
    return {variant.param: variant.chosen(query) for variant in VARIANTS}


def variant_links(query, graph):
    """
    The choices of the variants that change something on this graph, each with the query
    string that selects it (other parameters kept) and whether it is the current one.
    """
    links = []
    for variant in VARIANTS:
        if not variant.applies(graph):
            continue
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
