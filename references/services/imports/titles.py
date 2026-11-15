import html
import re
import unicodedata

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
# whole stays as it is, the others are rendered (#345): no approximate rendering.
MATH_SEGMENT = re.compile(r"\$([^$]*)\$")
# Old IEEE markup (#345): « low-/spl beta/ », « T/sub c/ », « 10/sup 3/ ».
IEEE_MARKUP = re.compile(r"/(spl|sub|sup)\s+([^/\s]+)\s*/")
IEEE_AS_LATEX = {"spl": "$\\{}$", "sub": "$_{{{}}}$", "sup": "$^{{{}}}$"}
# Commands whose backslash the publisher dropped, in a formula (IEEE, #345):
# « $hboxNb_3hboxSn$ », « $beta$ ».
BARE_BOX = re.compile(r"(?<![\\A-Za-z])(?:hbox|mbox|mathrm)(?=[A-Z{])")
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
    few symbols as characters. Each formula, and each piece of text between them, is
    rendered on its own: one that cannot be rendered whole stays as it is (#345). The
    title is returned unchanged when it holds no LaTeX.
    """
    if title and IEEE_MARKUP.search(title):
        title = IEEE_MARKUP.sub(lambda m: IEEE_AS_LATEX[m.group(1)].format(m.group(2)), title)
    if not title or ("$" not in title and "\\" not in title):
        return title or ""
    if title.count("$") % 2:
        return title
    # Text and formulas alternate: text, formula, text… (split keeps the formulas).
    parts = MATH_SEGMENT.split(title)
    rendered = [readable_part(part, math=bool(index % 2)) for index, part in enumerate(parts)]
    return SPACES_PATTERN.sub(" ", "".join(spaced(rendered, parts))).strip()


def readable_part(part, *, math):
    """A rendered piece of the title, or the piece as written when it cannot be."""
    try:
        return readable_latex(bare_commands(part) if math else part, math=math)
    except Unreadable:
        return f"${part}$" if math else part


def bare_commands(formula):
    """Commands written without their backslash, read as commands (#345)."""
    formula = BARE_BOX.sub("", formula)
    return re.sub(
        r"(?<![\\A-Za-z])([A-Za-z]+)(?![A-Za-z])",
        lambda m: f"\\{m.group(1)}" if m.group(1) in GREEK else m.group(1),
        formula,
    )


def spaced(rendered, parts):
    """
    The spaces some publishers drop around a formula (#345): « mm$…$Model » reads
    « mm Nb₃Sn Model ». Only between two letters, and a formula that begins or ends with
    a letter, not a subscript: « Nb$_3$Sn » stays one word.
    """
    pieces = list(rendered)
    for index in range(1, len(pieces), 2):
        formula = pieces[index]
        if formula == f"${parts[index]}$" or not formula:
            continue
        before, after = pieces[index - 1], pieces[index + 1]
        if before and is_letter(before[-1]) and formula[0].isupper():
            pieces[index] = " " + pieces[index]
        if after and is_letter(formula[-1]) and after[0].isupper():
            pieces[index] += " "
    return pieces


def is_letter(character):
    """A letter of a word (Latin, Greek), not a subscript or superscript letter."""
    return unicodedata.category(character) in ("Lu", "Ll")


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
