# Contribuer

## Règles du projet

- Le code est en anglais (noms, commentaires, URL). L'interface utilisateur est en français.
- On écrit des fonctions courtes. Ruff vérifie la complexité (C901) et le nombre d'instructions (PLR0915).
- Les appels à l'API Crossref doivent rester rares : on ne refait jamais un appel dont le résultat est déjà en base.
- Les templates respectent HTML5.

## Organisation du travail

- Tout problème repéré et toute fonctionnalité à ajouter fait l'objet d'une issue.
- Les issues sont regroupées par milestone. Le titre d'une milestone est préfixé par son numéro d'ordre (`M1 - …`, `M2 - …`). Pendant le travail sur une milestone, on peut y ajouter des issues si elles servent son objectif, mais on reste dans son sujet.
- On ne pousse jamais directement sur `main`. Chaque issue est traitée dans une branche (`fix/…`, `feat/…`, `chore/…`), puis fusionnée par une pull request qui la référence (`Closes #n`).
- Des branches peuvent avancer en parallèle si elles ne touchent pas les mêmes fichiers, pour éviter les conflits de merge.
- `main` est protégée : pas de push direct, la CI doit passer, et une branche doit être à jour avec `main` avant le merge (bouton « Update branch »).
- Après la fusion d'une pull request, sa branche est supprimée sur GitHub (automatique) et en local : `git switch main`, `git pull`, `git fetch --prune`, puis `git branch -d <branche>`.

## Messages de commit

Les messages suivent [Conventional Commits](https://www.conventionalcommits.org/fr/). Le type et la portée sont en anglais, la description en français :

```
<type>(<portée optionnelle>): <description>

<corps optionnel>

Closes #n
```

Types utilisés : `feat` (fonctionnalité), `fix` (correction de bug), `refactor`, `test`, `docs`, `style` (mise en forme sans changement de code), `chore` (outillage, dépendances, dépôt), `ci`, `perf`.

Exemples :
- `feat(crossref): identifier l'application via mailto`
- `fix(authors): éviter l'IntegrityError lors d'une fusion`
- `chore: retirer .venv du suivi git`

Un changement incompatible est signalé par `!` après le type (`feat!: …`), avec une ligne `BREAKING CHANGE: …` dans le corps.

## Linter et tests

```bash
pip install -r requirements-dev.txt
ruff check .
ruff format .
djlint --lint templates references/templates accounts/templates
python manage.py test
coverage run manage.py test && coverage report   # couverture, lignes non couvertes
```

Les templates suivent HTML5 : `lang="fr"`, balises sémantiques (`<header>`, `<nav>`, un seul `<main>`, `<aside>`…), pas de style inline. djLint vérifie une partie de ces règles. Après un changement de structure, validez aussi une page rendue avec le [validateur W3C](https://validator.w3.org/nu/).

### Interface

- Structure de page : `templates/base.html` (en-tête, navigation, `<main>`). Chaque page commence par un `<header>` qui porte son unique `<h1>`, et ses titres se suivent sans saut de niveau.
- Styles : classes Tailwind dans les templates. Les styles par défaut des éléments (titres, liens, tableaux, champs de formulaire) sont définis une seule fois, dans la couche `base` de `assets/css/source.css` : un template n'ajoute que ce qui diffère. Pas de nouvelle classe CSS propre au projet.
- Composants (`{% load ui %}`) : `button` (un lien quand il reçoit une `url`), `badge`, `alert`, `card`, `icon`. Les variantes sont définies dans `references/templatetags/ui.py`.
- Liens vers un autre site : toujours `{% external_link url libellé %}`, qui ouvre un nouvel onglet et le signale (icône et texte pour les lecteurs d'écran). Un test refuse les `href="http…"` écrits à la main.
- Navigation : elle est décrite dans `references/templatetags/navigation.py`. Une nouvelle page s'y ajoute si elle doit apparaître dans le menu.
- Icônes : `python manage.py add_icon <nom>` (noms de https://fonts.google.com/icons).

Les tests ne font aucun appel réseau : les appels à Crossref sont simulés avec `unittest.mock`. Le test runner (`config/test_runner.py`) fait échouer toute tentative de connexion, ce qui révèle un appel oublié.

La CI (GitHub Actions) lance `ruff check`, `ruff format --check`, `djlint --lint` et `python manage.py test` sur chaque pull request.
