# Graphes

Les graphes de citations : données produites par le serveur, dessin et interactions dans le navigateur. Vue d'ensemble du projet : [architecture.md](architecture.md).

**Décision : le serveur fournit les données, le navigateur dessine.**

- Trois graphes : celui d'une **publication** montre ses références identifiées et les
  publications de la base qui la citent (#186) ; celui du **corpus** montre les
  publications du corpus et ce qu'elles citent ; celui de **la base** (#131, `/graph/`,
  public comme la liste des publications) montre toutes les publications, y compris
  celles sans citation identifiée, et toutes les citations identifiées. Les publications
  du corpus de la personne connectée y sont en bleu (`source`), les autres en vert d'eau
  (`other`). Les liens sont dédoublonnés sans le tri par défaut (`order_by()`), sans quoi
  la position rendait distinctes deux citations d'une même publication.
- **Graphe d'un tag** (#290) : « Mon graphe » peut se limiter à un tag et ses sous-tags
  (`?tag=Projet`), choisi dans une liste du panneau du graphe (envoyée dès qu'elle change,
  `static/js/autosubmit.js`, avec un bouton sans JavaScript). Le contexte est celui des
  suggestions : `tags.context_publications`, et un tag qui n'existe plus ramène à tout le
  corpus avec un message (`views/tag_context.requested_tag`, partagé avec les
  suggestions). « Mes références » filtrée par un tag renvoie au graphe de ce tag, et le
  nom de l'image exportée le dit (`graphe-corpus-tag-projet`).
- `services/display/graph.py` produit les éléments Cytoscape. Les nœuds portent le titre lisible (#264), la date,
  la revue, le premier auteur et le nombre d'auteurs, le nombre de citations dans la
  base et le lien vers la fiche. Les arêtes vont de la publication qui cite vers la
  publication citée. Trois requêtes, quelle que soit la taille du graphe (publications,
  citations, auteurs par `Prefetch`), une de plus pour le corpus sur le graphe de la base.
- La vue intègre ces données dans la page avec `json_script`, sans route JSON séparée.
  Les modules ES de `references/static/references/graph/` les affichent sur une frise
  chronologique : l'axe horizontal suit la date, et les articles non datés sont dans une
  bande sous la frise.
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
  publication cite des publications plus anciennes, à sa gauche. Survoler un nœud fonce
  ses liens. Seuls les nœuds réagissent à la souris : un lien ne se survole ni ne se clique
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
  indication) ou, avec une sélection, la carte de la publication, enfin la légende et
  l'aide. Les commandes et les contrôles sont au-dessus de ce qui change de hauteur : rien
  ne bouge à la première sélection. Le cadre gagne la hauteur de la légende et de l'aide,
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
  **frise**, où x n'est qu'une date : le graphe sans frise (#195) gardera un zoom
  uniforme, sans quoi il déformerait les distances qu'il dessine.
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
    choix sous ce seuil.
  Limites connues : le survol redessine tout le canevas (40 ms à 1 000 publications,
  140 ms à 2 000) ; la réévaluation unique à la fin d'un zoom ou d'une sélection reste une
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
  à une place qui ne couvre aucun nœud, puis à une qui ne couvre qu'un nœud non nommé ; un
  libellé sans place est omis (la sélection, puis les plus citées, passent d'abord). Les
  libellés n'existent que sur l'image, pas à l'écran. Le nom du fichier dit ce que montre l'image :
  `graphe-corpus`, `graphe-publication-<id>`, suivi de `-selection-<id>` si une
  publication est sélectionnée, ou de `-zoom` si la vue n'est pas la vue d'ensemble. Pas
  de SVG : il demanderait une extension à embarquer.
- **Modules ES natifs**, sans outil de construction (#174) : `main.js` (point d'entrée,
  chargé avec `type="module"` après Cytoscape), `scale.js` (dates et échelle),
  `viewport.js` (cadrage, bornes de la vue, tailles fixes à l'écran), `focus.js`
  (recentrage à la sélection), `stretch.js` (étirement des positions à la sélection),
  `export.js` (export PNG),
  `layout.js` (position des nœuds), `axis.js` (axe des années), `selection.js` (sélection
  et carte), `style.js` (couleurs et feuille de style Cytoscape). Pas de Node ni de tests
  JavaScript pour l'instant : vérification dans Chrome headless.
- **Cytoscape.js est embarqué** dans `static/vendor/cytoscape/` (version épinglée,
  intégrité vérifiée, voir son README) : les graphes fonctionnent hors ligne, sans
  service tiers.
- Plotly rendu côté serveur (4,8 Mo de JavaScript par page) et `networkx` sont abandonnés.
