# Gestionnaire de références

Application Django pour analyser les relations entre articles scientifiques.
Quand on ajoute un article à son corpus, ses métadonnées et celles des articles
qu'il cite sont récupérées depuis [Crossref](https://www.crossref.org/).

## Installation

Il faut Python 3.12 ou plus récent. Le dossier `.venv` n'est pas versionné : chaque
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
python manage.py runserver
```

L'application est alors accessible sur http://127.0.0.1:8000/.

La base `db.sqlite3` est locale et n'est pas versionnée.
Pour récupérer ses données sur une autre machine, il faut la copier à la main.

## Commandes utiles

```bash
# Rattacher les affiliations des publications déjà en base, à partir des données OpenAlex
# stockées (les organisations parentes manquantes sont demandées en une requête groupée)
python manage.py complete_affiliations

# Idem, en demandant d'abord à OpenAlex les publications qui n'ont pas encore de réponse
# (une requête par lot de 50 publications)
python manage.py complete_affiliations --fetch-missing
```
