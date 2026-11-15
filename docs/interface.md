# Interface

Organisation des pages et des listes. Les conventions d'écriture des templates (couche
`base` de Tailwind, composants, liens externes, icônes) sont dans
[CONTRIBUTING.md](../CONTRIBUTING.md#interface). Vue d'ensemble du projet :
[architecture.md](architecture.md).

- **Tailwind**, compilé par django-tailwind-cli depuis `assets/css/source.css`, sans Node.
  Les styles par défaut des éléments sont définis une fois dans la couche `base`.
- **Composants** en template tags (`references/templatetags/ui.py`) : `button`, `badge`,
  `alert`, `card`, `icon`, `external_link`, `pagination`, `column_header`,
  `filter_summary` ; les panneaux `popover` partagent leurs classes
  (`popover_panel_classes`). **Verre dépoli** (`glass_classes`, #202) : ce qui flotte
  au-dessus du contenu (infobulle de survol du graphe, panneaux `popover`, menus de la
  navigation sur petit écran, et à l'avenir une barre qui reste au-dessus de ce qui
  défile) a un fond blanc translucide
  qui floute ce qu'il recouvre, une bordure claire, des coins arrondis et une ombre douce :
  le contenu reste deviné dessous. Les classes sont définies une seule fois
  (`GLASS_CLASSES`, `{% glass_classes %}`) ; l'élément ajoute sa taille, ses marges et son
  texte. Les toasts gardent la teinte de leur variante, translucide, sur le même flou
  (`TOAST_VARIANTS`, #333). Pas pour une surface posée dans la page (carte, tableau, panneau du graphe), qui
  reste blanche et opaque. **Navigation** décrite dans
  `templatetags/navigation.py`, avec des **compteurs** de ce qui attend une action
  (#152, `services/display/pending.py`) : références à identifier dans son corpus, conflits
  ouverts. Les références à identifier ont leur propre lien, « Mon corpus › À identifier »,
  qui filtre le corpus sur les publications concernées (`?to_identify=1`, #276) : posé sur
  « Publications », le nombre se lisait comme une taille de corpus. Une requête par compteur, sans cache, pour qu'un compteur soit juste aussitôt
  après l'action ; rien n'est affiché à zéro. Les doublons probables ont aussi
  leur compteur (« à examiner », #270), par un comptage léger
  (`author_duplicates.duplicate_count`, 78 ms pour 9 500 auteurs), gardé en cache sous une
  clé qui résume les auteurs (nombre, dernier, longueur des noms, ORCID, paires déclarées
  distinctes) : recompté seulement quand ils changent. **Notifications** : les messages Django s'affichent en
  toasts (`static/js/toasts.js`). **Boutons occupés** (`static/js/busy.js`, #339) : à
  l'envoi d'un formulaire POST, ses boutons sont désactivés (après la lecture du bouton
  cliqué, dont la valeur compte : « à lire ») et celui qui a été cliqué remplace son icône
  par une animation ; ils se réactivent au retour par l'historique. Sans JavaScript, rien
  ne change.
- **Ajouter une publication** (`_add_publication.html`, #277) : un seul composant, sur
  l'accueil, « Mon corpus » et « Publications » : DOI, ISBN ou arXiv, « Ajouter à mon corpus »
  (avec la bibliographie) ou « Ajouter à lire » (sans, #234) ; retour à la page du
  formulaire. Une publication sans identifiant se saisit à la main
  (`/publications/new/`), dans la base seulement.
- **Rapport d'import** (`_import_report.html`, `services/corpus/import_reports.py`, #330) :
  après l'import d'un fichier, un seul toast court ; le détail (publications ajoutées avec
  leur lien, déjà présentes, sans métadonnées, entrées ignorées et pourquoi, 20 par liste)
  est gardé en session et reste en tête de « Mon corpus » jusqu'à sa fermeture.
- **Retirer du corpus** (`_corpus_remove_form.html`, tableaux et fiche) : immédiat, sauf si
  l'entrée a des tags, un statut de lecture ou une note, que le retrait efface : le bouton
  ouvre alors une confirmation en popover, et le message dit ce qui a été perdu (#280,
  #283). `corpus_ids` rend ces entrées en une requête (`CorpusIds.with_tags`,
  `with_status`, `with_note`, sans lire le texte des notes).
- **Note** (#283) : sur la fiche d'une publication de mon corpus, une carte « Ma note » en
  tête de la colonne de droite, un champ de texte libre enregistré par un bouton (vide, la
  note est effacée). Privée : seul son auteur la voit. Cherchée par `note:` dans la
  recherche, exportée en JSON (`note`, version 3) et en BibTeX (`annote`).
- **Citer** (`_citation_panel.html`, `services/display/citations.py`, #286) : sur la fiche,
  un popover donne la référence en APA (7ᵉ édition) et en IEEE, et l'entrée BibTeX de la
  publication seule (`bibtex_entry` de l'export du corpus). Les citations sont mises en
  forme sur le serveur, à partir de la base : auteurs canoniques dans l'ordre de signature,
  titre lisible, année, et revue, volume, numéro, pages et éditeur de la réponse Crossref
  gardée ; une prépublication arXiv est citée par son identifiant. Le popover s'ouvre et se
  ferme sans JavaScript, le texte reste sélectionnable ; `static/js/copy_citation.js`
  ajoute « Copier » (HTML, qui garde l'italique, et texte brut ; texte brut pour BibTeX).
- **Tableau commun des publications** (`_publication_table.html`), utilisé par la liste
  des publications, « Mon corpus », « Cité par » et la page d'un auteur.
  `services/display/publication_table.py` (`for_publication_table`) calcule dans la même requête ce
  qu'il affiche à côté du titre : le premier auteur (« et al. » s'il y en a d'autres,
  sans la colonne sur la page d'un auteur), les références à identifier, les métadonnées
  manquantes et les références non importées. Ces valeurs sont des sous-requêtes, pour
  que les jointures ne multiplient pas les décomptes.
- **Listes paginées** (#154, `views/pagination.py`) : les publications, « Mon
  corpus » et les auteurs par pages de 50. Les annotations du tableau ne sont
  calculées que pour la page, et le nombre de requêtes ne dépend pas de la taille de la
  base. Le tri finit sur l'identifiant, pour que des lignes de même date ou de même nom
  ne passent pas d'une page à l'autre. Une page invalide ou au-delà de la dernière mène
  à la première ou à la dernière plutôt qu'à une erreur 404 : après le retrait de la
  dernière ligne d'une page, le retour sur cette page fonctionne encore. Le composant
  `{% pagination %}` garde les autres paramètres de l'URL (tri, filtres) ; sous `sm`, il
  ne montre que les lignes affichées et les liens Précédente et Suivante.
- **Tri par colonne** (#115, `services/display/sorting.py`) : `?sort=year`, `?sort=-year`,
  côté serveur et avant la pagination, donc sur toute la liste. Publications par titre,
  premier auteur (nom de famille) ou année ; « Mon corpus » aussi par statut de lecture et
  par date d'ajout (`?sort=-added`, #281 : sans colonne, un lien « Dernières ajoutées
  d'abord » au-dessus du tableau) ; auteurs par nom ou prénom. Les noms et les
  titres sont comparés sans casse ni accents (`normalized()`), les publications sans
  date ou sans auteur restent à la fin dans les deux sens, et les égalités sont toujours
  départagées dans le même ordre, jusqu'à l'identifiant. `{% column_header %}` fait de
  l'en-tête un lien (`aria-sort`, flèche) : un clic sur la colonne triée inverse l'ordre,
  un clic sur une autre colonne commence par son sens naturel (années récentes d'abord,
  noms de A à Z), et revient à la première page en gardant la recherche. Sans `sorting`
  dans le contexte (page d'un auteur, « Cité par »), les en-têtes restent simples.
- **Filtres par colonne** (#115, `services/display/filters.py`), comme dans un tableur : un
  entonnoir dans l'en-tête ouvre un panneau avec le champ de la colonne. Publications :
  titre et auteurs (texte contenu, sans casse ni accents), identifiant (avec DOI, avec
  ISBN, sans identifiant), années (de, à). Auteurs : nom, prénom (texte), ORCID (avec,
  sans). Chaque filtre a ses paramètres d'URL (`?title=…&year_from=2018`) : le tri, la
  pagination et les autres filtres le gardent, et le formulaire d'une colonne reprend
  les autres en champs cachés. Le panneau est un `popover` HTML : affiché au-dessus de
  la page, la carte qui fait défiler le tableau ne le coupe pas ; sans JavaScript, il se
  ferme par Échap ou un clic à l'extérieur. Il est placé sous son bouton par le
  positionnement par ancre CSS (ancre implicite du bouton qui l'ouvre, retourné près du
  bord droit), au milieu de l'écran dans un navigateur qui ne le connaît pas. L'entonnoir
  d'un filtre actif est bleu ; `{% filter_summary %}` liste les filtres actifs au-dessus
  du tableau, chacun retiré d'un clic, et les erreurs (année mal écrite). Un tableau
  filtré sans résultat reste affiché, pour changer les filtres. La recherche (`/search/`)
  et la page d'un auteur n'ont pas de filtres.
- **Recherche** (#153, `services/display/search.py`, `/search/?q=…`) : une seule barre, du
  texte libre et des opérateurs, `auteur:Felice titre:"champ magnétique"
  année:2020..2024 doi:10.1109`. Le texte libre cherche dans les titres, les noms des
  auteurs et les identifiants ; les mots d'un `auteur:` doivent appartenir à la même
  personne ; un `titre:` entre guillemets est une expression ; `note:` cherche dans les
  notes de mon corpus (#283), aucune pour un visiteur, à qui la page dit de se connecter. Un opérateur inconnu reste
  du texte (« Re:thinking ») ; une année mal écrite est signalée sans bloquer le reste.
  Résultats : les publications par pages, et les 20 premiers auteurs (sauf si la
  question porte sur des titres, des années ou des identifiants). Les comparaisons
  ignorent la casse et les accents grâce à `normalized()`, une fonction SQL enregistrée
  sur chaque connexion SQLite (`connection_created`) : le `LIKE` de SQLite ne replie que
  l'ASCII, et il n'a pas d'`unaccent`. Les titres sont cherchés, filtrés et triés sur leur
  forme lisible (`readable_title`, #264) : sa décomposition NFKD ramène les indices à des
  chiffres, si bien que « Nb3Sn » trouve « Nb₃Sn », écrit `Nb$_{3}$Sn` par la source. La barre est dans l'en-tête de toutes les pages
  (une icône vers `/search/` sous `md`) ; l'accueil et la page de recherche ont la leur,
  plus grande, avec l'aide de la syntaxe. Ctrl+K (⌘K sur Mac) y place le curseur, ou
  ouvre la page de recherche quand aucune barre n'est affichée (`static/js/search.js`).
- **Accueil** (#151, #278, `services/display/dashboard.py`) : connecté, « Bonjour » et la
  taille du corpus, le formulaire d'ajout en tête (#277), puis un tableau de bord : mon
  corpus (statuts de lecture, derniers ajouts sur une ligne avec leur statut), « À faire »
  en phrases avec un verbe (identifier des références, trancher des conflits, examiner des
  auteurs en double), « À lire ensuite » (en cours, puis « à lire » les plus anciennes) ;
  pour tous, la base commune : ses chiffres, des liens vers ses pages et les publications
  ajoutées récemment à un corpus (pas les références importées en masse). La recherche est
  celle de l'en-tête, comme ailleurs. Nombre de requêtes constant.
- **Mise en page fluide** (#150), la même sur tous les écrans : aucune page ne déborde
  horizontalement de 390 à 1400 px. Sur petit écran, chaque groupe de la navigation
  devient un menu (#207 : `<details name>` natifs, ouverts au toucher ou au clic, un seul
  à la fois, fermés par un clic à l'extérieur ou Échap via `static/js/navigation.js`), les
  boutons de l'en-tête n'affichent que leur icône (`compact`), les tableaux
  défilent dans leur carte et la colonne Identifiant est masquée sous `xl`.
- HTML5 sémantique, validé au W3C en fin de jalon.
