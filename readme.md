# Gestionnaire de références

Application Django pour analyser les relations entre articles scientifiques.
Quand on ajoute un article à son corpus, ses métadonnées et celles des articles qu'il
cite sont récupérées depuis [Crossref](https://www.crossref.org/), ou
[DataCite](https://datacite.org/) pour les DOI qu'il ne connaît pas (actes de conférence,
prépublications arXiv, Zenodo), puis complétées par [OpenAlex](https://openalex.org/)
(institutions, ORCID, résumé) et [ORCID](https://orcid.org/) (noms des auteurs). La
bibliographie d'une prépublication sans version publiée est lue dans ses sources LaTeX
sur [arXiv](https://arxiv.org/). Les livres sont identifiés par leur ISBN, avec
[Open Library](https://openlibrary.org/) en recours.

Fonctionnalités :
- un **corpus** personnel, avec statut de lecture et tags hiérarchiques, importable
  depuis un fichier BibTeX, RIS ou un export JSON, exportable en JSON et en BibTeX ;
- une **base commune** de publications et d'auteurs, corrigée par tous : identification
  assistée des références citées (candidats proposés, en série), fusion d'auteurs et de
  publications, doublons probables, conflits entre sources ;
- les **prépublications arXiv** remplacées par leur version publiée, déclarée par les
  auteurs ou proposée d'après OpenAlex ;
- une **recherche** à opérateurs, des tableaux triables et filtrables ;
- un **graphe des citations** sur une frise chronologique, pour une publication, son
  corpus ou toute la base ;
- les **affiliations** des auteurs, regroupées par organisation de tutelle.

Documentation :
- [Architecture](docs/architecture.md) : principe, organisation du code, modèle de
  données, et liens vers les documents détaillés ([sources de métadonnées](docs/sources.md),
  avec le schéma d'un import ; [corrections](docs/corrections.md) ;
  [graphes](docs/graphes.md) ; [interface](docs/interface.md) ;
  [journal des décisions](docs/decisions.md)) ;
- [Contribuer](CONTRIBUTING.md) : règles du projet, branches, messages de commit, tests.

## Installation

Il faut Python 3.14 (la version utilisée en développement et en CI). Le dossier `.venv` n'est pas versionné : chaque
machine crée le sien.

### Windows (PowerShell)

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Si PowerShell refuse d'exécuter le script d'activation :
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

La configuration sensible se lit dans des variables d'environnement, jamais dans le code :
le dépôt est public.

| Variable | Rôle |
|---|---|
| `DJANGO_DEBUG` | `1` en développement local. Absente, le mode debug est désactivé. |
| `DJANGO_SECRET_KEY` | Clé secrète de Django, obligatoire hors mode debug. |
| `DJANGO_ALLOWED_HOSTS` | Noms de domaine servis, séparés par des virgules (inutile en local). |
| `CROSSREF_MAILTO` | Adresse de contact pour Crossref et OpenAlex (voir plus bas). |

Sur une machine de développement, il suffit de `DJANGO_DEBUG` :

```powershell
# Windows (PowerShell), de façon permanente (nouveau terminal nécessaire)
setx DJANGO_DEBUG 1
```

```bash
# Linux / macOS (à ajouter dans ~/.bashrc)
export DJANGO_DEBUG=1
```

Pour un déploiement, générez une clé avec
`python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`.

### Adresse de contact Crossref

L'application interroge les API de Crossref, DataCite et OpenAlex. L'adresse ci-dessous sert de contact pour Crossref et OpenAlex. Pour bénéficier du *polite pool*
(10 requêtes/s au lieu de 5, et un service plus stable), il faut fournir une adresse
e-mail de contact dans la variable d'environnement `CROSSREF_MAILTO`. Ne la mettez pas
dans le code : le dépôt est public.

```powershell
# Windows (PowerShell), pour la session en cours
$env:CROSSREF_MAILTO = "vous@example.org"
# ou de façon permanente (nouveau terminal nécessaire)
setx CROSSREF_MAILTO "vous@example.org"
```

```bash
# Linux / macOS (à ajouter dans ~/.bashrc pour la rendre permanente)
export CROSSREF_MAILTO="vous@example.org"
```

Sans cette variable, l'application fonctionne dans le *public pool* et affiche un
avertissement au premier appel.

## Lancement du serveur

Une fois le venv activé, depuis la racine du dépôt :

```bash
python manage.py migrate
python manage.py tailwind runserver
```

L'application est alors accessible sur http://127.0.0.1:8000/.

`tailwind runserver` lance le serveur et reconstruit la feuille de style Tailwind à chaque
modification d'un template. Au premier lancement, il télécharge le CLI de Tailwind
(environ 110 Mo, sans Node) dans `.django_tailwind_cli/`. La feuille compilée
(`static/css/tailwind.css`) n'est pas versionnée ; pour la construire une seule fois, sans
serveur : `python manage.py tailwind build`. Ses sources sont dans `assets/css/source.css`.

La base `db.sqlite3` est locale et n'est pas versionnée.
Pour récupérer ses données sur une autre machine, il faut la copier à la main.

En développement (`DJANGO_DEBUG=1`), les réponses des sources externes sont gardées
7 jours dans `.http_cache.sqlite`, à part de la base, si `requests-cache` est installé
(`pip install -r requirements-dev.txt`). Réimporter les mêmes publications ne les
redemande donc pas.

## Commandes utiles

```bash
# Rattacher les affiliations des publications déjà en base, à partir des données OpenAlex
# stockées (les organisations parentes manquantes sont demandées en une requête groupée)
python manage.py complete_affiliations

# Idem, en demandant d'abord à OpenAlex les publications qui n'ont pas encore de réponse
# (une requête par lot de 50 publications)
python manage.py complete_affiliations --fetch-missing

# Compléter depuis ORCID les noms des auteurs déjà en base (--refresh : tout redemander)
python manage.py complete_orcid_names

# Fusionner les auteurs déjà en base qui portent le même ORCID
python manage.py merge_same_orcid

# Remplacer les prépublications arXiv par leur version publiée déclarée, et proposer
# dans « Conflits » celle que trouve OpenAlex
python manage.py replace_preprints

# Développement : vider la base en gardant les comptes et le cache des sources
python manage.py reset_data
# … en vidant aussi le cache, pour tout redemander aux sources
python manage.py reset_data --clear-http-cache
```

## Tests et vérifications

```bash
pip install -r requirements-dev.txt
python manage.py test
ruff check . && ruff format --check .
djlint --lint templates references/templates accounts/templates
```

Les tests ne font aucun appel réseau. Le détail des règles est dans
[CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

Le code est distribué sous licence [MIT](LICENSE). Les bibliothèques et ressources
embarquées gardent leur propre licence : Cytoscape.js (MIT,
`static/vendor/cytoscape/LICENSE`) et les icônes Material Symbols (Apache 2.0,
`static/icons/LICENSE`).
