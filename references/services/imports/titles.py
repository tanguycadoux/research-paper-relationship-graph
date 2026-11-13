import html
import re

# JATS or MathML elements (<i>, <sub>, <scp>, <mml:math>…), not a lone "<" in the text.
TAG_PATTERN = re.compile(r"</?[A-Za-z][\w:.-]*(?:\s[^<>]*)?/?>")
SPACES_PATTERN = re.compile(r"\s+")
# Some publishers escape their markup twice (IEEE: "&amp;lt;sub&amp;gt;", #263).
MAX_UNESCAPES = 3


def clean_title(raw):
    """
    Return a title as plain text: HTML entities decoded ("R&amp;D" becomes "R&D"),
    then markup removed, spaces collapsed. Entities are decoded until none is left, so
    that markup escaped twice by the publisher is removed too. LaTeX is kept as is.
    """
    if not raw:
        return ""
    text = raw
    for _ in range(MAX_UNESCAPES):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    return SPACES_PATTERN.sub(" ", TAG_PATTERN.sub("", text)).strip()


# Readable form of a title written in LaTeX (#264): « ${\rm Nb}_{3}{\rm Sn}$ » becomes
# « Nb₃Sn ». The title of the source is kept as is (it is authoritative, and BibTeX needs
# its LaTeX); this form is the one shown and searched. A formula that cannot be rendered
# whole leaves the title unchanged: no approximate rendering.
MATH_SEGMENT = re.compile(r"\$([^$]*)\$")
# Font and box commands: their argument, or the rest of their group, is kept.
FONT_COMMAND = re.compile(
    r"\\(?:rm|it|bf|sf|tt|cal|mathrm|mathit|mathbf|mathsf|mathtt|mathcal|text|textrm|textit|"
    r"textbf|textsf|texttt|textnormal|hbox|mbox|emph|boldsymbol|bm)(?![A-Za-z])\s*"
)
SPACING_COMMAND = re.compile(r"\\[,;:! ]")
COMMAND = re.compile(r"\\([A-Za-z]+)")
SCRIPT = re.compile(r"([_^])\s*(?:\{([^{}]*)\}|([^\s{}\\]))")
DEGREE = re.compile(r"\^\s*(?:\{\s*\\circ\s*\}|\\circ(?![A-Za-z]))")
ESCAPED = {"\\&": "&", "\\%": "%", "\\#": "#", "\\_": "_"}
GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "varepsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π",
    "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ",
    "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Upsilon": "Υ", "Phi": "Φ",
    "Psi": "Ψ", "Omega": "Ω",
}  # fmt: skip
SYMBOLS = GREEK | {
    "pm": "±", "mp": "∓", "times": "×", "cdot": "·", "sim": "∼", "approx": "≈",
    "simeq": "≃", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥", "ll": "≪", "gg": "≫",
    "neq": "≠", "to": "→", "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔",
    "infty": "∞", "partial": "∂", "nabla": "∇", "hbar": "ℏ", "ell": "ℓ", "AA": "Å",
    "prime": "′", "dagger": "†",
}  # fmt: skip
SUBSCRIPTS = dict(
    zip("0123456789+-−=()aeoxhklmnpstijruv", "₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜᵢⱼᵣᵤᵥ", strict=True)
)
SUPERSCRIPTS = dict(
    zip(
        "0123456789+-−=()abcdefghijklmnoprstuvwxyz",
        "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ",
        strict=True,
    )
)
SCRIPTS = {"_": SUBSCRIPTS, "^": SUPERSCRIPTS}


class Unreadable(Exception):
    """A piece of LaTeX that has no faithful plain-text form."""


def readable_title(title):
    """
    The title as plain text when it is written in LaTeX (#264): font commands and
    braces removed, simple subscripts and superscripts in Unicode, Greek letters and a
    few symbols as characters. The title is returned unchanged when it holds no LaTeX,
    or LaTeX that cannot be rendered whole.
    """
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
    """A piece of LaTeX as plain text, in math mode or not; Unreadable if it cannot be."""
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
    """A subscript or superscript in Unicode characters, when each has one."""
    characters = SCRIPTS[match.group(1)]
    content = match.group(2) if match.group(2) is not None else match.group(3)
    try:
        return "".join(characters[c] for c in content.replace(" ", ""))
    except KeyError:
        raise Unreadable(match.group(0)) from None
