# Contribuer

## Règles du projet

- Le code est en anglais (noms, commentaires, URL). L'interface utilisateur est en français.
- On écrit des fonctions courtes. Ruff vérifie la complexité (C901) et le nombre d'instructions (PLR0915).
- Les appels à l'API Crossref doivent rester rares : on ne refait jamais un appel dont le résultat est déjà en base.
- Les templates respectent HTML5.

## Organisation du travail

- Tout problème repéré et toute fonctionnalité à ajouter fait l'objet d'une issue.
- Les issues sont regroupées par milestone. Pendant le travail sur une milestone, on peut y ajouter des issues si elles servent son objectif, mais on reste dans son sujet.
- On ne pousse jamais directement sur `main`. Chaque issue est traitée dans une branche (`fix/…`, `feat/…`, `chore/…`), puis fusionnée par une pull request qui la référence (`Closes #n`).
- Des branches peuvent avancer en parallèle si elles ne touchent pas les mêmes fichiers, pour éviter les conflits de merge.

## Linter

```bash
pip install -r requirements-dev.txt
ruff check .
ruff format .
```

La CI (GitHub Actions) lance `ruff check` et `ruff format --check` sur chaque pull request.
