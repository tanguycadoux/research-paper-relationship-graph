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

## Lancement du serveur

Une fois le venv activé, depuis la racine du dépôt :

```bash
python manage.py migrate
python manage.py runserver
```

L'application est alors accessible sur http://127.0.0.1:8000/.

La base `db.sqlite3` est locale et n'est pas versionnée.
Pour récupérer ses données sur une autre machine, il faut la copier à la main.
