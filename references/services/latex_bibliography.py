r"""
Bibliography of an arXiv preprint read in its LaTeX sources (#227): arXiv does not run
BibTeX, so the authors deposit the .bbl, or write the thebibliography by hand. Each
\bibitem becomes a reference with its text, as Crossref gives them; it is linked only
through an identifier the authors wrote: a DOI, or an arXiv identifier (the DOI
10.48550/arXiv.…). The others are left to identify.

The archive is read in memory, never extracted: only the .tex and .bbl files, each
within a size limit.
"""

import gzip
import io
import re
import tarfile
import unicodedata

from .doi import is_valid_doi, normalize_doi

BS = "\\"
# A source file larger than this is not LaTeX written by hand: skipped.
MAX_FILE_BYTES = 5 * 1024 * 1024
ARXIV_ID = re.compile(
    r"(?:arXiv\s*:\s*|arxiv\.org/abs/|abs/)(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})",
    re.IGNORECASE,
)
DOI = re.compile(r"10\.\d{4,9}/[^\s{}\\,;]+")
ACCENTS = {
    '"': "\u0308",
    "'": "\u0301",
    "`": "\u0300",
    "^": "\u0302",
    "~": "\u0303",
    "c": "\u0327",
    "v": "\u030c",
    "u": "\u0306",
    "=": "\u0304",
    ".": "\u0307",
    "H": "\u030b",
    "k": "\u0328",
}
LETTERS = {
    "ss": "ß",
    "o": "ø",
    "O": "Ø",
    "l": "ł",
    "L": "Ł",
    "ae": "æ",
    "AE": "Æ",
    "oe": "œ",
    "OE": "Œ",
    "aa": "å",
    "AA": "Å",
    "i": "ı",
}
# Commands whose argument is the text to keep (\bibinfo{author}{X} keeps X).
KEEP_ARGUMENT = (
    "emph|textit|textbf|textrm|textsc|textsf|texttt|textup|mbox|hbox|url|path|"
    "bibnamefont|bibfnamefont|citenamefont|bibinfo\\s*\\{[^{}]*\\}|bibfield\\s*\\{[^{}]*\\}"
)


def read_eprint(raw):
    """
    What an arXiv e-print holds: {"source": "tar" | "gz" | "pdf", "format": "bbl" |
    "inline" | "none", "entries": [{"key", "text"}]} with the raw LaTeX of each entry.
    """
    kind, files = source_files(raw)
    where, entries = bibliography(files)
    return {"source": kind, "format": where, "entries": entries}


def source_files(raw):
    """Text files of an e-print: a tar.gz, a single gzipped .tex, or a PDF (nothing)."""
    if raw[:4] == b"%PDF":
        return "pdf", {}
    try:
        archive = tarfile.open(fileobj=io.BytesIO(raw))
    except tarfile.TarError:
        archive = None
    if archive is not None:
        files = {}
        for member in archive.getmembers():
            if (
                member.isfile()
                and member.name.endswith((".tex", ".bbl"))
                and member.size <= MAX_FILE_BYTES
            ):
                files[member.name] = archive.extractfile(member).read().decode("utf-8", "replace")
        return "tar", files
    try:
        text = gzip.decompress(raw)[:MAX_FILE_BYTES]
    except OSError, EOFError:
        text = raw[:MAX_FILE_BYTES]
    return "gz", {"main.tex": text.decode("utf-8", "replace")}


def bibliography(files):
    """The \\bibitem entries of the .bbl files, else of the .tex files (written inline)."""
    for where, suffix in (("bbl", ".bbl"), ("inline", ".tex")):
        entries = [
            entry
            for name, text in sorted(files.items())
            if name.endswith(suffix)
            for entry in bibitems(text)
        ]
        if entries:
            return where, entries
    return "none", []


def bibitems(text):
    """Entries of the thebibliography environments of a file."""
    entries = []
    for block in re.findall(
        r"\\begin\{thebibliography\}(.*?)(?:\\end\{thebibliography\}|\Z)", text, re.DOTALL
    ):
        for item in block.split(BS + "bibitem")[1:]:
            key, rest = item_key(item)
            entries.append({"key": key, "text": rest.strip()})
    return entries


def item_key(item):
    """\\bibitem[label]{key} text: (key, text), the label skipped (braces may nest)."""
    text = item.lstrip()
    if text.startswith("["):
        text = text[label_end(text) + 1 :].lstrip()
    match = re.match(r"\{([^{}]*)\}", text)
    if not match:
        return "", text
    return match.group(1).strip(), text[match.end() :]


def label_end(text):
    """Index of the ] that closes the [label] at the start of text, outside braces."""
    depth = 0
    for index, char in enumerate(text):
        depth += (char == "{") - (char == "}")
        if char == "]" and depth == 0:
            return index
    return len(text)


def written_identifier(text):
    """The DOI written in an entry, else the DOI of the arXiv identifier written; or ""."""
    flat = re.sub(r"\\(?:url|href|doi)\s*\{", "{", text).replace(BS + "_", "_")
    for match in DOI.finditer(flat):
        doi = normalize_doi(match.group(0).rstrip(".)]"))
        if is_valid_doi(doi):
            return doi
    match = ARXIV_ID.search(flat)
    return normalize_doi(f"10.48550/arXiv.{match.group(1)}") if match else ""


def clean_latex(text):
    """The text of an entry, readable: commands, braces and spacing marks removed."""
    text = re.sub(r"(?<!\\)%[^\n]*", "", text)  # comments
    text = re.sub(r"\\href\s*\{[^{}]*\}\s*\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\(?:newblock|natexlab\{[^{}]*\}|providecommand\S*)", " ", text)
    text = re.sub(r"\\(?:em|it|bf|sc|rm|tt|sl|sf|small|normalfont)\b\s*", "", text)
    for _ in range(3):  # nested commands
        text = re.sub(rf"\\(?:{KEEP_ARGUMENT})\s*\{{([^{{}}]*)\}}", r"\1", text)
    text = re.sub(r"\\([\"'`^~=.]|[cvuHk](?![a-zA-Z]))\s*\{?\s*([a-zA-Z]|\\i)\s*\}?", accent, text)
    text = re.sub(
        r"\\(ss|ae|AE|oe|OE|aa|AA|[oOlLi])(?![a-zA-Z])\s*", lambda m: LETTERS[m.group(1)], text
    )
    text = re.sub(r"\\([&%$#_])", r"\1", text)
    text = text.replace("~", " ").replace("--", "–").replace("``", "“").replace("''", "”")
    text = re.sub(r"\\[,;:! ]", " ", text)
    text = re.sub(r"\\[a-zA-Z@]+\*?", " ", text)  # remaining commands
    text = text.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", text).strip(" ,.") + "."


def accent(match):
    mark, letter = match.group(1), match.group(2)
    letter = "i" if letter == BS + "i" else letter
    return unicodedata.normalize("NFC", letter + ACCENTS[mark])


def references(data):
    """The entries of a stored e-print, as Crossref references: key, text, DOI if written."""
    refs = []
    for entry in (data or {}).get("entries", []):
        ref = {"key": entry.get("key", ""), "unstructured": clean_latex(entry.get("text", ""))}
        doi = written_identifier(entry.get("text", ""))
        if doi:
            ref["DOI"] = doi
        refs.append(ref)
    return refs
