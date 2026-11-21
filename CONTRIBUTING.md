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

- Structure de page : `templates/base.html` (en-tête, navigation, `<main>`). Chaque page commence par un `<header>` qui porte son unique `<h1>`, et ses titres se suivent sans saut de niveau. Une page du menu, ou atteinte depuis l'une d'elles (« Tags », graphes de la base, « Chercher par titre »), a pour `<h1>` le groupe de la navigation (« Mon corpus », « Base commune », « Corrections ») et pour premier `<h2>` son propre nom, suivi de son explication ; ses sections sont des `<h3>` (`{% card title=… level=3 %}`) ; son `<title>` est « Page · Groupe · Gestionnaire de références » (#417). Les boutons d'en-tête vers les autres pages du groupe restent à droite du `<h1>`. Une fiche (publication, auteur), ses graphes et ses modifications, l'identification d'une référence et la recherche gardent leur propre `<h1>` : le titre de l'objet est ce qu'on y cherche. Un test parcourt les pages du menu (`test_page_titles.py`).
- Styles : classes Tailwind dans les templates. Les styles par défaut des éléments (titres, liens, tableaux, champs de formulaire) sont définis une seule fois, dans la couche `base` de `assets/css/source.css` : un template n'ajoute que ce qui diffère. Pas de nouvelle classe CSS propre au projet. Tailwind en priorité, pas exclusivement : un attribut `style` reste permis pour ce que Tailwind ne peut pas écrire, typiquement une valeur calculée par le serveur (la largeur d’un segment de barre), entre `{# djlint:off H021 #}` et `{# djlint:on #}`.
- Composants (`{% load ui %}`) : `button` (un lien quand il reçoit une `url`), `badge`, `alert`, `card`, `icon`, `external_link`, `pagination`, `column_header`, `filter_summary`, `sort_links`, `field` et `form_errors`, et le filtre `pluralize_fr` (0 et 1 au singulier, à la place de `|pluralize`, #411). Un champ de formulaire Django passe par `{% field form.x %}` (libellé sans deux-points, aide et erreurs sous le champ, reliées par `aria-describedby`), jamais par `form.as_div`. Les variantes sont définies dans `references/templatetags/ui.py`.
- Stabilité : les contrôles d'une page restent à la même place d'un état à l'autre (un bouton inutile est désactivé plutôt que masqué), et les boutons d'une même rangée sont alignés.
- Ce qui flotte au-dessus du contenu (infobulle, panneau ou menu flottant) est en verre dépoli : `{% glass_classes %}` (fond translucide flouté, bordure claire, ombre douce), plutôt que des classes recopiées. Une surface posée dans la page (carte, tableau) reste opaque.
- Couleurs (#282) : l'ambre (`warning`) est réservé à ce qui attend une action de l'utilisateur (références à identifier, conflits, compteurs de la navigation, avertissements) ; un simple nombre est neutre. Un seul bouton plein par bloc pour l'action principale (« Identifier les 18 références en série ») ; les actions de chaque ligne sont des boutons secondaires discrets, sauf « Identifier » sur une référence à identifier, en ambre comme son filet et son badge (#384). Le lien qui nomme une ligne de tableau est en couleur de texte, bleu au survol (`{% row_title_classes %}`) ; le bleu reste aux actions et aux liens secondaires.
- Texte d'interface non sélectionnable (`select-none`, #210) : navigation, boutons, pastilles, en-têtes de tableau, axe et légende du graphe, logo. Ce qu'on peut vouloir copier (titres, auteurs, DOI, références) reste sélectionnable.
- Mise en page fluide, une seule pour tous les écrans (#150) : aucune page ne déborde horizontalement de 390 à 1400 px. Une grille déclare ses colonnes (`grid-cols-1`, pas de colonne implicite qui s'élargirait à la taille d'un tableau) ; un tableau est dans un `{% card flush=True %}`, qui défile horizontalement ; une colonne secondaire peut être masquée sous une largeur (`hidden xl:table-cell`) ; sous `sm`, le tableau des publications masque les colonnes Auteurs et Année, les résume sous le titre et garde leur tri par `{% sort_links %}` (#334), et de même pour la colonne Lecture de « Mon corpus », dont la liste passe sous le titre (#412) ; un bouton d'en-tête peut n'afficher que son icône sur petit écran (`compact=True`).
- Liens vers un autre site : toujours `{% external_link url libellé %}`, qui ouvre un nouvel onglet et le signale (icône et texte pour les lecteurs d'écran). Un test refuse les `href="http…"` écrits à la main.
- Navigation : elle est décrite dans `references/templatetags/navigation.py`. Une nouvelle page s'y ajoute si elle doit apparaître dans le menu.
- Vocabulaire (#275) : « corpus » désigne les publications d'un utilisateur (« Mon corpus », « Ajouter à mon corpus », « Retirer de mon corpus ») ; « références » est réservé à la bibliographie d'un article (« Références (21) », « références à identifier »).
- Icônes : `python manage.py add_icon <nom>` (noms de https://fonts.google.com/icons).

Les tests ne font aucun appel réseau. Les sources externes (Crossref, DataCite, OpenAlex, doi.org, ORCID, arXiv, Open Library) sont simulées au niveau HTTP par `references/tests/sources.py` (#299) : les clients de `references/services/sources/` tournent comme en production, seule la session HTTP répond à leur place, selon l'URL et les paramètres, lots compris. Un test dit donc quelles réponses existent, pas quels modules remplacer :

```python
from references.tests.sources import active_sources, fixture, simulated_sources


@simulated_sources(crossref={DOI: {"message": {"title": ["Titre"]}}})
class ImportTests(TestCase):
    def test_import(self):
        import_publication(Publication.objects.create(doi=DOI))
        self.assertEqual(active_sources().single("crossref"), [DOI])


class BatchTests(TestCase):  # sans décorateur : la simulation dans le test
    def test_batch(self):
        with simulated_sources(openalex=[fixture("openalex_arxiv1706.03762.json")]) as sources:
            complete_cited_with_openalex(source)
        self.assertEqual(sources.batches("openalex"), [[DOI_A, DOI_B]])
```

- `simulated_sources(...)` s'emploie comme `patch` : décorateur d'une méthode ou d'une classe de tests, ou bloc `with`, ou `self.enterContext(...)` dans `setUp`. Une seule simulation à la fois : un test d'une classe décorée ajoute des réponses par `active_sources().add(...)`, oubliées à la fin du test.
- Tant qu'elle est active, chaque source ne connaît que ce qu'on lui a donné : un DOI inconnu est un 404, un lot répond sans lui, une recherche ne trouve rien. `unreachable=["crossref"]` fait répondre 503 à une source (réessais sans attente). doi.org enregistre les DOI connus de Crossref et DataCite et ne répond pas pour les autres (accepté, comme quand doi.org est injoignable), sauf `doi_org=…`.
- Les réponses réelles sont dans `references/tests/fixtures/` (une réponse de la source, telle quelle) ; `fixture(nom)` les lit. Une réponse écrite dans le test peut se réduire aux champs utiles : le DOI (Crossref) ou l'`id` (DataCite) est ajouté d'après la clé.
- Ce qui a été demandé se lit dans la simulation : `single(source)` (un DOI à la fois), `batches(source)` (les lots), `searches(source)`, `asked(source)`, `to(source)` (les requêtes, avec leurs paramètres), `forget()`.
- Une requête qu'aucune route ne prévoit (autre hôte, autre chemin, autre paramètre) fait échouer le test : « requête non simulée : GET https://… ». Une nouvelle source ou un nouvel appel s'ajoute dans `sources.py`, avec un test dans `test_simulated_sources.py`.

Les tests de la couche HTTP elle-même (réessais, `Retry-After`, en-têtes, journal des appels, cache, fichiers tronqués) remplacent encore la session par un `Mock`. Le test runner (`config/test_runner.py`) fait échouer toute tentative de connexion, ce qui révèle un appel oublié, et désactive le cache HTTP de développement.

La CI (GitHub Actions) lance `ruff check`, `ruff format --check`, `djlint --lint`, `python manage.py test` (avec la couverture) et la construction de la feuille Tailwind sur chaque pull request. Les tests y tournent avec `requirements.txt` seul, comme en production : ceux qui demandent une dépendance de développement (requests-cache) sont sautés.
