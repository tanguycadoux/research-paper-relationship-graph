# Interface

Organisation des pages et des listes. Les conventions d'écriture des templates (couche
`base` de Tailwind, composants, liens externes, icônes) sont dans
[CONTRIBUTING.md](../CONTRIBUTING.md#interface). Vue d'ensemble du projet :
[architecture.md](architecture.md).

- **Tailwind**, compilé par django-tailwind-cli depuis `assets/css/source.css`, sans Node.
  Les styles par défaut des éléments sont définis une fois dans la couche `base`.
- **Composants** en template tags (`references/templatetags/ui/`) : `button`, `badge`,
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
  toasts (`static/js/toasts.js`), d'une phrase ; à partir de `md`, en bas de la colonne de
  navigation et de sa largeur, pour ne pas cacher les boutons des dernières lignes d'un
  tableau ; en dessous, en bas de l'écran (#411). **Accords** : 0 et 1 prennent le
  singulier, en Python avec `wording.count` (« 0 publication ajoutée ») et dans les
  templates avec le filtre `pluralize_fr` de `{% load ui %}` (`|pluralize` de Django met 0
  au pluriel). **Boutons occupés** (`static/js/busy.js`, #339) : à
  l'envoi d'un formulaire POST, ses boutons sont désactivés (après la lecture du bouton
  cliqué, dont la valeur compte : « à lire ») et celui qui a été cliqué remplace son icône
  par une animation ; ils se réactivent au retour par l'historique. Sans JavaScript, rien
  ne change.
- **Titres de page** (#417) : le `<h1>` d'une page du menu est son groupe de la
  navigation, le `<h2>` qui le suit est la page, sur le modèle de « Mon corpus »
  (« Mon corpus », puis « Publications (26) ») : « Corrections », puis « Conflits » ;
  « Base commune », puis « Auteurs (1 204) ». Le `<h2>` porte son compteur en gris et, à
  droite sur la même ligne, une action de la page s'il y en a une ; le paragraphe
  d'explication est dessous ; les sections de la page descendent d'un niveau (`<h3>`,
  `{% card title=… level=3 %}`, puis `<h4>`), dont le style par défaut est dans la couche
  `base`. Les pages atteintes depuis le menu prennent le groupe de leur page d'origine,
  dont le lien reste au-dessus de leur `<h2>` : « Tags » (Mon corpus), « Graphe des
  publications », « Graphe des auteurs », « Chercher par titre », « Saisir une
  publication à la main » (Base commune), « Fusionner 3 auteurs » (Corrections). Le
  `<title>` suit : « Conflits · Corrections · Gestionnaire de références ». Les boutons
  d'en-tête restent à droite du `<h1>` : ce sont des liens vers d'autres pages du groupe
  (« Suggestions » et « Mon graphe » sur « Mon corpus », avec le tag choisi ;
  « Publications » pour revenir de « Suggestions » ou « Tags » ; « Graphe des
  publications », « Graphe des auteurs »). Gardent leur propre `<h1>`, avec leur fil :
  les fiches d'une publication et d'un auteur, leurs graphes et leurs modifications,
  l'identification d'une référence, la recherche, l'accueil. `test_page_titles.py`
  vérifie pour chaque page du menu un seul `<h1>`, égal au groupe, le `<h2>` de la page,
  aucun saut de niveau et le `<title>`.
- **Ajouter une publication** (`_add_publication.html`, #277) : un seul composant, sur
  l'accueil, « Mon corpus » et « Publications » : DOI, ISBN ou arXiv, « Ajouter à mon corpus »
  (avec la bibliographie) ou « Ajouter à lire » (sans, #234) ; retour à la page du
  formulaire. Une publication sans identifiant se saisit à la main
  (`/publications/new/`), dans la base seulement.
- **Rapport d'import** (`_import_report.html`, `services/corpus/import_reports.py`, #330) :
  après l'import d'un fichier, un seul toast court ; le détail (publications ajoutées avec
  leur lien, déjà présentes, sans métadonnées, entrées ignorées et pourquoi, 20 par liste)
  est gardé en session et reste en tête de « Mon corpus » jusqu'à sa fermeture. Sa
  première ligne compte toutes les publications ajoutées, celles en file de récupération
  comprises (« 2 publications ajoutées à votre corpus ; leurs données arrivent en
  arrière-plan »), et n'écrit pas de compte à zéro (#411).
- **Exporter** (carte « Exporter et importer » de « Mon corpus », #285) : sans filtre, les
  boutons exportent tout le corpus (« JSON (réimportable) », « BibTeX ») ; avec des filtres
  (tag et ses sous-tags, colonnes, « à identifier »), ils exportent les publications
  affichées, toutes pages comprises, et le disent (« BibTeX des 12 publications
  affichées ») ; deux liens gardent l'export de tout le corpus. Aucun résultat : les
  boutons restent en place, désactivés. Les vues d'export lisent les mêmes paramètres que
  le tableau, par la même fonction (`filters.filtered_corpus`) ; le tri et la page sont
  ignorés. Le fichier s'appelle `corpus-<tag>-<date>` pour un tag seul,
  `corpus-selection-<date>` pour d'autres filtres ; son format est celui de l'export
  complet, il se réimporte de même.
- **Retirer du corpus** (`_corpus_remove_form.html`, tableaux et fiche) : immédiat, sauf si
  l'entrée a des tags, un statut de lecture ou une note, que le retrait efface : le bouton
  ouvre alors une confirmation en popover, et le message dit ce qui a été perdu (#280,
  #283). `corpus_ids` rend ces entrées en une requête (`CorpusIds.with_tags`,
  `with_status`, `with_note`, sans lire le texte des notes).
- **Note** (#283) : sur la fiche d'une publication de mon corpus, une carte « Ma note » en
  tête de la colonne de droite, un champ de texte libre enregistré par un bouton (vide, la
  note est effacée). Privée : seul son auteur la voit. Cherchée par le texte libre et par `note:` dans la
  recherche, exportée en JSON (`note`, version 3) et en BibTeX (`annote`).
- **Citer** (`_citation_panel.html`, `services/display/citations.py`, #286) : sur la fiche,
  un popover donne la référence en APA (7ᵉ édition) et en IEEE, et l'entrée BibTeX de la
  publication seule (`bibtex_entry` de l'export du corpus). Les citations sont mises en
  forme sur le serveur, à partir de la base : auteurs canoniques dans l'ordre de signature,
  titre lisible, année, et revue, volume, numéro, pages et éditeur de la réponse Crossref
  gardée ; une prépublication arXiv est citée par son identifiant. Le popover s'ouvre et se
  ferme sans JavaScript, le texte reste sélectionnable ; `static/js/copy_citation.js`
  ajoute « Copier » (HTML, qui garde l'italique, et texte brut ; texte brut pour BibTeX).
  L'entrée BibTeX revient à la ligne dans le panneau (`whitespace-pre-wrap`) ; la copie
  prend son `textContent`, sans ces retours à la ligne d'affichage (#413).
- **Métadonnées brutes** (`/publications/<pk>/metadata/`, `publication_metadata.html`,
  #413) : une carte par source, le JSON indenté et replié à la largeur de la carte, même
  dans une longue chaîne (`wrap-anywhere`) ; `?format=json` rend le JSON lui-même.
- **Actions groupées** (`_bulk_actions.html`, `views/corpus_bulk.py`,
  `services/corpus/bulk.py`, #287) : dans « Mon corpus », une case par ligne et, au-dessus
  du tableau, une barre pour ajouter un tag, changer le statut de lecture ou retirer du
  corpus (confirmation en popover) les publications cochées. Les cases appartiennent au
  formulaire de la barre par l'attribut `form=` (chaque ligne contient déjà le formulaire
  de son statut). Le serveur refuse tout, sans rien changer, si rien n'est coché ou si une
  publication cochée n'est pas dans le corpus de l'utilisateur. Quitter « à lire » importe
  les bibliographies comme pour une seule publication (par la file avec un worker).
  `static/js/bulk_actions.js` compte les cases cochées, montre la case « Tout cocher » et
  désactive les boutons tant que rien n'est coché ; sans lui, la barre fonctionne. Le
  champ du tag propose, par une `<datalist>` (`tags.suggested_paths`), les tags de
  l'utilisateur et leurs parents, comme le champ de tag de la fiche.
  Sur la fiche d'une publication (#408), connecté, les listes « Références » et « Cité
  par » ont chacune leur barre (`form_id` distinct : `references-actions`,
  `cited-by-actions`), envoyée à `publication_bulk`, avec en plus « Ajouter à mon
  corpus », qui donne aussi le tag et le statut choisis. Seules les références
  identifiées ont une case, y compris dans la partie dépliée (`?references=toutes`). Le
  mélange de publications dans et hors du corpus y étant normal, l'ajout compte à part
  celles qui y étaient déjà (elles reçoivent le tag, gardent leur statut), et les autres
  actions laissent de côté celles qui n'y sont pas, en le disant ; rien n'est fait si
  aucune n'y est. Seules les publications que ces listes montrent sont prises en compte.
  Retour à la liste par `next` (`#references-title` ou `#cited-by-title`), vérifié par
  `url_has_allowed_host_and_scheme`. Le message d'un retrait groupé dit ce qui est perdu
  (« avec 2 tags, 1 statut de lecture et 1 note »).
  Sur la fiche, les deux barres sont repliées (`collapsed=True`, #410) : tant que rien
  n'est coché, le script n'en montre que la première ligne, qui dit à quoi servent les
  cases ; elle se déplie pour de bon à la première case cochée (décochée ensuite, ses
  boutons sont désactivés, pas masqués). Les contrôles et l'aide sont dans la partie
  repliée (`data-bulk-more`) : l'aide ne s'affiche que dans une barre dépliée. Sans
  JavaScript, les barres restent dépliées. Celle de « Mon corpus » n'est jamais repliée.
- **Tableau commun des publications** (`_publication_table.html`), utilisé par la liste
  des publications, « Mon corpus », « Cité par » et la page d'un auteur.
  `services/display/publication_table.py` (`for_publication_table`) calcule dans la même requête ce
  qu'il affiche à côté du titre : le premier auteur (« et al. » s'il y en a d'autres,
  sans la colonne sur la page d'un auteur), les références à identifier, les métadonnées
  manquantes et les références non importées. Ces valeurs sont des sous-requêtes, pour
  que les jointures ne multiplient pas les décomptes.
  Sous `sm`, les colonnes Auteurs et Année sont résumées sous le titre (#334) ; dans
  « Mon corpus », la colonne Lecture aussi : la liste du statut est sous le titre, à côté
  de ce résumé (#412). Le formulaire du statut est alors deux fois dans la ligne, l'un
  masqué selon la largeur ; celui sous le titre a ses propres identifiants
  (`id_suffix="-compact"`). Le tri par ces colonnes reste dans `{% sort_links %}` ; leurs
  filtres actifs restent dans le résumé des filtres.
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
  auteurs, les identifiants et les notes de l'utilisateur connecté (#416), jamais
  dans celles des autres ; une publication qu'un mot ne trouve que dans ma note porte le
  badge « trouvée dans votre note ». Les mots d'un `auteur:` doivent appartenir à la même
  personne ; un `titre:` entre guillemets est une expression ; `note:` cherche seulement dans les
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
