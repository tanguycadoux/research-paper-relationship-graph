# Graphes

Les graphes de citations, le [graphe des auteurs](#graphe-des-auteurs-222) (coautorat) et la [carte des mots-clés](#carte-des-mots-clés-418) : données produites par le serveur, dessin et interactions dans le navigateur. Vue d'ensemble du projet : [architecture.md](architecture.md).

**Décision : le serveur fournit les données, le navigateur dessine.**

- Trois graphes : celui d'une **publication** montre ses références identifiées et les
  publications de la base qui la citent (#186) ; celui du **corpus** montre les
  publications du corpus et ce qu'elles citent ; celui de **la base** (#131, `/publications/graph/`,
  public comme la liste des publications, ouvert depuis elle par « Graphe des
  publications », sans entrée de menu comme celui des auteurs, #391) montre toutes les publications, y compris
  celles sans citation identifiée, et toutes les citations identifiées. Les publications
  du corpus de la personne connectée y sont en bleu (`source`), les autres en vert d'eau
  (`other`). Les liens sont dédoublonnés sans le tri par défaut (`order_by()`), sans quoi
  la position rendait distinctes deux citations d'une même publication.
- **Graphe d'un tag** (#290) : « Mon graphe » peut se limiter à un tag et ses sous-tags
  (`?tag=Projet`), choisi dans une liste du panneau du graphe (envoyée dès qu'elle change,
  `static/js/autosubmit.js`, avec un bouton sans JavaScript). Le contexte est celui des
  suggestions : `tags.context_publications`, et un tag qui n'existe plus ramène à tout le
  corpus avec un message (`views/tag_context.requested_tag`, partagé avec les
  suggestions). « Mon corpus » filtré par un tag renvoie au graphe de ce tag, et le
  nom de l'image exportée le dit (`graphe-corpus-tag-projet`).
- `services/display/graph.py` produit les éléments Cytoscape. Les nœuds portent le titre lisible (#264), la date,
  la revue, le premier auteur et le nombre d'auteurs, le nombre de citations dans la
  base et le lien vers la fiche. Les arêtes vont de la publication qui cite vers la
  publication citée. Trois requêtes, quelle que soit la taille du graphe (publications,
  citations, auteurs par `Prefetch`), une de plus pour le corpus sur le graphe de la base.
- La vue intègre ces données dans la page avec `json_script`, sans route JSON séparée.
  Les modules ES de `references/static/references/graph/` les affichent sur une frise
  chronologique : l'axe horizontal suit la date, et les articles non datés sont dans une
  bande sous la frise. Ou en **réseau**, sans axe du temps (#195, voir plus bas).
- **Disposition** (#138, `layout.js`) : x suit la date ; la position verticale rapproche
  les publications qui se citent, sans dépendance. Chaque **groupe** de publications
  reliées par des citations (composante connexe, #230) est disposé seul : d'abord un
  **ordre** par la méthode du barycentre (chaque publication va vers la rangée moyenne de
  ses voisines, en 20 passes), puis une petite **simulation verticale** : les
  publications liées s'attirent, une publication s'écarte des liens qui passent sur elle
  (aucun lien caché derrière un nœud), et deux publications proches en date ne se
  chevauchent pas (écart selon leur taille). Les rangées de départ sont espacées de
  36 px quelle que soit la taille du cadre : la disposition ne dépend pas de la fenêtre.
- **Groupes empilés** (#230) : les groupes se suivent de haut en bas, le plus grand en
  premier, séparés par un écart qui n'est pas comprimé (32 px, et tous les écarts ensemble
  au plus le quart de la hauteur). Des domaines sans lien entre eux (aimants
  supraconducteurs, apprentissage profond, cancer…) ne s'entremêlent plus. Ensemble, ils
  sont ramenés à la hauteur du cadre, chacun en proportion de sa hauteur, étirés ou
  comprimés : les nœuds gardent leur taille à l'écran, un dézoom ne les séparerait pas et
  perdrait de la largeur ; zoomer sépare ceux que la compression rapproche (#185). Les
  publications **sans aucun lien** vont, à leur date, sur des rangées sous les groupes
  (`packRows` : la première rangée où elles ne recouvrent personne). Sur le graphe de la
  base de développement (76 publications, trois groupes) : 67 croisements de liens au lieu
  de 78 quand les groupes étaient disposés ensemble.
- **Rapidité** (#202, mesures dans [banc-graphe.md](banc-graphe.md)) : la simulation ne
  parcourt que les couples assez proches pour agir. Les couples publication / lien et les
  couples de publications proches en date plus loin que leur portée (64 px) plus une marge
  (64 px) sont mis de côté. Ils sont cherchés à nouveau quand l'un d'eux a pu entrer à
  portée (`stillApart` : le mouvement depuis la dernière recherche est séparé en une
  contraction d'ensemble, qui rapproche lentement les publications proches, et un reste),
  et au plus toutes les 10 itérations : un grand groupe ne s'immobilise jamais tout à
  fait. Pour trouver les publications sous un lien sans les parcourir toutes, elles sont
  rangées par blocs de 32 dates voisines, triés par y (`nearEdges`). Sur la base du banc
  (1 797 publications) : 0,3 s au lieu de 11,2 s, pour un résultat équivalent
  (49 838 croisements, contre 50 436 avec une recherche exacte à chaque itération).
- **Publications non datées** (#288, `layout.js`, `band.js`) : sur une rangée sous la
  frise, séparée par une ligne pointillée libellée « Non daté ». Elles traversaient toute
  la frise depuis une colonne à gauche, avec des liens dont le sens ne se lisait plus.
  Les publications datées sont disposées entre elles comme d'habitude. Une non datée est
  placée d'après ses **sœurs**, les autres références datées des articles qui la citent :
  une référence a à peu près l'âge des autres références du même article. Pour chaque
  article qui la cite, le milieu de ses références datées (ou l'article lui-même s'il
  n'en a pas d'autre) ; on garde **le plus ancien de ces milieux**, puisqu'une référence
  est plus ancienne que tous les articles qui la citent. Une publication est plus
  récente que ses propres références : jamais avant la plus récente qu'elle cite, et
  c'est là qu'elle va si rien de daté ne la cite. Sans aucun lien daté, elles sont
  réparties sur la largeur (`bandX`). Trop nombreuses pour une seule rangée, elles en
  prennent plusieurs, au plus quatre (#318) : chacune va sur la première rangée où elle
  tient à sa place ; au-delà de quatre, elle est poussée le long de la rangée qui finit le
  plus à gauche (`packRows`). La frise
  commence à l'année la plus ancienne, et l'axe ne montre que des années. La ligne de la
  bande suit le zoom, le déplacement et l'étirement d'une sélection, comme l'axe. Les liens
  restent sans flèche, comme les autres.
- **Vue « Réseau »** (#195, `network.js`, `services/display/graph_variants.py`) : sans axe
  du temps, les publications qui se citent sont rapprochées dans les deux directions. Un
  sélecteur « Disposition : Frise | Réseau » du panneau, sous les commandes et au-dessus
  du tag, choisit la vue ; le choix est dans l'URL (`?vue=reseau`), la frise par défaut,
  et une valeur inconnue ramène à la frise. Rien n'est gardé sur le serveur : une vue se
  partage et se compare dans deux onglets. Les liens du sélecteur gardent les autres
  paramètres (`?tag=`), et le formulaire du tag garde le réseau (champ caché,
  `graph_kept_params`). Une variante se déclare une fois dans `graph_variants.py`
  (paramètre, libellé, choix, le défaut en premier) ; `main.js` lit les valeurs choisies
  (`#citation-graph-layout`). Le style, la sélection, le panneau, la légende et l'export
  sont les mêmes ; l'axe des années et la bande « Non daté » n'existent pas, et l'aide le
  dit. **Disposition** : `cose`, la disposition à forces de Cytoscape, sans dépendance.
  Elle part d'une spirale (angle d'or, dans l'ordre des données) plutôt que de positions au
  hasard : le même graphe est disposé de la même façon à chaque visite. Les tailles des
  nœuds sont celles de l'écran (au zoom 1 de la disposition). Le refroidissement est plus
  rapide que par défaut (`coolingFactor` 0,9 : 66 itérations au lieu de 690), avec une
  répulsion doublée qui compense une partie des recouvrements : 2,9 s au lieu de 27 s sur
  1 797 publications, 20 ms sur 76 ([banc-graphe.md](banc-graphe.md)). Les groupes sans
  lien sont rangés par `cose` lui-même, côte à côte. **Au-delà de 600 éléments** (#202,
  même seuil que les grands graphes), `cose` tourne dans un **Web Worker**
  (`network-worker.js`, Cytoscape sans affichage, chargé depuis la même URL que la page) :
  le cadre affiche « Disposition du graphe… » (`data-graph-waiting`, `role="status"`),
  « Vue d'ensemble » et « Exporter (PNG) » sont désactivés jusqu'à ce que le graphe existe, et
  la page reste utilisable ; le graphe est créé avec les positions reçues. Les positions
  sont **les mêmes** qu'en disposant dans la page (vérifié sur la base du banc) : le worker
  reçoit les tailles des nœuds (`LAYOUT_STYLE`, celles de `style.js` au zoom 1, bordure
  comprise) et la taille du cadre, vers le centre duquel `cose` attire les nœuds ; il part
  de la spirale par une disposition `preset` (sans elle, Cytoscape poserait tous les nœuds
  en (0, 0), que `cose` séparerait au hasard). Si le worker échoue (navigateur sans worker
  de module, script introuvable), la disposition se fait dans la page, comme sous le
  seuil. Sous 600 éléments, `cose` prend moins de 100 ms environ : la disposition reste
  dans la page, sans message qui ne ferait que clignoter.
- **Style** (#139, #140, `style.js`) : la couleur d'un nœud dit son **rôle** (`role` dans
  les données) : `source` en bleu (la publication du graphe, ou celles du corpus),
  `citing` en orange (une publication qui la cite), `cited` en vert d'eau (citée
  seulement). Sa **taille** suit
  son nombre de citations dans la base (aire proportionnelle). Tailles des nœuds, épaisseurs
  des liens et libellés sont **fixes à l'écran** (#185) : divisées par le zoom, réévaluées
  au plus une fois par image (`requestAnimationFrame`) quand le zoom change, ou à l'arrêt
  du zoom sur un grand graphe (voir « Grands graphes »). Zoomer écarte
  donc les nœuds sans les grossir, ce qui sépare les publications proches en date. Les couleurs sont définies
  une seule fois, en variables de thème Tailwind (`--color-graph-*` dans
  `assets/css/source.css`) : la légende HTML utilise les classes, Cytoscape lit les
  variables. Palette vérifiée (daltonisme, contraste d'au moins 3:1 sur blanc). Liens au repos
  droits, gris, sans flèche : une
  publication cite des publications plus anciennes, à sa gauche. Survoler un nœud affiche
  son titre dans une **infobulle HTML** (`hover.js`, `data-graph-tooltip`) au-dessus du
  nœud (en dessous s'il n'y a pas la place), centrée sur lui et gardée dans le cadre ; elle
  disparaît quand la souris quitte le nœud ou le cadre, au début d'un clic ou d'un glisser
  et à tout mouvement de la vue. Plus lisible qu'un libellé dans le canevas, que d'autres
  nœuds pouvaient couvrir. Le survol fonce aussi ses liens, sauf sur un grand graphe (voir
  « Grands graphes »). Seuls les nœuds réagissent à la souris : un lien ne se survole ni ne se clique
  (`events: no`), et Cytoscape ne dessine plus son halo carré au clic. Le nœud sélectionné
  porte un anneau sombre ; un halo rond discret (`underlay`) ne l'entoure que tant que la
  souris est enfoncée (`:active`).
- **Vue** (#141, `viewport.js`) : la vue d'ensemble (tout le graphe dans le cadre, avec
  une petite marge) est le zoom minimal, recalculé quand le cadre change de taille, et
  la vue ne sort jamais de cette emprise : le déplacement est ramené dans les bornes à
  chaque événement `viewport`. L'axe n'affiche donc jamais d'années vides.
  Le bouton « Vue d'ensemble » du panneau y revient (#196), par le même cadrage que le
  chargement et le redimensionnement. Il est désactivé (grisé), plutôt que masqué, quand
  la vue d'ensemble est déjà affichée : il reste visible et à sa place.
- **Axe des années** : une bande HTML au-dessus du canevas (`#citation-graph-axis`),
  redessinée à chaque événement `viewport` de Cytoscape et à chaque étirement d'une
  sélection (voir plus bas), qu'elle suit : les années restent sous les nœuds. Le pas des graduations dépend de
  la place à l'écran (au moins 60 px entre deux libellés), pas de la plage d'années (#62).
- **Sélection** (#61) : un clic sur un article met en évidence ses références (nœuds
  vert d'eau) et les articles qui le citent (nœuds orange), chaque lien dans une nuance
  plus claire de son nœud, et estompe le reste. La carte d'informations HTML
  (`#citation-graph-card`) est compacte (#187) : le titre est le lien vers la fiche, puis
  la revue (lue dans la réponse stockée de Crossref ou de DataCite, dans la même
  requête), le premier auteur et l'année, et les compteurs. Un double-clic ouvre la
  fiche ; Échap, un clic dans le vide ou le bouton « Désélectionner » de la carte
  désélectionne.
- **Panneau** (#291) : **hors du cadre**, toujours présent, il ne cache aucune
  publication. Le cadre et le panneau forment **une seule carte**, séparés par une
  bordure, sans espace entre eux : à partir de `xl`, le panneau est une colonne de 20rem
  à droite du cadre (`border-l`), qui prend la hauteur du cadre et défile à l'intérieur si
  son contenu dépasse (il ne rend jamais la carte plus haute) ; en dessous, il est sous le
  cadre (`border-t`). Dans l'ordre : les **commandes** (« Vue d'ensemble », « Exporter
  (PNG) »), puis les contrôles du contexte (le tag de « Mon graphe », #290 ; restés au-dessus
  du message quand un tag n'a aucune citation), puis ce que montre le graphe (« 76 publications, 85 citations » et une
  indication) ou, avec une sélection, la carte de la publication, enfin la légende. Le
  mode d'emploi (lecture de l'axe ou du réseau, survol, clic, double-clic, Échap) est
  derrière le bouton « ? » au bout des commandes (#415) : un popover natif en verre dépoli
  (`_graph_help.html`, sans JavaScript), le même pour les graphes de citations et de
  coauteurs ; la légende reste visible, et c'est elle que reprend l'export PNG. Les
  commandes et les contrôles sont au-dessus de ce qui change de hauteur : rien
  ne bouge à la première sélection. Le cadre gagne la hauteur de la légende,
  et rien ne se superpose au graphe. Sous `xl`, le cadre a sa propre hauteur (70vh,
  24rem au moins) plutôt que l'espace restant : un panneau qui grandit ne le
  redimensionne jamais, ce qui ramènerait la vue d'ensemble ; les commandes sont alors
  sous le graphe.
- **Recentrage à la sélection** (#142, #291, `focus.js`, `stretch.js`) : l'article et
  ses voisins occupent **tout le cadre, en largeur et en hauteur** (animation de 300 ms,
  aucune avec « réduire les animations » ni sur un grand graphe). Cytoscape n'a qu'un zoom, le même sur les deux
  axes : le zoom remplit l'axe le plus serré (au plus 4 fois celui de la vue d'ensemble),
  puis le graphe est **étiré** sur l'autre axe, autour du centre de la sélection, jusqu'à
  le remplir aussi (au plus 4 fois). L'étirement déplace les positions, toujours
  recalculées depuis celles de la disposition : la désélection ramène exactement les
  positions et la vue d'avant (la vue d'ensemble dans le cas courant, un zoom fait à la
  main sinon). Étirer l'axe horizontal change l'échelle du temps le temps de la
  sélection ; la frise la suit. Limites : un axe où la sélection n'a pas d'étendue
  (voisins de la même année, ou de la même rangée) n'est pas étiré ; un article et un
  seul voisin ne remplissent que 60 % du cadre, sans quoi ils finiraient dans deux coins
  opposés. La vue visée reste dans les bornes de #141, étirées avec le graphe
  (`viewport.within`) : jamais en deçà du zoom de la vue d'ensemble, et décalée du
  minimum pour ne pas en sortir. Pendant l'animation, le maintien dans les bornes attend
  (`viewport.hold`), puis s'applique de nouveau ; un zoom ou un déplacement à la main
  pendant une sélection reste dans les bornes étirées. L'étirement ne vaut que pour la
  **frise**, où x n'est qu'une date : en **réseau** (#195), le zoom est uniforme, sans
  étirement, sans quoi il déformerait les distances qu'il dessine ; la sélection remplit
  l'axe le plus serré, et les positions ne bougent pas. Les règles des grands graphes
  (ci-dessous) s'appliquent de la même façon.
- **Animation du recentrage** (#291) : une seule boucle (`requestAnimationFrame`) déplace
  ensemble la vue et l'étirement. Ce qui est interpolé, c'est la plus petite des deux
  fenêtres de la disposition (celle d'arrivée quand on zoome, celle de départ quand on
  revient) : son rectangle à l'écran va de sa place à tout le cadre, ou l'inverse, avec
  son centre en ligne droite et sa largeur et sa hauteur en progression géométrique, au
  même rythme. Les deux axes se resserrent donc ensemble, et la sélection ne sort jamais
  du cadre en route : une moyenne géométrique reste sous la linéaire, si bien que chaque
  bord reste entre sa position de départ et celle d'arrivée. Le zoom (taille des nœuds,
  #185) progresse aussi géométriquement ; l'étirement fait le reste sur chaque axe. La
  dernière image est exactement la vue visée. Interpoler séparément le zoom et
  l'étirement, comme d'abord, désynchronisait les axes (la largeur suivait la hauteur
  avec retard) et faisait sortir la sélection du cadre à mi-course. Une nouvelle
  sélection, Échap ou « Vue d'ensemble » repart de la vue du moment ; un zoom ou un
  déplacement à la main arrête l'animation là où elle est. « Vue d'ensemble » pendant une
  sélection y revient par la même animation (un redimensionnement du cadre, sans).
- **Grands graphes** (#202, `viewport.js`, mesures dans [banc-graphe.md](banc-graphe.md)) :
  au-delà de **600 éléments** (nœuds et liens, `LIVE_SIZES_MAX_ELEMENTS`), le graphe ne
  suit plus le mouvement au même prix. Réévaluer le style coûte à Cytoscape environ
  0,03 ms par élément, quelle que soit la forme des valeurs (fonctions, ou valeurs
  recalculées pour le zoom et `mapData` : plus cher encore) : 135 ms pour les 4 300
  éléments d'un graphe de 1 800 publications, trois fois le dessin lui-même. Le seuil
  garde cette réévaluation sous 20 ms environ : sous lui, rien ne change (le graphe d'une
  base de 76 publications et 85 citations, 161 éléments, anime et zoome comme avant).
  Au-delà :
  - les tailles fixes à l'écran sont réévaluées **une fois le zoom arrêté** (150 ms sans
    changement) ; pendant le geste, elles grandissent avec le zoom, comme une image ;
  - la **sélection va directement à sa vue**, sans animation, les tailles réévaluées une
    fois : sans réévaluation à chaque image, l'animation ferait gonfler les nœuds jusqu'à
    4 fois (le zoom de la sélection) avant de les réduire ;
  - pendant un zoom à la molette ou un déplacement à la souris, Cytoscape déplace **une
    image** du graphe, liens compris (`textureOnViewport`, `rendererOptions`), et le
    redessine à la fin du geste ; au-delà de **5 000 éléments**, cette image est lente à
    son tour (32 images de plus de 50 ms pendant un zoom à 2 000 publications) : les
    **liens sont masqués** pendant le geste (`hideEdgesOnViewport`, 2 images lentes). Les
    deux gagnent autant jusqu'à 1 800 publications ; l'image garde les liens, d'où son
    choix sous ce seuil ;
  - le **survol** (`hover.js`) ne change aucune classe Cytoscape, ce qui redessinerait
    tout le canevas (40 ms à 1 000 publications, 140 ms à 2 000) : l'infobulle seule, les
    liens ne foncent pas. Le survol revient à 17 ms par image ;
  - en vue réseau, la disposition se fait dans un Web Worker (voir « Vue Réseau »).
  Limite connue : la réévaluation unique à la fin d'un zoom ou d'une sélection reste une
  image longue (190 ms sur 1 800 publications).
- **Export en image** (#175, `export.js`) : le bouton « Exporter (PNG) » du panneau
  télécharge le graphe affiché en PNG (`cy.png`, deux fois la taille à l'écran,
  multipliée par la densité de pixels), tel qu'à l'écran, sélection comprise. L'axe des
  années (au-dessus, étirée comme à l'écran), la bande « Non daté » (ligne pointillée et
  libellé, s'il y en a une à l'écran) et la légende du panneau (en dessous, renvoyée à la
  ligne sur la largeur de l'image) sont redessinés depuis leur HTML. Sans survol, un point
  ne dit pas quel article il est : l'image **nomme** donc certaines publications (#289),
  d'un libellé court (`shortLabel` : nom du premier auteur et année, « Vaswani 2017 » ; à
  défaut d'auteur, le début du titre). Avec une sélection, la publication sélectionnée et
  ses voisins ; sans sélection, les publications `source` (la publication du graphe, ou le
  corpus, y compris sur le graphe de la base pour la personne connectée). Chaque libellé,
  sur un fond clair, va à droite du nœud, sinon à gauche, au-dessus ou en dessous : d'abord
  à une place qui ne couvre aucun nœud, puis à une qui ne couvre qu'un nœud non nommé ;
  à défaut, il est **raccourci** au mot (ou à la lettre) avec « … » pour tenir à droite ou
  à gauche du nœud (#421), sans quoi il est omis (la sélection, puis les plus citées,
  passent d'abord). Aucun libellé ne sort de l'image : `fillText` ne le dessine jamais plus
  large que son cadre, quelle que soit la police (vérifié dans Chrome sans interface par
  `tools/graph_bench/labels.py`). Les
  libellés n'existent que sur l'image, pas à l'écran. Le nom du fichier dit ce que montre l'image :
  `graphe-corpus`, `graphe-publication-<id>`, suivi de `-reseau` en vue réseau (sans axe
  ni bande sur l'image), puis de `-selection-<id>` si une
  publication est sélectionnée, ou de `-zoom` si la vue n'est pas la vue d'ensemble. Pas
  de SVG : il demanderait une extension à embarquer.
- **Modules ES natifs**, sans outil de construction (#174) : `main.js` (point d'entrée,
  chargé avec `type="module"` après Cytoscape), `graph.js` (commun à tous les graphes :
  éléments du cadre, création du graphe Cytoscape, puis vue, sélection et export),
  `card.js` (commun aussi : carte de la sélection et gestes de la sélection), `scale.js` (dates et échelle),
  `viewport.js` (cadrage, bornes de la vue, tailles fixes à l'écran), `focus.js`
  (recentrage à la sélection), `stretch.js` (étirement des positions à la sélection),
  `export.js` (export PNG), `export_labels.js` (noms des nœuds sur l'image),
  `layout.js` (position des nœuds sur la frise), `network.js` (disposition en réseau),
  `network-worker.js` (la même dans un Web Worker, chargé comme module),
  `axis.js` (axe des années), `selection.js` (ce que sélectionne
  un clic sur une publication et le remplissage de sa carte), `hover.js` (survol : infobulle, et liens foncés sous 600 éléments), `style.js`
  (couleurs et feuille de style Cytoscape). Pas de Node ni de tests
  JavaScript dans l'application : la CI vérifie seulement la syntaxe de chaque fichier
  (`tools/check_js.sh`, `node --check`, sans npm, #341) ; le comportement se vérifie dans
  Chrome headless (banc). Fonctions courtes, comme en Python : la vue
  (`viewport.js`) sépare la vue d'ensemble et ses bornes (`makeWholeView`), le bouton
  « Vue d'ensemble » (`bindShowAllButton`) et les tailles à l'écran (`keepScreenSize`) ;
  le recentrage (`focus.js`) sépare l'animation (`makeMover`) de la sélection ; le style
  est fait de trois groupes de règles (nœuds, liens, sélection).
- **Cytoscape.js est embarqué** dans `static/vendor/cytoscape/` (version épinglée,
  intégrité vérifiée, voir son README) : les graphes fonctionnent hors ligne, sans
  service tiers.
- Plotly rendu côté serveur (4,8 Mo de JavaScript par page) et `networkx` sont abandonnés.

## Graphe des auteurs (#222)

Les auteurs reliés par les publications qu'ils signent ensemble (coautorat), avec le même
dessin que les graphes de citations, en vue réseau seulement.

- **Deux graphes, un seul code** (`services/display/author_graph.py`,
  `views/author_graphs.py`) : celui d'**un auteur** (`/authors/<id>/graph/`, bouton
  « Graphe » de sa fiche, public comme elle) montre l'auteur, ses coauteurs et les liens
  entre eux, y compris par des publications où l'auteur n'est pas ; celui de **tous les
  auteurs** (`/authors/graph/`, bouton « Graphe des auteurs » de la liste des auteurs,
  public) montre chaque auteur qui a au moins une publication. Pas d'entrée de menu : la
  page reste sous « Auteurs ». Deux requêtes quelle que soit la taille (les signatures
  des publications concernées, puis les auteurs) ; les paires sont comptées en Python.
- **Graphe des auteurs de mon corpus** (#422, `/corpus/graph/authors/`, connecté) : les
  auteurs des publications du corpus, ou d'un tag et de ses sous-tags (`?tag=`, le
  sélecteur de « Mon graphe »), reliés par ces publications seulement. Les publications
  seulement citées n'en font pas partie (décision de l'utilisateur : elles doubleraient le
  graphe sans dire qui je lis). La taille d'un nœud est son nombre de publications **dans
  le corpus** (ou le tag) : la carte et la légende le disent (`data-scope`). Comme autour
  d'un auteur, les auteurs des seules grandes collaborations n'y sont pas (sur le banc,
  une publication de 1 012 auteurs aurait fait autant de nœuds sans lien). Un choix
  « Graphe : Publications | Auteurs » en tête du panneau passe de « Mon graphe » à ce
  graphe en gardant le tag ; « Mon graphe » reste l'entrée de menu en surbrillance.
  Doublons regroupés comme les autres ; export `graphe-auteurs-corpus[-tag-<tag>]`.
- **Nœuds** : la taille suit le nombre de publications de l'auteur dans la base (aire
  proportionnelle), toutes comprises. L'auteur du graphe est en bleu (`source`), les
  autres de la couleur ordinaire ; pas de couleur par tutelle ni par communauté.
- **Liens** : pondération de **Newman** : chaque publication de n auteurs apporte
  1/(n − 1) à chaque paire de ses auteurs (1 pour un article à deux, 0,5 par paire à trois,
  0,025 à 41). Un seul lien par paire, qui porte la somme (`weight`) et le nombre de
  publications communes (`shared`). Une personne compte une fois par publication, même
  avec plusieurs signatures après une fusion. Pas de seuil : la force se lit dans
  l'**épaisseur** (0,75 à 4 px) et l'**opacité** (0,3 à 0,9) du lien, en racine carrée du
  poids rapporté au plus fort du graphe, pour que les nombreux liens faibles restent
  visibles sans couvrir les forts.
- **Grandes collaborations** : une publication de plus de **50 auteurs**
  (`LARGE_COLLABORATION`) ne crée aucun lien, mais compte dans la taille des nœuds. Le
  panneau dit combien de publications sont ainsi écartées (celles qui auraient relié deux
  auteurs du graphe). Sur le graphe d'un auteur, un coauteur ne l'est que par une
  publication d'au plus 50 auteurs.
- **Disposition** : `cose` avec les réglages de la vue réseau (`network.js`, `COSE`), et
  des liens dont la longueur idéale et la raideur dépendent de la force : de 64 px et une
  élasticité de 64 pour le lien le plus faible à 32 px et 16 pour le plus fort (`cose`
  tire avec (longueur − idéale)² / élasticité ; ses valeurs par défaut sont 48 et 32). Un
  lien fort est donc deux fois plus court et quatre fois plus raide qu'un lien faible ;
  les liens faibles gardent leur place dans le réseau. Départ en spirale, l'auteur du
  graphe au centre.
- **Le reste est celui des graphes de citations** : vue d'ensemble et zoom bornés
  (`viewport.js`), sélection par un zoom uniforme (`focus.js`, `uniform`), panneau à
  droite, légende, aide derrière « ? » (qui explique aussi le poids des liens), export
  PNG. Les éléments de la page portent les mêmes identifiants
  (`citation-graph`, `citation-graph-data`…), que lisent aussi les outils du banc.
- **Sélection** (`coauthor_selection.js`) : un clic sur un auteur met en avant ses
  coauteurs et leurs liens (vert d'eau clair), estompe le reste et zoome sur eux. La carte
  du panneau donne son nom (lien vers sa fiche), son nombre de publications dans la base,
  son nombre de coauteurs dans ce graphe, et ses trois liens les plus forts (avec le
  nombre de publications communes). Survol : le nom, dans l'infobulle en verre dépoli des
  graphes de citations (`hover.js`, liens foncés sous 600 éléments) ; double-clic : la fiche.
- **Doublons probables regroupés** (#419, `services/display/author_groups.py`) : par
  défaut, les auteurs d'un même groupe de « Doublons probables » (même nom de famille,
  prénoms compatibles, jamais deux ORCID différents ni une paire déclarée distincte)
  présents dans le graphe ne font qu'un nœud, au nom le plus complet (ou à celui de
  l'auteur du graphe) ; ses publications sont comptées une fois, ses liens additionnés, et
  deux variantes sur une même publication y sont une seule personne. **Rien n'est écrit
  dans la base.** Le nœud est entouré d'un contour foncé (`outline`, aussi dans la
  légende et sur l'image exportée) ; son infobulle liste les variantes et leurs
  publications ; sa carte aussi, avec, pour un utilisateur connecté, des cases et deux
  boutons : « Ce ne sont pas les mêmes » (`AuthorDistinction`, comme sur la page des
  doublons, donc valable partout ensuite) et « Fusionner pour de bon… » (la confirmation
  de fusion habituelle), qui reviennent au graphe. L'interrupteur « Regrouper les doublons
  probables (n) » du panneau recharge la page avec `?doublons=separes` : la base telle
  qu'elle est. Les groupes sont calculés une fois par page, sans les nombres de
  publications ni les tutelles qui ne servent qu'à les ordonner (deux requêtes, 0,1 s sur
  les 9 507 auteurs du banc, contre 0,15 à 0,6 s pour `duplicate_groups`). L'image des
  grands graphes (#328) reste celle de la base telle qu'elle est.
- **Export** : `graphe-auteur-<id>`, `graphe-auteurs`, `graphe-auteurs-corpus`, suivis de
  `-doublons-separes` sans regroupement, puis de `-selection-<id>` ou `-zoom` comme les
  autres. L'image nomme (nom de famille) l'auteur du graphe, ou l'auteur sélectionné et
  ses coauteurs, les plus publiés d'abord.
- **Modules** : `coauthors.js` (point d'entrée : tailles, épaisseurs, style, disposition)
  et `coauthor_selection.js` (ce que sélectionne un clic, la carte de l'auteur) ; le
  reste est partagé (voir ci-dessous).
- **Taille** (mesures du 14 novembre 2026, Chrome headless, 1 400 px) :

  | Graphe | Auteurs | Liens | JSON | Disposition | Page jusqu'à `DOMContentLoaded` |
  |---|---|---|---|---|---|
  | Base de développement, Helene Felice | 163 | 2 906 | 0,29 Mo | 0,16 s | 0,5 s |
  | Base de développement, tous les auteurs | 411 | 4 886 | 0,51 Mo | 0,40 s | 0,9 s |
  | Base du banc, Helene Felice | 314 | 7 628 | 0,76 Mo | 0,47 s | 1,3 s |
  | Base du banc, Arup Ghosh | 308 | 8 865 | 0,88 Mo | 0,59 s | 1,6 s |
  | Base du banc, tous les auteurs | 9 507 | 56 389 | 6,7 Mo | 120 s | (non chargée) |

  Sur la base du banc (1 797 publications), le graphe de tous les auteurs compte 9 507
  auteurs (dont 3 566 sans aucun lien, auteurs des seules grandes collaborations) et
  56 389 liens ; 23 publications de plus de 50 auteurs sont écartées. Le serveur le
  produit en 0,3 s (0,4 s pour la page, 6,7 Mo). `cose` sur les auteurs les plus reliés :
  1,0 s pour 500 auteurs (11 192 liens), 3,4 s pour 1 000, 11 s pour 2 000, 33 s pour
  4 000 (52 470 liens), **120 s pour les 9 507** (mesuré sans dessin, Cytoscape sans
  cadre) : la page serait bloquée deux minutes. **Limiter ce graphe sur une grande base
  reste à décider.**

## Carte des mots-clés (#418)

Une carte de co-occurrence à la manière de VOSviewer : les mots-clés (ou les thèmes)
qu'OpenAlex donne pour les publications de « Mon corpus », ou d'un tag et de ses
sous-tags, reliés par les publications qui les portent ensemble. En vue réseau seulement.

- **Page** : `/corpus/keywords/` (`views/keywords.py`), entrée « Mots-clés » du groupe
  « Mon corpus » de la navigation, et bouton « Mots-clés » de « Mon corpus » (avec le tag
  filtré, s'il y en a un). Une page à part plutôt qu'un mode de « Mon graphe » : ses
  nœuds ne sont pas des publications, et ses réglages (seuil, mots-clés ou thèmes) n'ont
  pas de sens sur le graphe des citations.
- **Données** (`services/display/keyword_graph.py`) : **aucune requête aux sources**. Les
  champs `keywords` et `topics` des réponses OpenAlex déjà en base (`ExternalRecord.data`),
  extraits par la base de données (`data__keywords`), sans charger les réponses entières.
  Trois requêtes quelle que soit la taille du corpus : les termes, la taille du corpus,
  les publications listées par les cartes. Un terme est nommé par son `display_name`.
- **Mots-clés ou thèmes** (`?kind=keywords` par défaut, `?kind=topics`) : les mots-clés
  sont tirés par OpenAlex du titre et du résumé, avec des synonymes (« HL-LHC »,
  « High-Luminosity LHC ») laissés tels quels ; les thèmes viennent d'une liste fixe,
  plus grossière, sans synonymes. La carte d'un thème donne aussi son domaine et son
  sous-domaine.
- **Nœuds** : la taille suit le nombre de publications du corpus qui portent le terme
  (aire proportionnelle, 12 à 36 px à l'écran). **Liens** : un par paire de termes portés
  par une même publication, d'autant plus épais (0,75 à 5 px), opaque, court et raide que
  ces publications sont nombreuses (`shared`), en racine carrée comme le graphe des
  auteurs. Disposition `cose` de la vue réseau, départ en spirale, le terme le plus porté
  au centre.
- **Seuil** (`?min=`, de 1 à 10) : seuls les termes portés par au moins *n* publications
  sont gardés, et les liens ne relient que ceux-là. Chaque choix de la liste dit combien
  de termes il garde. **2 par défaut** : sur la copie de la base de l'utilisateur
  (corpus de 26 publications, 25 réponses OpenAlex, 21 novembre 2026), 88 des 117
  mots-clés ne sont portés que par une publication ; ils ne relient aucune paire de
  publications et faisaient 117 nœuds et 578 liens. Avec 2 : 29 mots-clés et 135 liens ;
  avec 3 : 17 et 71. Thèmes : 12 et 22 liens avec 1, 6 et 11 avec 2.

  | Seuil | 1 | 2 | 3 | 4 | 5 |
  |---|---|---|---|---|---|
  | Mots-clés (corpus, 26 publications) | 117 / 578 | 29 / 135 | 17 / 71 | 13 / 48 | 6 / 11 |
  | Thèmes (corpus) | 12 / 22 | 6 / 11 | 6 / 11 | 5 / 8 | 4 / 6 |
  | Mots-clés (toute la base, 192 publications) | 725 / 3 574 | 171 / 970 | 91 / 552 | — | 51 / 284 |
  | Thèmes (toute la base) | 65 / 124 | 30 / 62 | 24 / 52 | — | 13 / 25 |

  (termes / liens). Construction des données : 4,5 ms pour le corpus, 17 ms pour les
  termes des 192 publications de la base ; disposition dans Chrome : 19 ms (29 mots-clés),
  5 ms (6 thèmes).
- **Noms** (`keyword_labels.js`) : comme sur VOSviewer, écrits sous les nœuds, le
  terme sélectionné puis les plus portés d'abord, chacun seulement s'il ne chevauche aucun
  nom déjà placé ; zoomer en fait tenir davantage. Ils sont replacés quand la vue ou la
  sélection ne bouge plus (120 ms), jamais pendant une animation. L'image exportée les a
  (c'est le canevas).
- **Sélection** (`keyword_selection.js`) : un clic met en avant le terme, ses voisins et
  leurs liens, et zoome sur eux. La carte liste ses publications (lien vers leur fiche,
  les plus récentes d'abord), le lien « Ouvrir ses n publications dans « Mon corpus » »
  et les cinq termes qui l'accompagnent le plus souvent (un clic les sélectionne). Un
  double clic ouvre « Mon corpus » filtré sur le terme.
- **Filtre de « Mon corpus »** : `?keyword=<nom>` ou `?topic=<nom>` (avec `?tag=` sur la
  carte d'un tag), sans colonne : il est posé par la carte et se lit dans le résumé des
  filtres actifs.
- **Publications écartées** : sous le graphe, le nombre de publications sans réponse
  OpenAlex (sans DOI, ou inconnues d'OpenAlex), et de celles dont la réponse n'a aucun
  terme du type choisi.
- **Export** : `graphe-mots-cles`, `graphe-themes`, suivis de `-tag-<tag>` sur la carte
  d'un tag.
- **Synonymes** : pas de regroupement pour l'instant (voir la PR de #418 pour la suite
  proposée).

## Code commun à tous les graphes (#340)

Les graphes de citations et de coauteurs partagent leur cadre, leur carte et leur
sélection ; un nouveau graphe (mots-clés, auteurs du corpus) ne fournit que ses nœuds,
sa disposition, son style et ce que dit sa carte.

- **Gabarit** `_graph_frame.html`, étendu par `_citation_graph.html` et
  `_author_graph.html` : la carte unique (cadre et panneau), l'infobulle, les commandes,
  la carte de la sélection (titre, bouton « Désélectionner »), la légende, les données
  (`citation-graph-data`) et Cytoscape. Chaque graphe remplit ses blocs : `graph_label`,
  `frame_top` et `frame_overlays` (dans le cadre : l'axe, la bande « Non daté », l'attente
  du réseau), `export_name`, `help`, `controls`, `card_label`, `card_empty`, `card_title`,
  `card_content`, `legend`, `data`, `script` et `empty` (sans aucun lien). Les
  identifiants restent ceux des graphes de citations (`citation-graph`,
  `citation-graph-card`…), que lisent aussi les outils du banc.
- **`graph.js`** : `graphFrame()` (les éléments du cadre et les données),
  `createGraph(container, nodes, edges, style)` (positions données, pas de déplacement ni
  de sélection native, options de rendu selon la taille), `bindGraph(cy, frame,
  {bindSelection, uniform, bindAxes})` (vue, recentrage, sélection, export, puis la
  marque `citation-graph-shown` du banc), et `LAYOUT_MEASURE`, le nom de la mesure de la
  disposition.
- **`card.js`** : `bindSelection(cy, card, focus, {selector, classes, select})` lie les
  gestes communs (appui : sélection et recentrage ; double appui : la fiche ; Échap, clic
  dans le vide ou « Désélectionner » : retour à la vue d'avant) et le survol (`hover.js`).
  Le graphe ne donne que `select(node, card)`, qui pose ses classes, remplit la carte et
  renvoie les nœuds à montrer ; `cardField(card, name)` lit un champ `[data-card=name]`.
- **Style** : `graphStyle(edges)` reçoit la largeur des liens (au repos, survolés), leur
  opacité et celle des éléments estompés ; le graphe ajoute après ses propres règles de
  sélection. `color(name)` lit une couleur du thème. **Disposition** : `spiralPosition(i)`
  (`network.js`), le départ en spirale de toute vue réseau.

## Grands graphes : une image calculée sur le serveur (#328)

Au-delà de `LARGE_GRAPH` nœuds (1 000), le graphe de la base et celui de tous les auteurs
ne sont plus dessinés dans la page : sur la base de banc, le premier a 1 797 publications,
le second 9 507 auteurs et 56 389 liens (2 minutes de disposition `cose` dans le
navigateur, 6,8 Mo de données). La page propose à la place leur **image complète**,
calculée sur le serveur et gardée pour tous (`services/display/graph_images.py`, modèle
`GraphImage`, une ligne par graphe).

- **Calcul** : un utilisateur connecté le lance (`POST /graph/image/<kind>/generate/`) ; il
  passe par la file des récupérations quand un worker tourne (`fetch_worker`, #380), sinon
  dans un thread du serveur. Un calcul « en cours » depuis plus de 5 minutes est considéré
  comme mort et peut être relancé (une demande déjà en file n'est pas dédoublée).
  Pendant le calcul, `static/js/graph_image.js` interroge l'état toutes les 2 s
  (`/graph/image/<kind>/status/`) et recharge la page une fois l'image prête.
- **Disposition** (`services/display/large_graph_layout.py`, #420) : igraph (dépendance
  du projet), **composante par composante** : chaque groupe relié dans une boîte à sa
  mesure, les boîtes rangées par taille décroissante, puis les nœuds sans lien en grille.
  Disposés ensemble, les petits groupes et les auteurs isolés (ceux des grandes
  collaborations, qui ne relient personne) s'étalaient sur toute l'image autour d'un petit
  cœur relié. Dans un groupe :
  - les **feuilles** (nœuds d'un seul lien : la plupart des références, citées une fois)
    sont mises de côté, puis rangées **en couronne** autour de leur nœud, les plus grosses
    à l'intérieur, chaque anneau aussi plein que son périmètre le permet. Disposées avec les
    autres, elles serraient chaque article dans un « pissenlit » ;
  - le **cœur** (les autres nœuds) est disposé par Fruchterman-Reingold (3 000 itérations,
    au lieu de 500), ses **liens pondérés** (rapportés à leur médiane, bornés entre 0,25 et
    8) : deux auteurs qui signent souvent ensemble sont plus proches que les cosignataires
    d'un seul gros article ;
  - **plus de place** : le cœur est agrandi pour que son lien médian vaille 4 fois le
    diamètre de ses extrémités (couronnes comprises) et que ses disques couvrent au plus un
    sixième de son carré ; puis les nœuds dont les couronnes se chevauchent sont écartés,
    paire par paire (grille de voisinage, 80 passes au plus).
  Le générateur d'igraph est fixé : la même base donne la même image. DrL, essayé, tassait
  chaque groupe en un point (78 s pour les auteurs).
- **SVG** : un cercle par nœud (taille selon les publications ou les citations), lien vers
  sa page et nom au survol (`<title>`) ; les noms des 150 plus gros nœuds écrits à côté ;
  les liens en quelques chemins, un par épaisseur (quartiles du poids), pour que le
  fichier reste léger. Servi avec `Content-Security-Policy: default-src 'none'`.
- **Mesures** (base de banc, disposition seule) : graphe des auteurs, 4,6 s (0,7 s avant
  #420) et 3,1 Mo ; graphe de la base, 0,7 s (0,2 s avant) et 0,5 Mo. L'image, plus
  compacte, passe de 6 246 × 9 362 à 3 947 × 6 310 px pour les auteurs.
- **Fraîcheur** : la signature de l'image (nombres et derniers identifiants des
  publications, des créneaux d'auteurs, des citations) dit quand la base a changé depuis ;
  la page le signale et propose « Recalculer l'image ».
- L'image est commune : le corpus de la personne connectée n'y est pas distingué.
- **Parcourir l'image** (#453, `/graph/image/<kind>/`, `graph_image_viewer.html`) :
  « Ouvrir l'image complète » mène à une page qui la parcourt (le fichier SVG reste
  téléchargeable). Le calcul produit, avec l'image, la **liste de ses nœuds**
  (`GraphImage.node_list`, JSON servi par `/graph/image/<kind>/nodes.json`) : nom, taille,
  page, centre et rayon, et les liens en liste de paires ; chaque cercle du SVG porte le
  rang de son nœud (`data-node`). Une image calculée avant n'a pas de liste : la page
  demande de la recalculer. Le SVG est récupéré (`fetch`) et inséré dans la page, sans
  `<script>` ni `<foreignObject>` ; dessiné par le serveur, il n'a pour texte que des noms
  échappés.
  - **Vue** (`image_view.js`) : la vue d'ensemble à l'ouverture ; zoom à la molette centré
    sur le pointeur, déplacement par glisser, boutons + / − / « Tout voir ». La vue est le
    `viewBox` du SVG, aux proportions du cadre, bornée entre l'image entière et 8 pixels
    par unité. Pendant un geste, le SVG déjà dessiné est seulement déplacé et agrandi par
    une transformation CSS ; le `viewBox` suit 150 ms après le dernier mouvement, et
    l'image est redessinée nette.
  - **Pointeur** (`image_pointer.js`) : le SVG ne reçoit aucun événement. Un calque
    transparent au-dessus prend la molette et la souris, et trouve lui-même le nœud sous
    le pointeur dans une grille des nœuds (cases de 64 unités, 3 pixels de tolérance) :
    infobulle du nom (verre dépoli), anneau, ligne de la liste. Un clic **sélectionne** le
    nœud, un second le retire ; un glisser commencé sur un nœud n'est pas un clic. Ctrl, ⌘
    ou le bouton du milieu ouvrent sa page dans un nouvel onglet. Sous un gestionnaire de molette, Chrome
    enregistrait chacun des 66 000 éléments du SVG des auteurs comme une zone de ce
    gestionnaire, et les parcourait à chaque image où la page changeait : 90 ms par image
    au survol. Pour la même raison, les liens et les noms du SVG ont
    `pointer-events="none"`.
  - **Surbrillance** (`image_highlight.js`) : un second SVG, vide, posé sur l'image avec le
    même `viewBox`, porte l'anneau du nœud survolé (bleu) et ceux des nœuds sélectionnés
    (orange), avec leurs liens tracés à partir de la liste. Les anneaux gardent 6 pixels
    d'écart et 3 pixels d'épaisseur quel que soit le zoom (`non-scaling-stroke`) : un nœud
    de 3 pixels se voit dans la vue d'ensemble.
  - **Minicarte** (`image_minimap.js`) : les nœuds dessinés une fois en points dans un
    `<canvas>` (180 pixels au plus, un tiers du cadre sur petit écran), plutôt qu'une
    seconde copie du SVG ; un rectangle montre la partie vue. Un clic ou un glisser y
    centre la vue. En verre dépoli, en bas à droite du cadre.
  - **Sélection** (`image_selection.js`), en haut du panneau, au-dessus de la liste de
    tous les nœuds : son compte, et pour chaque nœud sélectionné (dans l'ordre de la
    sélection) son nom, qui centre la vue sur lui, un lien vers sa page et un bouton pour
    le retirer ; « Tout désélectionner », désactivé quand rien n'est sélectionné. Vide, une
    ligne grise dit comment sélectionner. C'est le seul chemin vers la page d'un nœud, hors
    Ctrl+clic : un clic sur un point ou sur un nom de la liste ne quitte pas la page.
  - **Liste** (`image_nodes.js`), dans le même panneau : recherche sans casse ni accents, tri par taille (publications d'un auteur, citations
    d'une publication) ou par nom, compte des nœuds trouvés. Seules les lignes visibles
    sont dessinées, à leur rang dans une liste aussi haute que toutes. Survoler une ligne
    allume son nœud ; la cocher, ou cliquer sur son nom, le sélectionne ; « Centrer » l'amène au
    milieu de la vue, au moins à la taille réelle. Survoler un nœud de l'image allume sa
    ligne et la fait défiler jusqu'à elle.
  - **Mesures** (`tools/graph_bench/image_frames.py`, base de banc, graphe des auteurs :
    9 507 nœuds, SVG de 3,1 Mo, liste de 1,1 Mo ; Chrome sans interface, 1 400 × 1 000,
    médiane de 3 séries) : page prête en 0,5 s ; zoom de 30 crans, déplacement, survol de
    40 nœuds et de 12 lignes, zoom avec 3 nœuds sélectionnés : 17 ms par image, aucune de
    plus de 50 ms, sauf le redessin net à la fin d'un zoom (une image de 380 ms, le cadre
    étant plus grand en pleine largeur ; 470 à 550 ms à 1 920 × 1 080). Sélection de
    10 nœuds par des clics : 17 ms, 35 ms au plus.
  - **Mise en page** : à partir de `lg`, la page tient dans la fenêtre (bloc `page_height`
    de `base.html` : `h-dvh`) ; le cadre prend toute la place restante, le panneau est à
    sa droite (18rem, 22rem à partir de `xl`, la taille des nœuds masquée entre les deux),
    et seules ses listes défilent. Sous `lg`, le cadre et le panneau ont leur propre hauteur,
    l'un sous l'autre, et la page défile : empilés dans la fenêtre, la liste n'aurait que
    quelques lignes à 1 024 × 768.
