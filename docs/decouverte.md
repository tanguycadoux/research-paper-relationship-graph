# Découverte d'articles

Ce que l'application suggère de lire à partir du corpus d'un utilisateur.
Retour au [sommaire](architecture.md).

## Suggestions par co-citation

Page « Suggestions » (`/corpus/suggestions/`, `views/suggestions.py`,
`services/discovery/suggestions.py`, #162). Si plusieurs articles du corpus citent la même
publication, elle est sans doute centrale pour le sujet. La page liste les publications
citées par au moins `MIN_CITING` (1) publication d'un **contexte**, de la plus citée à
la moins citée ; « Citées par au moins 1 / 2 articles » (`?min=2`) resserre la liste.

- **Contexte** : tout le corpus (par défaut), ou un tag avec ses sous-tags
  (`?tag=Projet` compte aussi les articles tagués « Projet/Groupe », comme le filtre de
  « Mon corpus », `tags.tagged`). Un tag qui n'existe plus ramène à tout le corpus,
  avec un message. Le graphe d'un tag partage ce contexte (`tags.context_publications`,
  `views/tag_context.py`, #290 : voir [graphes.md](graphes.md)).
- **Calcul** : une agrégation sur `CitedReference.target`, en base, sans appel externe.
  Seules les références identifiées comptent ; la page dit combien de références du
  contexte restent à identifier. Une publication qui cite deux fois la même compte
  une fois.
- **Ce qui est exclu** : les publications du contexte. Pour tout le corpus, c'est tout le
  corpus. Pour un tag, une publication du corpus rangée ailleurs reste suggérée, marquée
  « déjà dans mon corpus » avec ses tags, et un bouton lui ajoute le tag du contexte :
  elle a peut-être été oubliée en taguant.
- **Affichage** : les publications citantes sont dans un panneau (popover) ouvert depuis
  leur nombre ; listées dans la ligne, elles la rendaient très haute. Les boutons
  d'ajout sont ceux des autres tableaux (« à lire », puis « + »).
- **Tris** (#432, `SUGGESTIONS` dans `suggestions.py`, `?sort=` comme les autres
  tableaux, en-têtes `column_header` et `sort_links` sous sm) : par articles du contexte
  qui la citent (par défaut), par **citations dans la littérature**, par **citations par
  an** et par **importance**, ainsi que par titre, auteur et année. Les égalités gardent
  l'ordre par défaut (citée par, puis la plus récente, puis le titre).
  - *Citations* : `cited_by_count` de la réponse OpenAlex gardée, sinon
    `is-referenced-by-count` de Crossref (`literature_citations`, une sous-requête sur
    `ExternalRecord`). Aucune requête de plus : le nombre date de l'import, sa source et
    sa date sont dans l'infobulle, « Rafraîchir les métadonnées » le met à jour. Sans
    nombre, une publication est en fin de liste, dans les deux sens.
  - *Par an* : les citations divisées par les années écoulées depuis l'année de
    publication, 1 au moins (une publication de l'année compte pour un an).
  - *Importance* : le PageRank (igraph, amortissement 0,85) du graphe des citations
    identifiées, sans les autocitations (`services/discovery/importance.py`). Affiché
    relativement à la plus importante des suggestions (100), avec une barre. Le tri se
    fait en Python sur toute la liste (quelques centaines de lignes), les autres en SQL.
  - *Portée du PageRank* : `importance.SCOPE`. `SCOPE_BASE` (par défaut) le calcule sur
    toute la base, une fois pour tous, gardé dans le cache de Django sous une clé qui
    contient la signature des citations identifiées (nombre, dernier id, sommes des
    sources et des cibles) : une citation identifiée, retirée ou déplacée change la clé.
    `SCOPE_CONTEXT` le calcule à chaque page sur le sous-graphe du contexte et des
    publications qu'il cite. Mesures sur la base de l'utilisateur (629 publications,
    904 citations) : 4 ms sans cache pour la base, 1 ms avec (la signature) ; 2 à 5 ms
    pour un contexte. Comparaison des deux portées dans la PR de #432.
- **Accès** : la navigation (« Mon corpus › Suggestions ») et le bouton « Suggestions »
  de « Mon corpus », qui garde le tag filtré.

## Citations entrantes

Section « Cité dans toute la littérature » de la fiche d'une publication avec DOI
(`services/discovery/incoming_citations.py`, modèle `IncomingCitations`, #163). « Cité par » ne
voit que les bibliographies importées dans la base ; OpenAlex connaît les publications
qui citent celle-ci partout (`GET /works?filter=cites:W…`).

- **À la demande seulement** : un bouton de la fiche (connecté), jamais à l'import. Un
  article ancien peut avoir des milliers de citants, et chaque liste filtrée consomme le
  budget quotidien gratuit d'OpenAlex (environ 1 000 requêtes par jour et par adresse IP,
  sans clé).
- **Deux requêtes au plus** : les 25 plus citées (`PER_ORDER`), puis les 25 plus récentes
  si les premières ne sont pas toutes les citantes. Le total vient de `meta.count`. L'id
  OpenAlex de la publication vient de sa réponse OpenAlex stockée, sinon d'une recherche
  par DOI, gratuite.
- **Cache** : la réponse résumée est gardée en base avec sa date ; « Relancer la
  recherche » la remplace. Ce n'est pas le cache HTTP de développement (`http.py`) : c'est
  une donnée affichée, qui doit tenir en production. Si OpenAlex ne répond pas, rien
  n'est remplacé.
- **Pas de `Publication` créée** pour un citant : le tableau les montre (les plus citées
  ou les plus récentes, `?citants=`) ; un citant déjà dans la base renvoie à sa fiche,
  marqué s'il est dans le corpus. Les boutons d'ajout passent par son DOI
  (`corpus_add_by_identifier`, avec `next`) : la publication n'est créée qu'à ce
  moment. Un citant sans DOI renvoie à OpenAlex, sans ajout possible.
- OpenAlex peut avoir deux fiches pour un même article (prépublication et version
  publiée) : elles apparaissent telles quelles.

## Chercher une publication par son titre

Pour ajouter une publication dont on ne connaît pas le DOI (#309) :
`/publications/by-title/`, atteinte par « Chercher par titre » sous le champ « Ajouter ».
On y saisit un titre (au moins deux mots significatifs), et si on les connaît, le nom du
premier auteur et l'année.

- **Sources** : la base d'abord (`candidates.publications_titled`), pour ne pas recréer
  une publication connue ; puis Crossref (`query.bibliographic` sur « auteur titre année »,
  10 résultats) et DataCite (le titre). Une requête par source à l'envoi du formulaire,
  jamais à la frappe ; les réponses sont gardées 10 minutes dans le cache de Django, si
  bien que revenir aux résultats après un ajout ne demande rien.
- **Vérification** : celle des candidats d'une référence (#160, `candidates.select_likely`),
  avec deux différences. Sans auteur saisi, aucun n'est exigé. Le titre saisi peut n'être
  qu'un morceau du vrai titre : un candidat qui en contient presque tous les mots est
  gardé même s'il est bien plus long, et les candidats sont classés par part des mots
  saisis retrouvés, le titre identique d'abord, puis dans l'ordre des sources (8 au plus).
- **Ajout** : par les boutons des tableaux de publications : par sa fiche si la
  publication est dans la base, sinon par son DOI (vérification doi.org, file des
  récupérations, corpus ou « à lire »). Aucune publication n'est créée avant ce clic.

Mesuré sur 8 publications de la base de développement : avec le titre entier comme avec
ses six premiers mots, la bonne publication est la première proposée dans les 16 cas.
`query.bibliographic` a trouvé autant que `query.title` + `query.author` sur ces cas : il est gardé.
