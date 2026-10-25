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
- `services/graph.py` produit les éléments Cytoscape. Les nœuds portent le titre, la date,
  la revue, le premier auteur et le nombre d'auteurs, le nombre de citations dans la
  base et le lien vers la fiche. Les arêtes vont de la publication qui cite vers la
  publication citée. Trois requêtes, quelle que soit la taille du graphe (publications,
  citations, auteurs par `Prefetch`), une de plus pour le corpus sur le graphe de la base.
- La vue intègre ces données dans la page avec `json_script`, sans route JSON séparée.
  Les modules ES de `references/static/references/graph/` les affichent sur une frise
  chronologique : l'axe horizontal suit la date, et les articles non datés sont à gauche.
- **Disposition** (#138, `layout.js`) : x suit la date ; la position verticale rapproche
  les publications qui se citent, sans dépendance. D'abord un **ordre** par la méthode du
  barycentre (chaque publication va vers la rangée moyenne de ses voisines, en
  20 passes), puis une petite **simulation verticale** : les publications liées
  s'attirent, une publication s'écarte des liens qui passent sur elle (aucun lien caché
  derrière un nœud), et deux publications proches en date ne se chevauchent pas
  (écart selon leur taille). Les rangées de départ sont espacées de 36 px quelle que soit
  la taille du cadre : la disposition ne dépend pas de la fenêtre. Le résultat est ramené à la hauteur du cadre, étiré ou comprimé : les nœuds gardent leur taille à l'écran, un dézoom ne les séparerait pas et perdrait de la largeur ; zoomer sépare ceux que la compression rapproche (#185). Sur le graphe du
  corpus de la base réelle : 51 croisements de liens au lieu de 147 avec une rangée par
  publication dans l'ordre des dates. « Non daté » n'apparaît sur l'axe que s'il y a des
  publications sans date.
- **Style** (#139, #140, `style.js`) : la couleur d'un nœud dit son **rôle** (`role` dans
  les données) : `source` en bleu (la publication du graphe, ou celles du corpus),
  `citing` en orange (une publication qui la cite), `cited` en vert d'eau (citée
  seulement). Sa **taille** suit
  son nombre de citations dans la base (aire proportionnelle). Tailles des nœuds, épaisseurs
  des liens et libellés sont **fixes à l'écran** (#185) : divisées par le zoom, réévaluées
  au plus une fois par image (`requestAnimationFrame`) quand le zoom change. Zoomer écarte
  donc les nœuds sans les grossir, ce qui sépare les publications proches en date. Les couleurs sont définies
  une seule fois, en variables de thème Tailwind (`--color-graph-*` dans
  `assets/css/source.css`) : la légende HTML utilise les classes, Cytoscape lit les
  variables. Palette vérifiée (daltonisme, contraste d'au moins 3:1 sur blanc). Liens au repos
  droits, gris, sans flèche : une
  publication cite des publications plus anciennes, à sa gauche. Survoler un nœud fonce
  ses liens.
- **Vue** (#141, `viewport.js`) : la vue d'ensemble (tout le graphe dans le cadre, avec
  une petite marge) est le zoom minimal, recalculé quand le cadre change de taille, et
  la vue ne sort jamais de cette emprise : le déplacement est ramené dans les bornes à
  chaque événement `viewport`. L'axe n'affiche donc jamais d'années vides.
  Un bouton en haut à droite du cadre y revient (#196), par le même cadrage que le
  chargement et le redimensionnement. Il est désactivé (grisé), plutôt que masqué, quand
  la vue d'ensemble est déjà affichée : il reste visible et à sa place.
- **Axe des années** : une bande HTML au-dessus du canevas (`#citation-graph-axis`),
  redessinée à chaque événement `viewport` de Cytoscape. Le pas des graduations dépend de
  la place à l'écran (au moins 60 px entre deux libellés), pas de la plage d'années (#62).
- **Sélection** (#61) : un clic sur un article met en évidence ses références (nœuds
  vert d'eau) et les articles qui le citent (nœuds orange), chaque lien dans une nuance
  plus claire de son nœud, et estompe le reste. La carte d'informations HTML
  (`#citation-graph-card`, en bas à gauche du cadre) est compacte (#187) : le titre est
  le lien vers la fiche, puis la revue (lue dans la réponse stockée de Crossref ou de
  DataCite, dans la même requête), le premier auteur et l'année, et les compteurs. Un double-clic ouvre la fiche ; Échap ou
  un clic dans le vide désélectionne.
- **Recentrage à la sélection** (#142, `focus.js`) : la vue zoome sur l'article et ses
  voisins (animation de 300 ms, aucune avec « réduire les animations »), dans la zone que
  la carte laisse libre, à sa droite ou au-dessus, celle où ils paraissent le plus
  grands ; au plus 4 fois le zoom de la vue d'ensemble, pour un voisin tout proche. La
  désélection ramène la vue d'avant la sélection (la vue d'ensemble dans le cas courant,
  un zoom fait à la main sinon). Le temps de la sélection, les bornes de #141 s'élargissent
  à la vue voulue : dans la vue d'ensemble, un voisin caché sous la carte ne pourrait pas
  être montré autrement.
- **Export en image** (#175, `export.js`) : un bouton à côté de celui de la vue
  d'ensemble télécharge le graphe affiché en PNG (`cy.png`, deux fois la taille à l'écran,
  multipliée par la densité de pixels), tel qu'à l'écran, sélection comprise. L'axe des
  années (au-dessus) et la légende (en dessous, renvoyée à la ligne comme sur la page) sont
  redessinés depuis leur HTML. Le nom du fichier dit ce que montre l'image :
  `graphe-corpus`, `graphe-publication-<id>`, suivi de `-selection-<id>` si une
  publication est sélectionnée, ou de `-zoom` si la vue n'est pas la vue d'ensemble. Pas
  de SVG : il demanderait une extension à embarquer.
- **Modules ES natifs**, sans outil de construction (#174) : `main.js` (point d'entrée,
  chargé avec `type="module"` après Cytoscape), `scale.js` (dates et échelle),
  `viewport.js` (cadrage, bornes de la vue, tailles fixes à l'écran), `focus.js`
  (recentrage à la sélection), `export.js` (export PNG),
  `layout.js` (position des nœuds), `axis.js` (axe des années), `selection.js` (sélection
  et carte), `style.js` (couleurs et feuille de style Cytoscape). Pas de Node ni de tests
  JavaScript pour l'instant : vérification dans Chrome headless.
- **Cytoscape.js est embarqué** dans `static/vendor/cytoscape/` (version épinglée,
  intégrité vérifiée, voir son README) : les graphes fonctionnent hors ligne, sans
  service tiers.
- Plotly rendu côté serveur (4,8 Mo de JavaScript par page) et `networkx` sont abandonnés.
