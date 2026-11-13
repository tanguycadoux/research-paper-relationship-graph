import re

from django.db import migrations, models

# Copy of references.services.imports.titles.readable_title at the time of this
# migration (#264): the title without its LaTeX, or the title itself.
SPACES_PATTERN = re.compile(r"\s+")
MATH_SEGMENT = re.compile(r"\$([^$]*)\$")
FONT_COMMAND = re.compile(
    r"\\(?:rm|it|bf|sf|tt|cal|mathrm|mathit|mathbf|mathsf|mathtt|mathcal|text|textrm|textit|"
    r"textbf|textsf|texttt|textnormal|hbox|mbox|emph|boldsymbol|bm)(?![A-Za-z])\s*"
)
SPACING_COMMAND = re.compile(r"\\[,;:! ]")
COMMAND = re.compile(r"\\([A-Za-z]+)")
SCRIPT = re.compile(r"([_^])\s*(?:\{([^{}]*)\}|([^\s{}\\]))")
DEGREE = re.compile(r"\^\s*(?:\{\s*\\circ\s*\}|\\circ(?![A-Za-z]))")
ESCAPED = {"\\&": "&", "\\%": "%", "\\#": "#", "\\_": "_"}
SYMBOLS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π",
    "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ",
    "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ",
    "Psi": "Ψ", "Omega": "Ω",
    "pm": "±", "mp": "∓", "times": "×", "cdot": "·", "sim": "∼", "approx": "≈",
    "simeq": "≃", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ll": "≪", "gg": "≫",
    "neq": "≠", "to": "→", "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔",
    "infty": "∞", "partial": "∂", "nabla": "∇", "hbar": "ℏ", "ell": "ℓ", "AA": "Å",
    "prime": "′", "dagger": "†",
}  # fmt: skip
SCRIPTS = {
    "_": dict(zip("0123456789+-−=()aeoxhklmnpstijruv", "₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜᵢⱼᵣᵤᵥ")),
    "^": dict(
        zip(
            "0123456789+-−=()abcdefghijklmnoprstuvwxyz",
            "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ",
        )
    ),
}


class Unreadable(Exception):
    pass


def readable_title(title):
    if not title or ("$" not in title and "\\" not in title):
        return title or ""
    if title.count("$") % 2:
        return title
    try:
        text = MATH_SEGMENT.sub(lambda match: readable_latex(match.group(1), math=True), title)
        text = readable_latex(text, math=False)
    except Unreadable:
        return title
    return SPACES_PATTERN.sub(" ", text).strip()


def readable_latex(text, *, math):
    for escaped, character in ESCAPED.items():
        text = text.replace(escaped, character)
    if math:
        text = DEGREE.sub("°", text)
    text = COMMAND.sub(symbol, SPACING_COMMAND.sub(" ", FONT_COMMAND.sub("", text)))
    if math:
        text = SCRIPT.sub(script, text)
    if "\\" in text or (math and ("_" in text or "^" in text)):
        raise Unreadable(text)
    return text.replace("{", "").replace("}", "")


def symbol(match):
    try:
        return SYMBOLS[match.group(1)]
    except KeyError:
        raise Unreadable(match.group(0)) from None


def script(match):
    content = match.group(2) if match.group(2) is not None else match.group(3)
    try:
        return "".join(SCRIPTS[match.group(1)][c] for c in content.replace(" ", ""))
    except KeyError:
        raise Unreadable(match.group(0)) from None


def fill_readable_titles(apps, schema_editor):
    Publication = apps.get_model("references", "Publication")
    publications = list(Publication.objects.only("pk", "title"))
    for pub in publications:
        pub.readable_title = readable_title(pub.title)
    Publication.objects.bulk_update(publications, ["readable_title"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("references", "0030_sort_ieee_references"),
    ]

    operations = [
        migrations.AddField(
            model_name="publication",
            name="readable_title",
            field=models.TextField(blank=True, editable=False, verbose_name="titre lisible"),
        ),
        migrations.RunPython(fill_readable_titles, migrations.RunPython.noop),
    ]
