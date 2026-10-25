# Découverte d'articles

Ce que l'application suggère de lire à partir du corpus d'un utilisateur.
Retour au [sommaire](architecture.md).

## Suggestions par co-citation

Page « Suggestions » (`/corpus/suggestions/`, `views/suggestions.py`,
`services/suggestions.py`, #162). Si plusieurs articles du corpus citent la même
publication, elle est sans doute centrale pour le sujet. La page liste les publications
citées par au moins `MIN_CITING` (2) publications d'un **contexte**, de la plus citée à
la moins citée.

- **Contexte** : tout le corpus (par défaut), ou un tag avec ses sous-tags
  (`?tag=Projet` compte aussi les articles tagués « Projet/Groupe », comme le filtre de
  « Mes références », `tags.tagged`). Un tag qui n'existe plus ramène à tout le corpus,
  avec un message.
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
- **Accès** : la navigation (« Mon corpus › Suggestions ») et le bouton « Suggestions »
  de « Mes références », qui garde le tag filtré.

## Citations entrantes

Section « Cité dans toute la littérature » de la fiche d'une publication avec DOI
(`services/incoming_citations.py`, modèle `IncomingCitations`, #163). « Cité par » ne
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
