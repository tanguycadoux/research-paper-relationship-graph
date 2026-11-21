"""
The tree of docs/architecture.md (« Organisation du code ») cites every module (#343):
each Python module of references/ (migrations and tests aside), each script of
static/js/ and of the graphs, at its place in the tree.
"""

import re

from django.conf import settings
from django.test import SimpleTestCase

BASE_DIR = settings.BASE_DIR
TREE = re.compile(r"## Organisation du code\n+```\n(.*?)```", re.DOTALL)
FILE_NAME = re.compile(r"(?<![\w./-])([\w/-]+\.(?:py|js))\b")
SKIPPED_DIRS = {"migrations", "tests", "__pycache__"}


def tree_lines():
    text = (BASE_DIR / "docs" / "architecture.md").read_text(encoding="utf-8")
    return TREE.search(text).group(1).splitlines()


def walk_tree():
    """
    (path of a directory or file named on a line, files of the line), the parent of a
    line being the last directory written with less indentation.
    """
    parents = []  # (indentation, path)
    for line in filter(str.strip, tree_lines()):
        indent = len(line) - len(line.lstrip())
        while parents and parents[-1][0] >= indent:
            parents.pop()
        parent = parents[-1][1] if parents else ""
        first = line.split()[0].rstrip(",")
        if first.endswith("/"):
            parents.append((indent, parent + first))
            continue
        yield parent + first, {parent + name for name in FILE_NAME.findall(line)}


def cited_files():
    return {path for _, names in walk_tree() for path in names}


def project_files():
    python = {
        path
        for path in (BASE_DIR / "references").rglob("*.py")
        if path.name != "__init__.py" and not SKIPPED_DIRS & set(path.parts)
    }
    scripts = {
        *(BASE_DIR / "static" / "js").glob("*.js"),
        *(BASE_DIR / "references" / "static" / "references" / "graph").glob("*.js"),
    }
    return {str(path.relative_to(BASE_DIR)) for path in python | scripts}


class ArchitectureDocTests(SimpleTestCase):
    def test_every_module_is_cited_at_its_place(self):
        missing = sorted(project_files() - cited_files())
        self.assertFalse(
            missing,
            "Modules absents de l'arbre « Organisation du code » de docs/architecture.md."
            " Ajoutez pour chacun une ligne sous son dossier (`nom.py  à quoi il sert`,"
            " au niveau de ses voisins) : " + ", ".join(missing),
        )

    def test_every_cited_file_exists(self):
        absent = sorted(path for path in cited_files() if not (BASE_DIR / path).exists())
        self.assertFalse(
            absent,
            "Fichiers cités dans l'arbre de docs/architecture.md mais absents du dépôt"
            " (renommés, supprimés, ou mal placés dans l'arbre) : " + ", ".join(absent),
        )
