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
  (`popover_panel_classes`). **Navigation** décrite dans
  `templatetags/navigation.py`, avec des **compteurs** de ce qui attend une action
  (#152, `services/pending.py`) : références à identifier dans son corpus, conflits
  ouverts. Une requête par compteur, sans cache, pour qu'un compteur soit juste aussitôt
  après l'action ; rien n'est affiché à zéro. Les doublons probables n'ont pas de
  compteur : des suggestions, nombreuses (55), pas des tâches. **Notifications** : les messages Django s'affichent en
  toasts (`static/js/toasts.js`).
- **Tableau commun des publications** (`_publication_table.html`), utilisé par la liste
  des publications, « Mes références », « Cité par » et la page d'un auteur.
  `services/publication_table.for_publication_table` calcule dans la même requête ce
  qu'il affiche à côté du titre : le premier auteur (« et al. » s'il y en a d'autres,
  sans la colonne sur la page d'un auteur), les références à identifier, les métadonnées
  manquantes et les références non importées. Ces valeurs sont des sous-requêtes, pour
  que les jointures ne multiplient pas les décomptes.
- **Listes paginées** (#154, `views/pagination.py`) : les publications, « Mes
  références » et les auteurs par pages de 50. Les annotations du tableau ne sont
  calculées que pour la page, et le nombre de requêtes ne dépend pas de la taille de la
  base. Le tri finit sur l'identifiant, pour que des lignes de même date ou de même nom
  ne passent pas d'une page à l'autre. Une page invalide ou au-delà de la dernière mène
  à la première ou à la dernière plutôt qu'à une erreur 404 : après le retrait de la
  dernière ligne d'une page, le retour sur cette page fonctionne encore. Le composant
  `{% pagination %}` garde les autres paramètres de l'URL (tri, filtres) ; sous `sm`, il
  ne montre que les lignes affichées et les liens Précédente et Suivante.
- **Tri par colonne** (#115, `services/sorting.py`) : `?sort=year`, `?sort=-year`,
  côté serveur et avant la pagination, donc sur toute la liste. Publications par titre,
  premier auteur (nom de famille) ou année ; auteurs par nom ou prénom. Les noms et les
  titres sont comparés sans casse ni accents (`normalized()`), les publications sans
  date ou sans auteur restent à la fin dans les deux sens, et les égalités sont toujours
  départagées dans le même ordre, jusqu'à l'identifiant. `{% column_header %}` fait de
  l'en-tête un lien (`aria-sort`, flèche) : un clic sur la colonne triée inverse l'ordre,
  un clic sur une autre colonne commence par son sens naturel (années récentes d'abord,
  noms de A à Z), et revient à la première page en gardant la recherche. Sans `sorting`
  dans le contexte (page d'un auteur, « Cité par »), les en-têtes restent simples.
- **Filtres par colonne** (#115, `services/filters.py`), comme dans un tableur : un
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
- **Recherche** (#153, `services/search.py`, `/search/?q=…`) : une seule barre, du
  texte libre et des opérateurs, `auteur:Felice titre:"champ magnétique"
  année:2020..2024 doi:10.1109`. Le texte libre cherche dans les titres, les noms des
  auteurs et les identifiants ; les mots d'un `auteur:` doivent appartenir à la même
  personne ; un `titre:` entre guillemets est une expression. Un opérateur inconnu reste
  du texte (« Re:thinking ») ; une année mal écrite est signalée sans bloquer le reste.
  Résultats : les publications par pages, et les 20 premiers auteurs (sauf si la
  question porte sur des titres, des années ou des identifiants). Les comparaisons
  ignorent la casse et les accents grâce à `normalized()`, une fonction SQL enregistrée
  sur chaque connexion SQLite (`connection_created`) : le `LIKE` de SQLite ne replie que
  l'ASCII, et il n'a pas d'`unaccent`. La barre est dans l'en-tête de toutes les pages
  (une icône vers `/search/` sous `md`) ; l'accueil et la page de recherche ont la leur,
  plus grande, avec l'aide de la syntaxe. Ctrl+K (⌘K sur Mac) y place le curseur, ou
  ouvre la page de recherche quand aucune barre n'est affichée (`static/js/search.js`).
- **Accueil** (#151, `services/dashboard.py`) : connecté, un tableau de bord (mon corpus
  et ses dernières publications ajoutées, « À faire » avec les références à identifier,
  les conflits ouverts et les doublons probables, base commune) ; visiteur, une
  présentation et les chiffres de la base. Nombre de requêtes constant.
- **Mise en page fluide** (#150), la même sur tous les écrans : aucune page ne déborde
  horizontalement de 390 à 1400 px. Sur petit écran, chaque groupe de la navigation
  devient un menu (#207 : `<details name>` natifs, ouverts au toucher ou au clic, un seul
  à la fois, fermés par un clic à l'extérieur ou Échap via `static/js/navigation.js`), les
  boutons de l'en-tête n'affichent que leur icône (`compact`), les tableaux
  défilent dans leur carte et la colonne Identifiant est masquée sous `xl`.
- HTML5 sémantique, validé au W3C en fin de jalon.
