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
  200 ms (maximum à 190–480 ms), perceptible comme un à-coup à la fin du geste ;
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
   HTML au-delà du même seuil (fait, « Survol léger »). Reste l'image longue à la fin
   d'un geste.
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
