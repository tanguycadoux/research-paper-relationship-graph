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
