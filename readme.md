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

L'application interroge l'API de Crossref. Pour bénéficier du *polite pool*
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
