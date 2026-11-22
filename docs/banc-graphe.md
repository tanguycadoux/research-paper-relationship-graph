# Banc d'essai des graphes

Mesures de la disposition et de l'affichage des graphes de citations sur de grands
graphes (#202) : avant toute optimisation, puis après la disposition par groupes et la
simulation allégée (voir « Après l'optimisation de la disposition »). Vue d'ensemble du projet :
[architecture.md](architecture.md) ; les graphes eux-mêmes : [graphes.md](graphes.md).

## Méthode

Les outils sont dans `tools/graph_bench/`, sans dépendance de plus que celles du
projet. Ils ne changent pas le code de l'application.

- **`grow_base.py`** fait grossir une **copie** de la base avec de vraies publications,
  par les services de l'application (`add_to_corpus`) et les vraies sources. À lancer
  dans une copie de travail du dépôt (worktree) qui a sa propre `db.sqlite3`, avec
  `DJANGO_DEBUG=1` pour garder les réponses dans `.http_cache.sqlite`. Deux façons de
  grossir :
  - **en chaîne** : un utilisateur `bench` reprend les corpus de la base, puis ajoute à
    son corpus, niveau par niveau, les publications qu'il cite (les plus citées d'abord,
    60 par niveau), ce qui importe leurs propres bibliographies ;
  - **sans lien** : douze articles très cités de domaines éloignés (AlphaFold, CRISPR,
    cancer, vaccin, apprentissage profond, économie, climat, ondes gravitationnelles…),
    avec leurs bibliographies : des groupes sans lien avec le reste (#230).
- **`server.py`** mesure, côté serveur, la construction des données de chaque graphe
  (`services/display/graph.py`) : temps, nombre de requêtes SQL, taille du JSON. Il donne
  aussi un cookie de session de `bench`, pour le graphe de son corpus.
- **`bench.py`** pilote Chrome headless par le protocole DevTools (client WebSocket en
  Python pur) :
  - pour une **page** de l'application : temps jusqu'à la réponse et jusqu'à
    `DOMContentLoaded` (les modules de `main.js` s'exécutent avant : disposition et
    création du graphe, sauf un grand réseau, disposé dans un Web Worker), jusqu'à
    l'affichage du graphe (marque `citation-graph-shown` de `main.js`, colonne `shown`),
    la plus longue image pendant la disposition (`layoutFrameMax` : la page répond-elle ?
    enregistrée par un script posé avant ceux de la page), taille des données, étapes de la disposition, une écriture de
    toutes les positions (ce que fait `stretch.js` à chaque image de l'animation de
    sélection), intervalles entre images pendant l'animation de sélection de la
    publication la plus reliée, captures ;
  - pour des **graphes synthétiques** (`--synthetic 500 1000 2000`) : quatre composantes
    de tailles décroissantes, chaque publication cite 2 ou 3 publications plus anciennes
    de sa composante (les plus citées plus souvent), dates de 1960 à 2025 avec davantage
    de récentes, 2 % sans date. Disposition, création du graphe Cytoscape dans un cadre
    de 690 × 767 px (celui de la page à 1 400 px de large), images pendant un zoom.
- **`frames.py`** (et `frames.js`, dans la page) mesure le **dessin pendant un geste**,
  avec de vrais événements de souris envoyés par DevTools : zoom à la molette (30 crans),
  glisser de la vue, sélection de la publication la plus reliée (animation), survol de
  30 publications. Il enregistre les intervalles entre images (`requestAnimationFrame`) et
  donne médiane, 90e centile, maximum et nombre d'images de plus de 50 ms ; médiane de 3
  séries, chacune repartant de la vue d'ensemble. Les graphes synthétiques sont montés
  dans une page de l'application avec ses modules (style, vue, étirement, sélection,
  axe) ; leurs positions sont posées sans la disposition (x : la date, y : au hasard),
  qui est mesurée par `bench.py`. Son port DevTools est réglable (`--port`).
- **`labels.py`** vérifie les **libellés de l'export PNG** (#421) : il importe
  `export_labels.js` dans une page du serveur et place le libellé d'un nœud au bord droit
  ou dans un cadre étroit ; le libellé doit rester dans l'image, à gauche du nœud ou
  raccourci avec « … ». Code de sortie 1 si un cas échoue (Node n'est pas nécessaire).
- **`image_frames.py`** mesure les **images de la page qui parcourt un grand graphe**
  (#453) : temps jusqu'à l'image dans le cadre, puis, avec les événements de souris de
  `frames.py` et l'enregistrement de `frames.js`, un zoom de 30 crans, un glisser, le
  survol de 40 nœuds de l'image et de 12 lignes de la liste, et un zoom avec 3 nœuds
  cochés. Résultats dans [graphes.md](graphes.md) (« Parcourir l'image »).
- **`bench.js`**, exécuté dans la page : `placeNodes` est appelé avec un objet `timings`,
  dans lequel `layout.js` additionne le temps de chacune de ses étapes (et le nombre de
  recherches de couples, `refreshes`) ; puis les croisements de liens du résultat sont
  comptés. Jusqu'à #230, `bench.js` relisait `layout.js` et en refaisait les étapes ; les
  colonnes de la première série viennent de là.
- Deux bancs peuvent tourner en même temps : chacun son port DevTools
  (`--devtools-port`, ou la variable `GRAPH_BENCH_DEVTOOLS_PORT` ; 9420 par défaut).

Médiane de 3 répétitions (une seule au-delà de 1 000 nœuds), sur la machine de
développement.

```bash
# Dans un worktree, sur une copie de la base
DJANGO_DEBUG=1 python tools/graph_bench/grow_base.py --target 2500 --per-level 60
DJANGO_DEBUG=1 python tools/graph_bench/server.py --user bench
DJANGO_DEBUG=1 python manage.py runserver 8120
python tools/graph_bench/bench.py http://127.0.0.1:8120 --out /tmp/bench \
    --session <cookie de server.py> --page /graph/ --page /corpus/graph/ \
    --page /publications/<pk>/graph/ --synthetic 500 1000 2000
```

## Base grossie (14 novembre 2026)

Partie de la base de développement (76 publications, 85 citations), en 464 s :

| Étape | Publications | Citations identifiées | Auteurs | Corpus de `bench` |
|---|---|---|---|---|
| Corpus existants | 76 | 85 | 411 | 4 |
| Chaîne, niveau 1 | 138 | 174 | 752 | 25 |
| Niveau 2 | 475 | 651 | 2 139 | 85 |
| Niveau 3 | 837 | 1 295 | 3 083 | 145 |
| Niveau 4 | 1 152 | 1 920 | 3 669 | 205 |
| Douze articles sans lien | **1 797** | **2 559** | **9 507** | 217 |

- Requêtes réseau : 498 (OpenAlex 218, Crossref 178, ORCID 94, DataCite 8), sans
  `CROSSREF_MAILTO` (*public pool*). Aucune erreur d'import.
- 31 publications sans date ; 11 publications de plus de 100 auteurs (LIGO surtout :
  1 012, 964, 945…), qui font l'essentiel des 9 507 auteurs (#292).
- Restent ouverts : 22 conflits « Auteurs différents » (24 avertissements « OpenAlex
  authors do not match » à l'import, malgré #265 ; 3 après #317, de vraies différences), 33 « Nom différent selon
  ORCID », 17 « ORCID différent », 5 versions publiées proposées. 1 214 références sur
  3 776 restent à identifier.

## Résultats

### Base grossie

| Graphe | Nœuds | Liens | Données (serveur) | JSON | Page jusqu'à `DOMContentLoaded` | `placeNodes` | dont `clearEdges` | `separateClose` | `crossedEdges` | Image pendant la sélection |
|---|---|---|---|---|---|---|---|---|---|---|
| Base | 1 797 | 2 539 | 437 ms, 4 requêtes SQL | 726 Ko | **11,5 s** | **10,3 s** | 7,2 s | 0,76 s | 0,25 s | 141 ms (max 164) |
| Corpus de `bench` | 1 775 | 2 517 | 442 ms, 4 requêtes | 719 Ko | **11,4 s** | **10,9 s** | 7,0 s | 1,7 s | 0,15 s | 137 ms (max 170) |
| Publication la plus citée (32 citants) | 35 | 34 | 10 ms, 3 requêtes | 13 Ko | 73 ms | 6 ms | 4,8 ms | 0,2 ms | 0,2 ms | 17 ms (max 22) |

Sur la base, `closePairs` trouve 488 000 paires proches en date (la plupart des
publications ont moins de vingt ans) et `crossedEdges` 720 000 couples nœud / lien ;
`clearEdges` et `separateClose` les parcourent à chacune des 300 itérations. Écrire toutes
les positions (ce que `stretch.js` fait à chaque image) prend 5 ms : le coût d'une image
de l'animation est le dessin de Cytoscape, pas l'étirement.

### Graphes synthétiques

| Nœuds | Liens | `placeNodes` | `clearEdges` | `separateClose` | `crossedEdges` | Paires proches | Couples nœud / lien | Création Cytoscape | Image pendant un zoom (médiane / max) |
|---|---|---|---|---|---|---|---|---|---|
| 500 | 1 240 | 2,1 s | 2,1 s | 37 ms | 28 ms | 21 000 | 230 000 | 121 ms | 72 / 102 ms |
| 1 000 | 2 471 | 8,2 s | 7,9 s | 130 ms | 116 ms | 80 000 | 878 000 | 158 ms | 147 / 173 ms |
| 2 000 | 4 956 | 45 s | 34 s | 0,54 s | 0,44 s | 327 000 | 3,6 M | 331 ms | 295 / 358 ms |
| 4 000 | 9 940 | 181 s | 163 s | 4,6 s | 2,4 s | 1,3 M | 14,4 M | 532 ms | 535 / 584 ms |

`barycentreOrder`, `closePairs` et `pullLinked` restent sous 50 ms partout. Au-delà de
1 000 nœuds, une seule répétition : les écarts entre `placeNodes` et la somme des étapes
viennent de là.

### Ce qui se voit

- **Graphe de la base** (1 797 nœuds) : les domaines sans lien (cancer, AlphaFold, LIGO,
  aimants supraconducteurs) s'empilent en bandes horizontales et s'entremêlent par leurs
  liens longs (#230) ; les publications des vingt dernières années sont tassées dans le
  tiers droit de la frise et se recouvrent ; les 31 non datées forment une rangée
  régulière en bas, la plupart sans lien daté (réparties sur la largeur).
- **Sélection** de « Hallmarks of Cancer » (239 références) : l'étirement de #291 marche,
  mais les références, presque toutes de 2005 à 2011, restent tassées et se recouvrent.
- **Temps ressentis** : 11 s de page blanche avant le graphe (le navigateur est bloqué
  pendant la disposition), puis 7 images par seconde à l'animation de sélection et au
  zoom.

## Dessin pendant un geste, avant et après (#202, piste 4)

Intervalle entre images, en millisecondes : **médiane / 90e centile**, puis nombre
d'images de plus de 50 ms. Mesuré avec `frames.py`, Chrome headless à 1 400 px.

| Graphe (éléments) | Geste | Avant | Après |
|---|---|---|---|
| Base grossie (4 336) | Zoom | 44 / 195, 35 lentes | **17 / 18**, 3 |
| | Glisser | 17 / 38 | 17 / 18 |
| | Sélection | 80 / 176 | **17 / 17** (saut direct) |
| | Survol | 17 / 50, 7 lentes | 17 / 50, 11 lentes |
| Synthétique 500 (1 740) | Zoom | 32 / 93, 30 lentes | **17 / 17**, 2 |
| | Sélection | 23 / 105 | 17 / 18 |
| Synthétique 1 000 (3 471) | Zoom | 69 / 190, 60 lentes | **17 / 18**, 5 |
| | Glisser | 48 / 55, 22 lentes | **17 / 17**, 1 |
| | Sélection | 126 / 203 | **17 / 17** |
| | Survol | 42 / 79, 29 lentes | 39 / 73, 29 lentes |
| Synthétique 2 000 (6 956) | Zoom | 152 / 402, 69 lentes | **17 / 24**, 2 |
| | Glisser | 101 / 109, 31 lentes | **17 / 21**, 3 |
| | Sélection | 270 / 407 | **17 / 141** |
| | Survol | 141 / 149, 30 lentes | 137 / 143, 30 lentes |
| Base de l'utilisateur (161) | Tous les gestes | 17 / 17 à 23 | inchangé |

Ce qui part en temps, sur la base grossie (profil Chrome, 40 images de zoom) :
- la **réévaluation du style** à chaque image (`style().update()`) : 135 ms sur 4 300
  éléments, trois fois le dessin ; sans elle, le dessin seul est de 44 ms (`renderOnly`) ;
- une feuille de style recalculée pour le zoom (`style().fromJson`, tailles en `mapData`)
  coûte plus cher que les fonctions (236 contre 177 ms par image, zoom compris) : la
  réévaluation est liée au nombre d'éléments, pas à la forme des valeurs ;
- sans réévaluation, le dessin d'une image de zoom est de 44 ms, de 41 avec les liens
  masqués, 37 avec `textureOnViewport` et 36 avec `motionBlur` (mesure sans événements
  de souris : ce sont les vrais gestes qui font la différence, ci-dessus).

Ce qui a été fait (`viewport.js`, `focus.js`, `main.js`) :
1. **Au-delà de 600 éléments**, tailles réévaluées une fois le zoom arrêté (150 ms) et
   sélection sans animation : zoom et sélection de 44 à 17 ms (base grossie).
2. **Au-delà de 600 éléments aussi**, `textureOnViewport` : le glisser à 1 000 publications
   passe de 48 à 17 ms, et le zoom de 17 / 61 à 17 / 18.
3. **Au-delà de 5 000 éléments**, `hideEdgesOnViewport` à la place : la texture devient
   lente (32 images lentes à 2 000 publications, 2 avec les liens masqués).

Ce qui n'est pas réglé :
- le **survol** : il redessine tout le canevas (classes `hovered` du nœud et de ses
  liens) : 39 ms à 1 000 publications, 137 à 2 000 ;
- **l'image qui suit un zoom ou une sélection** : réévaluer le style une fois reste 140 à
  200 ms (maximum à 190–480 ms), perceptible comme un à-coup à la fin du geste (réduite
  quand la vue ne montre qu'une partie du graphe : « Image longue en fin de geste ») ;
- la sélection d'un graphe de 2 000 publications a un 90e centile de 141 ms, pour la même
  raison (une image longue au saut).

## Après l'optimisation de la disposition

Disposition par groupes (#230), non datées sur plusieurs rangées (#318), et simulation
qui ne parcourt que les couples à portée (`clearEdges`, `separateClose` : pistes 1 à 3
ci-dessous), mesurées le même jour sur la même base et la même machine. « Recherches » :
les recherches des couples à portée (`nearEdges` et `nearPairs`, au plus toutes les
10 itérations par groupe).

| Graphe | `placeNodes` avant | après | Recherches | `clearEdges` | Page jusqu'à `DOMContentLoaded` | Croisements avant | après |
|---|---|---|---|---|---|---|---|
| Base du banc (1 797 nœuds, 13 groupes) | 11,2 s | **0,30 s** | 115 ms (153) | 123 ms | 11,5 s → **1,5 s** | 42 952 | 49 838 |
| Publication la plus citée (35 nœuds) | 6 ms | 4 ms | 0,5 ms (15) | 2 ms | 73 ms → 66 ms | — | 0 |
| Base de développement (76 nœuds, 3 groupes) | 35 ms | 6 ms | 0,5 ms (19) | 3 ms | 99 ms | 78 | 67 |

| Nœuds synthétiques | `placeNodes` avant | après | Recherches | `clearEdges` |
|---|---|---|---|---|
| 500 | 2,7 s | 0,81 s | 266 ms | 519 ms |
| 1 000 | 10,8 s | 2,5 s | 796 ms | 1,7 s |
| 2 000 | 45,9 s | 8,7 s | 2,7 s | 5,9 s |
| 4 000 | 181 s | 26,7 s | 8,0 s | 18,3 s |

- **La base du banc passe sous la seconde** (0,3 s), et la page s'affiche en 1,5 s au lieu
  de 11,5 s (le reste : données, création du graphe Cytoscape).
- **Croisements** : sur le banc, les groupes séparés n'ont plus de croisements entre eux,
  mais un peu plus à l'intérieur (42 952 → 49 838 au total) ; l'approximation des
  recherches n'y est pour rien (50 436 avec une recherche exacte à chaque itération). Sur
  la base de développement, 78 → 67. Dans la vue d'ensemble, les écarts entre les groupes
  prennent un peu de hauteur : 99 recouvrements de nœuds au lieu de 83 sur la base de
  développement, que le zoom sépare toujours.
- **Les graphes synthétiques restent lents** au-delà de 500 nœuds : très denses (chaque
  publication cite 2 ou 3 publications de toute sa composante, 292 000 croisements pour
  1 000 nœuds), beaucoup de couples y sont vraiment à portée, et `clearEdges` les traite
  à chaque itération. Les vrais graphes en ont beaucoup moins (6 000 couples en moyenne
  sur la base du banc).
- **Le dessin** (images pendant un zoom ou une sélection) n'a pas changé : c'est la
  piste 4, traitée à part.

## Vue réseau (#195)

Disposition `cose` de Cytoscape (`network.js`), mesurée dans la page : `bench.py` lit
maintenant la mesure `citation-graph-layout` de `main.js` (colonne `layout`), pour la
frise comme pour le réseau. Recouvrements : couples de nœuds dont les cercles se
chevauchent au zoom de la disposition (1). Médiane de 3 chargements, Chrome headless à
1 400 px.

| Graphe | Vue | Disposition | Page jusqu'à `DOMContentLoaded` | Recouvrements |
|---|---|---|---|---|
| Base de développement (76 nœuds, 85 liens) | Frise | 13 ms | 81 ms | 99 |
| | Réseau | 20 ms | 83 ms | 0 |
| Base du banc (1 797 nœuds, 2 539 liens) | Frise | 0,32 s | 1,3 s | 39 650 |
| | Réseau | **2,9 s** | 3,8 s | 193 |

Réglages de `cose` essayés sur la base du banc (même départ en spirale, zoom 1) ; sur la
base de développement, tous donnent 0 recouvrement, de 9 à 65 ms :

| Réglage | Itérations | Disposition | Recouvrements | Longueur des liens (médiane / 90e centile) |
|---|---|---|---|---|
| Par défaut (`coolingFactor` 0,99) | 690 | 27,6 s | 60 | 120 / 176 px |
| 0,95 | 135 | 5,6 s | 197 | 126 / 177 px |
| 0,93 | 95 | 4,1 s | 264 | 129 / 182 px |
| 0,9 | 66 | 2,9 s | 329 | 131 / 184 px |
| 0,9, `nodeOverlap` 32 | 66 | 3,0 s | 474 | 157 / 247 px |
| **0,9, `nodeRepulsion` 16 000 (retenu)** | 66 | **2,9 s** | **193** | 141 / 197 px |

- Chaque itération coûte n² (répulsion entre toutes les paires, groupes sans lien
  compris) : environ 40 ms à 1 800 nœuds. Disposer chaque groupe à part (10 groupes, le
  plus grand de 1 129 nœuds) donne 2,1 s au lieu de 2,9 s : trop peu pour écrire notre
  propre rangement des groupes, que `cose` fait déjà.
- **Dessin pendant un geste** (`frames.py`, base du banc, 4 336 éléments) : les règles des
  grands graphes de #320 valent aussi en réseau. Zoom, glisser et sélection à 17 ms en
  médiane et au 90e centile, comme la frise. Le survol est plus souvent lent (24 images de
  plus de 50 ms sur 30 survols, 4 en frise) : les nœuds y sont plus serrés et chaque
  survol redessine tout le canevas (limite connue, #202). Base de développement : 17 à
  22 ms partout.
- La page restait bloquée 2,9 s sur la base du banc, au-delà de la limite de 1 s : la
  disposition se fait maintenant dans un Web Worker (voir la section suivante).

## Survol léger et réseau disposé hors de la page (#202)

Le survol affiche le titre dans une infobulle HTML (`hover.js`) ; au-delà de 600 éléments
(`LIVE_SIZES_MAX_ELEMENTS`), il ne change plus aucune classe `hovered` (liens foncés), et la vue réseau dispose le
graphe dans un Web Worker (`network-worker.js`). Mesuré le 14 novembre 2026, Chrome
headless à 1 400 px.

**Survol** (`frames.py`, 30 survols, médiane de 3 séries) : intervalle entre images,
**médiane / 90e centile**, puis nombre d'images de plus de 50 ms. Les autres gestes
(zoom, glisser, sélection) n'ont pas changé.

| Graphe (éléments) | Avant | Après |
|---|---|---|
| Base du banc, frise (4 336) | 17 / 48, 2 lentes | **17 / 20**, 0 |
| Base du banc, réseau (4 336) | 17 / 51, 24 lentes | **17 / 20**, 0 |
| Synthétique 1 000 (3 471) | 37 / 73, 29 lentes | **17 / 19**, 0 |
| Synthétique 2 000 (6 956) | 133 / 142, 30 lentes | **17 / 20**, 0 |
| Base de développement (161), frise et réseau | libellé Cytoscape, liens foncés | inchangé : 17 / 19, 0 |

**Réseau de la base du banc** (1 797 nœuds, 2 539 liens ; `bench.py`, médiane de 3
chargements) :

| | Avant (dans la page) | Après (Web Worker) |
|---|---|---|
| `DOMContentLoaded` | 3,7 s | **0,6 s** |
| Disposition (`layout`) | 2,9 s | 3,0 s (aller-retour du worker compris) |
| Graphe affiché (`shown`) | 3,7 s (avec `DOMContentLoaded`) | 4,0 s |
| Plus longue image pendant la disposition | 3,6 s (page figée) | **17 ms** |

- **Positions** : identiques à celles de la disposition dans la page (écart maximal 0 sur
  les 1 797 nœuds, et en repli après un échec du worker). Il a fallu donner au worker la
  taille du cadre : `cose` attire les nœuds vers son centre (`cy.width()`,
  `cy.height()`, que Cytoscape sans affichage n'a pas), et une disposition `preset` à la
  création, sans quoi Cytoscape pose tous les nœuds en (0, 0) et `cose` les sépare au
  hasard (écarts de 300 à 700 px d'une fois à l'autre).
- **Le graphe s'affiche 0,3 s plus tard** qu'avant (démarrage du worker, chargement de
  Cytoscape, copie des éléments, puis création du graphe), mais la page est utilisable dès
  0,6 s, avec le message « Disposition du graphe… » dans le cadre : pendant la
  disposition, une évaluation DevTools répond en 1 ms et les images restent à 17 ms.
- **Seuil** : l'aller-retour du worker coûte 70 à 90 ms sur 400 à 750 éléments
  (démarrage et chargement de Cytoscape compris), autant que `cose` dans la page à cette
  taille (20 ms pour les 161 éléments de la base de développement) : sous 600 éléments,
  le worker ne ferait gagner que l'affichage d'un message de moins de 100 ms. Le seuil
  des grands graphes est donc gardé.
- La frise ne change pas : positions identiques à `main` sur la base de développement.

## Limites proposées et étapes qui les dépassent

- **Disposition : 1 s.** Elle est dépassée dès 300 à 350 nœuds (2,1 s à 500, en n²). En
  cause, dans l'ordre : `clearEdges` (70 à 95 % du temps : chaque couple nœud / lien qui
  passe au-dessus, à chacune des 300 itérations), puis `separateClose` sur les graphes
  aux dates serrées (1,7 s sur le corpus de `bench`), puis `crossedEdges` (une fois,
  n × liens) au-delà de 2 000 nœuds.
- **Image pendant une animation ou un zoom : 50 ms** (20 images par seconde ; 16 ms pour
  être fluide). Dépassée dès 500 nœuds (72 ms) ; 140 ms sur la base. En cause : le dessin
  de Cytoscape et la réévaluation du style (tailles fixes à l'écran, #185) à chaque image.
- **Serveur : sans souci** à cette taille (moins de 0,5 s, 4 requêtes, 0,7 Mo de JSON).

## Pistes d'optimisation

Classées par gain attendu pour l'effort. Les pistes 1 à 4 sont faites (#319, #320, voir plus haut), la 5 pour la vue réseau ; le cache des positions et la 6 restent à décider.

1. **`clearEdges`** : ne l'appliquer que pendant les dernières itérations (les positions
   ont déjà convergé), et ne garder pour chaque nœud que les liens proches de lui en y,
   recalculés de temps en temps (index par tranches). Gain attendu : un ordre de
   grandeur sur les grands graphes.
2. **Composantes disposées séparément** (#230) : un graphe de domaines sans lien devient
   plusieurs petits graphes, empilés ; moins de liens passent au-dessus d'un nœud, et les
   bandes ne s'entremêlent plus.
3. **`separateClose`** : moins d'itérations, ou seulement les voisins immédiats en x
   (balayage par tri) au lieu de toutes les paires à moins de 40 px.
4. **Dessin pendant le mouvement** (fait, voir la série ci-dessus) : options de Cytoscape
   `textureOnViewport` et `hideEdgesOnViewport` au-delà d'un seuil, et tailles à l'écran
   recalculées à la fin du zoom plutôt qu'à chaque image ; le survol par une infobulle
   HTML au-delà du même seuil (fait, « Survol léger »). L'image longue à la fin d'un
   geste ne porte plus que sur ce qui est dans la vue (#326, « Image longue en fin de
   geste ») ; elle reste quand la vue montre tout le graphe.
5. **Ne pas bloquer la page** : fait pour la vue réseau (`cose` dans un Web Worker avec
   un message d'attente, « Survol léger et réseau disposé hors de la page ») ; la frise
   (0,3 s sur le banc) reste dans la page. Les positions gardées en cache (navigateur)
   tant que les données du graphe ne changent pas restent à décider.
6. **Graphe de la base** : au-delà d'un seuil, proposer de le limiter (corpus, tag,
   composante) plutôt que de tout dessiner.

## Moins de croisements de liens (#322, #323)

Frise : échanges de hauteurs après la simulation (`untangle.js`, groupes d'au plus
300 liens) et références de la même date décalées vers la gauche. Réseau : feuilles en
couronne, références partagées alignées, dessin tourné, six départs de `cose` jusqu'à
300 éléments (`crown.js`, `crossings.js`). Mesuré le 22 novembre 2026, Chrome headless
à 1 400 px.

**Croisements** (liens droits, comptés sur les positions affichées), sur une copie de la
base de l'utilisateur :

| Graphe | Vue | Avant | Après | Disposition avant | après |
|---|---|---|---|---|---|
| « Mon graphe » (96 publications, 130 citations) | Frise | 376 | **151** | 23 ms | 76 ms |
| | Réseau | 302 | **57** (94 avec un seul départ) | 38 ms | 65 ms |
| Tag « ASTERICS › MT28 » (41, 58) | Frise | 140 | **29** | 10 ms | 19 ms |
| | Réseau | 68 | **22** | 16 ms | 34 ms |
| « Attention Is All You Need » (23, 22) | Frise | 0 | 0 | 12 ms | 6 ms |

Sur « Attention », la frise n'avait pas de croisement au sens strict, mais ses sept
références de 2017 formaient une colonne sous lui, les liens confondus et passant sur les
nœuds : elles sont maintenant en escalier vers la gauche.

**Base du banc** (`bench.py`, médiane de 3 chargements). Le graphe de la base et le
corpus de `bench` dépassent 1 000 nœuds et sont maintenant une image calculée sur le
serveur (#328) : mesurés sur les plus grands graphes de publication et les graphes
synthétiques.

| Graphe | Vue | Disposition avant | après | `untangle` | Plus longue image pendant la disposition |
|---|---|---|---|---|---|
| « Hallmarks of Cancer » (240 nœuds, 239 liens) | Frise | 81 ms | 91 ms | 5 ms | 200 → 217 ms |
| | Réseau | 121 ms | **7 ms** | — | 233 → 117 ms |
| « Fast heavy ion induced desorption » (109, 108) | Frise | 20 ms | 23 ms | 1 ms | 83 → 83 ms |
| | Réseau | 39 ms | **6 ms** | — | 100 → 17 ms |
| Publication la plus citée (35, 34) | Frise | 10 ms | 11 ms | 0,1 ms | 50 → 17 ms |
| | Réseau | 12 ms | 8 ms | — | 33 → 50 ms |
| Synthétique 500 (1 240 liens) | `placeNodes` | 722 ms | 941 ms | 198 ms | — |
| Synthétique 1 000 (2 471 liens) | `placeNodes` | 2,29 s | 2,43 s | 136 ms | — |

- Le réseau d'une publication et de ses références est presque tout en feuilles : `cose`
  ne dispose plus que le cœur, d'où 7 ms au lieu de 121.
- Les échanges coûtent peu sur les vrais graphes (moins de 6 ms) ; sur les graphes
  synthétiques, très denses, ils coûtent 0,1 à 0,2 s. Avec une limite de 600 liens par
  groupe, c'était 1,2 s sur 500 nœuds : la limite est donc de 300.
- Les animations ne changent pas : images de la sélection à 17 ms en médiane partout
  (maximum 22 à 29 ms), zoom des graphes synthétiques inchangé.

## Temps de calcul (#323)

Les dispositions vont jusqu'au temps donné par le champ « Temps de calcul » et gardent le
dessin le moins croisé (voir [graphes.md](graphes.md)). Mesuré le 22 novembre 2026,
Chrome headless à 1 400 px, sur une copie de la base de l'utilisateur : `placeNodes` et
`networkPositions` appelés dans la page avec chaque temps, croisements comptés sur les
positions finales (bande « Non daté » comprise). Le « Avant » est cette même PR avant le
temps de calcul (six départs de `cose`, échanges sur 8 voisins sans contrôle des
chevauchements).

| Croisements | Avant | 0,1 s (défaut) | 0,5 s | 2 s | 10 s |
|---|---|---|---|---|---|
| « Mon graphe », frise | 174 | 171 | 130 | 127 | **100** |
| « Mon graphe », réseau | 67 | 58 | 58 | 55 | **47** |
| Tag MT28, frise | 34 | 38 | 35 | 20 | **20** |
| Tag MT28, réseau | 26 | 21 | 17 | 17 | **17** |

- Les nombres d'avant diffèrent de la section précédente : la base de l'utilisateur a
  changé depuis, et la feuille Tailwind manquait alors à la copie de travail (le cadre
  du graphe n'avait pas de hauteur).
- Frise : les nœuds qui se recouvrent à l'écran passent de 48 à 25 sur « Mon graphe »
  (11 à 10 s) et de 7 à 0 sur le tag (au plus 3 selon le temps) : un échange ne serre plus les nœuds. D'où, au temps
  par défaut, un peu plus de croisements sur le tag (38 au lieu de 34).
- Le résultat dépend du nombre d'essais qui tiennent dans le temps : dans la page, au
  chargement, le réseau de « Mon graphe » à 0,1 s a 67 croisements (moins de départs, le
  code n'étant pas encore compilé), 58 appelé ensuite.
- Sur « Mon graphe », l'ordre de départ de la simulation fait varier ses croisements de
  156 à 367, et après les premiers échanges de 103 à 213 : les autres départs sont ce
  qui gagne le plus. Élargir seulement la fenêtre (24 voisins, blocs) gagnait peu (192 →
  180), et sans contrôle de la hauteur du groupe les nœuds se recouvraient davantage
  (39 au lieu de 19 à 2 s).
- Un groupe de plus de 300 liens (graphe aléatoire de 1 000 nœuds, 2 509 liens) : à 2 s,
  la simulation seule prend le temps et le groupe n'est pas démêlé ; à 10 s, 8 s
  d'échanges, 398 307 → 392 774 croisements, et l'échéance est tenue (10,03 s).
- Animations : pendant le calcul (dans le Web Worker), la page reste à 16,7 ms par image
  (maximum 17) ; les nœuds glissent vers leurs nouvelles positions à 16,7 ms par image en
  médiane (maximum 17), en frise comme en réseau, sur « Mon graphe » (226 éléments).

Captures côte à côte, 0,1 s à gauche et 10 s à droite : `~/revue-app/work/b5/compare/`
(`corpus-frise.png`, `corpus-reseau.png`, `tag-frise.png`, `tag-reseau.png`).

## Image longue en fin de geste (#326)

Au-delà de 600 éléments, les tailles fixes à l'écran sont réévaluées une fois le zoom
arrêté (#320). Cette réévaluation et le dessin qui suit faisaient une image de 190 à
220 ms sur le corpus de `bench` (1 775 publications, 2 517 citations, 4 292 éléments).
Mesuré le 22 novembre 2026, Chrome headless à 1 400 px, sur la base du banc.

**Où part le temps** (profil Chrome) : la réévaluation du style est répartie dans tout
Cytoscape (cascade des règles, empreintes du style, boîtes englobantes, textures des
nœuds), sans point chaud ; elle est **paresseuse** : `updateStyle` ne fait que marquer les
éléments, et le dessin suivant réévalue tous ceux qui sont marqués, dans la vue ou non.
Chaque élément dont la taille change fait aussi redessiner le cadre (événement `bounds`),
de 10 à 30 ms à cette taille.

**Pistes essayées** (outil de mesure : un zoom de 30 crans vers l'intérieur, jusqu'à
2,5 fois la vue d'ensemble, puis vers l'extérieur jusqu'à elle ; la sélection de la
publication la plus reliée, puis sa désélection ; « Vue d'ensemble » ; plus longue image
après le geste, médiane de 3 séries, en ms) :

| Corpus de `bench`, frise | Zoom avant | Zoom arrière | Désélection | Vue d'ensemble |
|---|---|---|---|---|
| Avant (tout d'un coup) | 194 | 216 | 106 | 199 (+ 245 au clic) |
| Vue d'abord, puis le reste par parties de 8 ms (**retenu**) | **132** | 218 | **87** | **18** (+ 245 au clic) |
| Tout par parties de 6 à 15 ms, vue d'abord | 110 à 122, puis 9 à 13 images de 35 à 60 ms | 60 à 80 × 8 | 56 à 94 | — |
| Nœuds de la vue d'abord, liens ensuite | 111 | 165, puis 5 images de 60 à 85 | 108 | — |
| Tailles qui suivent le zoom (aucune réévaluation) | 117 | 97 | 47 | 18 |

- **Retenu** : les éléments dans la vue (élargie de 48 px) sont réévalués d'un coup, puis
  les autres par parties de 50, 8 ms par image, lus aussitôt (`pstyle`) pour que le coût
  tombe dans l'image prévue et non au dessin suivant (`screen_size.js`). L'image longue
  suit la part du graphe dans la vue : 2 427 éléments sur 4 292 à 2,5 fois la vue
  d'ensemble, 132 ms au lieu de 194 ; les parties suivantes font des images de 35 à 55 ms.
  Quand la vue montre tout (retour à la vue d'ensemble), rien ne change.
- **« Vue d'ensemble »** réévaluait les tailles deux fois : pour se mesurer (`measure`,
  245 ms au clic, inchangé), puis 150 ms après, l'arrêt du zoom (199 ms). La seconde est
  retirée : les tailles sont déjà celles de ce zoom.
- **Tout par parties** : chaque partie fait redessiner tout le cadre, 50 à 60 ms dans la
  vue d'ensemble ; une image de 210 ms devient 8 à 10 images de 60 ms, et sur les graphes
  synthétiques, plus coûteux à dessiner, 5 images de 90 ms au lieu d'une de 150. Ce n'est
  pas mieux ; et les nœuds changent de taille par vagues, du centre vers les bords.
- **Tailles qui suivent le zoom** : plus d'image longue (il ne reste que la fin du dessin
  de Cytoscape, 45 à 60 ms, et le début du geste, 100 à 130 ms, qui ne dépendent pas des
  tailles), mais zoomer grossit les nœuds au lieu de les écarter (#185) au-delà de
  600 éléments.
- Le début d'un geste reste une image de 100 à 140 ms : Cytoscape y prend l'image du
  graphe qu'il déplace (`textureOnViewport`, #320) ; elle ne dépend pas des tailles.
- **Sélection** : l'appui lui-même bloque 245 à 265 ms (classes de la sélection posées sur
  tous les éléments, puis vue calculée), avant comme après ; seule l'image de l'arrêt du
  zoom qui suit change (90 → 40 à 60 ms).

Avec `frames.py` (médiane / 90e centile / plus longue image, puis images de plus de
50 ms ; avant → après) :

| Graphe (éléments) | Zoom | Glisser | Sélection |
|---|---|---|---|
| Corpus de `bench`, frise (4 292) | 17 / 18 / **191**, 2 → 17 / 18 / **139**, 3 | inchangé (56) | 17 / 17 / 60, 1 → 17 / 17 / 44, 0 |
| Corpus de `bench`, réseau (4 292) | 17 / 17 / **192**, 2 → 17 / 17 / **123**, 3 | inchangé (66) | 17 / 17 / 93, 1 → 17 / 17 / 52, 1 |
| Synthétique 1 000 (3 471) | 17 / 17 / 169, 4 → 17 / 18 / 176, 6 | inchangé (53) | 17 / 46 / 79, 2 → 17 / 43 / 75, 2 |
| « Hallmarks of Cancer » (479, petit graphe) | 15 / 33 / 36 → 16 / 32 / 38 | inchangé | 17 / 28 / 31 → 17 / 29 / 30 |

Le graphe synthétique, aux positions tirées au hasard sur toute la hauteur, a presque
tout dans la vue après le zoom de `frames.py` : rien n'y change. Les petits graphes
(600 éléments au plus) gardent leur réévaluation à chaque image. Après la passe, l'image
est la même qu'avant à l'œil (captures comparées : écarts de lissage au bord des nœuds,
au plus 55 pixels sur 1 400 × 1 000 qui diffèrent de plus de 40 niveaux).

## Glisser hors du cadre (#476)

Pendant un glisser, ce qui était hors du cadre au début du geste n'était pas dessiné
avant le relâchement. Mesuré le 22 novembre 2026, Chrome headless à 1 400 px, base du
banc ; `frames.py` et `image_frames.py`, médiane / 90e centile / plus longue image (ms),
images de plus de 50 ms.

**Graphes Cytoscape** (au-delà de 600 éléments) :

| Graphe (éléments) | Geste | Image déplacée (`textureOnViewport`, avant) | Liens masqués (**retenu**) | Dessin complet |
|---|---|---|---|---|
| Corpus de `bench`, frise (4 292) | Glisser | 17 / 18 / 55, 1 | 17 / 24 / 53, 1 | 17 / 39 / 45, 0 |
| | Zoom | 17 / 18 / 187, 2 | 17 / 26 / 201, 2 | 18 / 34 / 191, 4 |
| Corpus de `bench`, réseau (4 292) | Glisser | 17 / 17 / 65, 1 | 17 / 23 / 63, 1 | — |
| | Zoom | 17 / 17 / 198, 2 | 16 / 26 / 192, 1 | — |
| Synthétique 1 000 (3 471) | Glisser | 17 / 17 / 52, 1 | 17 / 20 / 51, 1 | 48 / 52 / 56, 19 |
| | Zoom | 17 / 17 / 154, 4 | 17 / 21 / 151, 2 | 17 / 51 / 135, 10 |

- **Liens masqués** : les nœuds sont redessinés à chaque image, ce qui entre dans le cadre
  apparaît aussitôt ; le 90e centile monte de 17–18 à 20–26 ms, la médiane reste à 17.
  Les liens reviennent au relâchement. C'était déjà la règle au-delà de 5 000 éléments.
- **Dessin complet** : fluide en médiane sur le corpus, mais 48 ms par image sur le
  graphe synthétique de 1 000 publications, plus dense en liens.
- Les petits graphes (600 éléments au plus) ne changent pas : ni image, ni liens masqués.

**Image d'un grand graphe** (`image_view.js`) : le SVG est dessiné avec une marge autour
du cadre. Mêmes mesures avec une marge de 0 (avant), d'un demi-cadre et d'un cadre de
chaque côté (retenu) :

| Image | Marge | Chargement | Zoom | Glisser | Survol |
|---|---|---|---|---|---|
| Auteurs (9 507 nœuds, 56 389 liens) | 0 | 490 ms | 17 / 17 / 370, 2 | 17 / 17 / 19 | 17 / 18 / 20 |
| | ½ cadre | 516 ms | 17 / 17 / 366, 1 | 17 / 17 / 19 | 17 / 19 / 36 |
| | 1 cadre | 490 ms | 17 / 17 / 361, 1 | 17 / 17 / 18 | 17 / 19 / 25 |
| Base (1 797, 2 539) | 0 | 153 ms | 17 / 17 / 25 | 17 / 17 / 19 | 17 / 18 / 22 |
| | 1 cadre | 116 ms | 17 / 17 / 21 | 17 / 17 / 18 | 17 / 18 / 19 |

- La marge ne coûte rien de mesurable : le navigateur dessine un SVG par ses éléments
  plus que par sa surface. Un glisser d'au plus un cadre dans chaque direction montre
  donc tout de suite le graphe ; la position est la même au pixel près avant et après le
  redessin du relâchement.

## Positions gardées dans le navigateur (#327)

Chaque disposition est gardée dans IndexedDB sous l'empreinte de ce qu'elle lit
(`layout_cache.js`, voir [graphes.md](graphes.md)). Mesuré le 22 novembre 2026, Chrome
headless à 1 400 px, base du banc : trois chargements de suite dans un profil neuf,
médiane de 3 profils. `layout` : la disposition (ou la lecture de celle gardée), `shown` :
le graphe affiché, depuis le début de la navigation (ms).

| Graphe | Temps de calcul | `main`, chaque visite (`layout` / `shown`) | 1re visite | 2e visite |
|---|---|---|---|---|
| Corpus de `bench`, frise (1 775 nœuds, 2 517 liens) | 0,1 s | 431 à 488 / 1 622 à 1 847 | 506 / 1 965 | **15 / 1 225** |
| Corpus de `bench`, réseau | 0,1 s | 289 à 323 / 1 465 à 1 723 | 296 / 1 718 | **12 / 1 219** |
| Corpus de `bench`, frise | 2 s | 2 048 à 2 218 / 3 147 à 3 363 | 2 070 / 3 278 | **14 / 1 177** |
| Corpus de `bench`, réseau | 2 s | 1 719 à 1 798 / 2 809 à 2 930 | 1 776 / 2 907 | **10 / 1 105** |
| « Hallmarks of Cancer », frise (240, 239) | 0,1 s | 89 à 101 / 265 à 540 | 112 / 604 | **8 / 204** |
| « Hallmarks of Cancer », réseau | 0,1 s | 11 à 21 / 190 à 475 | 28 / 515 | **9 / 224** |

- **La deuxième visite** lit la disposition en 8 à 15 ms au lieu de la refaire : le
  graphe s'affiche 0,4 à 2,2 s plus tôt sur le corpus, et toujours **au même endroit**
  (positions identiques d'une visite à l'autre ; sans la mémoire, à 2 s de calcul, deux
  visites sur trois donnaient un autre dessin, le nombre d'essais dépendant de la charge).
- La première visite ne coûte presque rien de plus : l'empreinte prend 3 à 6 ms pour
  1 775 nœuds (`JSON.stringify` et un hachage de 64 bits), l'écriture se fait après.
  La première visite de chaque ligne compte aussi le démarrage du navigateur.
- **Donnée changée** : le titre d'une publication modifié entre la 2e et la 3e visite, la
  disposition est refaite (337 ms au lieu de 10 sur le réseau du corpus).
- **Sans IndexedDB** (accès qui lève une erreur, ou base qui ne répond pas) : le graphe
  s'affiche comme sur `main`, sans erreur ; une base muette coûte l'attente de 0,3 s.
- Un nouveau temps de calcul est gardé à son tour : la page rechargée avec ce temps lit sa
  disposition (12 ms au lieu de 0,5 s).
- La plus longue image au premier chargement du corpus (900 ms) est la création du
  graphe et son premier dessin, sur `main` comme ici ; selon l'instant où la disposition
  finit, `bench.py` la compte ou non dans `layoutFrameMax`.
