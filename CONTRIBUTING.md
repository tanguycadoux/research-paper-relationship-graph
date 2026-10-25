# Contribuer

## Règles du projet

- Le code est en anglais (noms, commentaires, URL). L'interface utilisateur est en français.
- On écrit des fonctions courtes. Ruff vérifie la complexité (C901) et le nombre d'instructions (PLR0915).
- Les appels aux sources externes (Crossref, DataCite, OpenAlex, ORCID…) doivent rester rares : on ne refait jamais un appel dont le résultat est déjà en base, et on groupe les requêtes par lots quand la source le permet.
- Une donnée externe n'est jamais appliquée d'office si elle vient d'un rapprochement automatique : elle est proposée (candidat, conflit) ou signalée.
- Les templates respectent HTML5.
- La documentation (`docs/`) est mise à jour dans la pull request qui change l'architecture ou le comportement décrit ; une décision de conception s'ajoute au [journal des décisions](docs/decisions.md).

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
- Composants (`{% load ui %}`) : `button` (un lien quand il reçoit une `url`), `badge`, `alert`, `card`, `icon`, `external_link`, `pagination`, `column_header`, `filter_summary`. Les variantes sont définies dans `references/templatetags/ui.py`.
- Stabilité : les contrôles d'une page restent à la même place d'un état à l'autre (un bouton inutile est désactivé plutôt que masqué), et les boutons d'une même rangée sont alignés.
- Texte d'interface non sélectionnable (`select-none`, #210) : navigation, boutons, pastilles, en-têtes de tableau, axe et légende du graphe, logo. Ce qu'on peut vouloir copier (titres, auteurs, DOI, références) reste sélectionnable.
- Mise en page fluide, une seule pour tous les écrans (#150) : aucune page ne déborde horizontalement de 390 à 1400 px. Une grille déclare ses colonnes (`grid-cols-1`, pas de colonne implicite qui s'élargirait à la taille d'un tableau) ; un tableau est dans un `{% card flush=True %}`, qui défile horizontalement ; une colonne secondaire peut être masquée sous une largeur (`hidden xl:table-cell`) ; un bouton d'en-tête peut n'afficher que son icône sur petit écran (`compact=True`).
- Liens vers un autre site : toujours `{% external_link url libellé %}`, qui ouvre un nouvel onglet et le signale (icône et texte pour les lecteurs d'écran). Un test refuse les `href="http…"` écrits à la main.
- Navigation : elle est décrite dans `references/templatetags/navigation.py`. Une nouvelle page s'y ajoute si elle doit apparaître dans le menu.
- Icônes : `python manage.py add_icon <nom>` (noms de https://fonts.google.com/icons).

Les tests ne font aucun appel réseau : les sources externes sont simulées avec `unittest.mock`, là où elles sont appelées, souvent par les décorateurs de `references/tests/helpers.py` (`without_other_sources`, `without_candidate_search`, `without_doi_org`…). Le test runner (`config/test_runner.py`) fait échouer toute tentative de connexion, ce qui révèle un appel oublié, et désactive le cache HTTP de développement.

La CI (GitHub Actions) lance `ruff check`, `ruff format --check`, `djlint --lint`, `python manage.py test` (avec la couverture) et la construction de la feuille Tailwind sur chaque pull request. Les tests y tournent avec `requirements.txt` seul, comme en production : ceux qui demandent une dépendance de développement (requests-cache) sont sautés.
