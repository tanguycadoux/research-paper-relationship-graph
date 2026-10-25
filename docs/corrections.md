# Corrections

Les données des sources sont parfois incomplètes ou fausses : références sans DOI, auteurs
écrits de plusieurs façons, sources qui se contredisent. Les corrections sont **communes à
tous les utilisateurs**, tracées, et survivent aux ré-imports. Vue d'ensemble du projet :
[architecture.md](architecture.md).

## Références citées

### Identifier une référence

`identification.py` : une référence citée est reliée à une publication par DOI, par ISBN,
ou en créant une publication sans identifiant ; ou elle est déclarée non identifiable
(rapport interne, présentation, communication privée…), et ne compte plus parmi celles à
identifier. La décision est tracée (qui, quand) et survit aux ré-imports : la référence
est retrouvée par sa clé Crossref, ou par sa position à défaut, et la correction
l'emporte sur la source.

La page propose d'abord des **publications candidates** (`candidates.py`, #160), jamais
reliées sans un clic sur « C'est celle-ci » :

- Crossref sur le texte complet de la référence (`query.bibliographic`), DataCite sur
  son titre seul (actes JACoW, prépublications arXiv ; sur le texte complet, DataCite
  exige tous les mots et ne trouve rien), le DOI d'un code JACoW écrit dans la
  référence, et les publications de la base au titre proche. Le titre est le champ
  structuré, ou la phrase qui suit les auteurs dans le texte brut.
- Le score de Crossref ne se compare pas d'une recherche à l'autre : chaque candidat est
  vérifié ici. Titres proches dans les deux sens (le plus long au plus deux fois plus
  long), année à ±1 près, premier auteur exigé si le titre n'est que proche ; copies
  ResearchGate écartées. Sur les 32 références à identifier de la base, le bon candidat
  sort en tête pour les 22 qui ont un DOI.
- Les réponses des sources sont gardées sur la référence (deux requêtes au premier
  affichage, puis aucune) ; « Relancer la recherche » les oublie. Une source qui ne
  répond pas n'est pas mise en cache.

**DOI saisi à la main** (`doi_registration.py`, #240) : il est d'abord soumis à doi.org
(`/ra/`, qui répond pour toutes les agences). S'il n'existe pas, le formulaire le refuse
au lieu de créer une publication vide. Même règle pour l'ajout au corpus par DOI et pour
l'import d'un fichier (une requête pour 20 DOI ; une entrée au faux DOI passe par son
ISBN si elle en a un, sinon elle est écartée et listée). Les identifiants `10.5555/…` de
l'ACM Digital Library ressemblent à des DOI sans en être. La requête est évitée si une
publication de la base, avec métadonnées, porte ce DOI ; si doi.org ne répond pas, le DOI
est accepté.

**En série** (#242) : « Identifier en série », sur la fiche, enchaîne les références à
identifier de la publication, par position. Après chaque décision, la page passe à la
suivante au lieu de revenir à la fiche ; « Passer » la laisse à identifier, et
« Terminer » revient à la fiche. La série tient dans l'URL (`?serie=1`) et dans un champ
caché des formulaires : pas de session ni de modèle.

Pas de rapprochement automatique des références au texte identique : sans DOI ni ISBN,
rien ne prouve qu'il s'agit du même ouvrage.

## Publications

- **Modifier une publication** (`publication_edits.py`, #146) : un titre ou une date
  corrigés sont marqués et ne sont plus réécrits par les analyses suivantes ; la fiche le
  signale, et « Revenir aux valeurs des sources » relit la réponse stockée, sans requête.
  Un champ vidé redevient celui de la source. Un **nouveau DOI ou ISBN** désigne une autre
  œuvre : les réponses des sources, les signatures et la bibliographie de l'ancien sont
  supprimées (avec les auteurs restés sans publication), puis le nouveau est importé.
- **« Cette publication est en fait… »** (`publication_merge.py`) : une publication sans
  DOI ni ISBN peut être fusionnée dans une autre, désignée par un DOI, un ISBN ou le lien
  de sa page. Ses citations sont reportées et marquées comme corrections manuelles, ses
  entrées de corpus sont reportées sans doublon (`publication_moves.py`), puis elle est
  supprimée. Une publication identifiée ne peut pas être fusionnée de cette façon.
- **Suppression** : uniquement depuis l'administration Django, qui liste ce qui part en
  cascade (#77).

## Auteurs

- **Modifier un auteur** : un prénom ou un nom changé marque le nom comme corrigé
  (`name_edited`), et ORCID ne le modifie plus (#220).

### Fusion d'auteurs

`services/author_merge.py` : pour chaque champ (prénom, nom, ORCID), on propose les valeurs
des auteurs fusionnés, ou une autre valeur saisie. Par défaut, on prend la forme la plus
complète : sans initiale, pas tout en capitales, puis la plus longue. Pour l'ORCID, on
prend le premier existant. Deux ORCID différents désignent en général deux personnes :
la fusion demande alors une confirmation explicite. Les noms publiés restent sur chaque
publication (`AuthorPublication`), si bien qu'aucune variante n'est perdue et que la
fusion résiste aux ré-imports. Chaque fusion, manuelle ou automatique, est tracée
(`AuthorMerge`) et listée sur la fiche de l'auteur.

### Doublons probables

`services/author_duplicates.py`. Les auteurs sont regroupés par nom de famille normalisé,
sans accents ni casse. Deux prénoms sont compatibles mot à mot : identiques, ou une
initiale qui correspond à la première lettre de l'autre (« J.-L. » et « Jean Luc »). Un
auteur n'entre dans un groupe que s'il est compatible avec **tous** ses membres : sinon,
« J. » relierait « John » et « James ». Deux ORCID différents ne sont jamais regroupés, et
deux auteurs qui ont le **même** ORCID le sont toujours, quelle que soit l'écriture de
leurs noms. Les noms de famille sont comparés sans tenir compte des tirets ni de la
ponctuation (« Correia-Machado » = « Correia Machado »).

Une **tutelle commune** (organisation de plus haut niveau, par exemple le CEA) déclarée
par au moins deux auteurs d'un groupe est affichée et fait remonter le groupe. Ce n'est
qu'un indice : des organisations différentes ne séparent jamais deux auteurs, car les
chercheurs changent de laboratoire. Les groupes qui comptent exactement un ORCID viennent
en premier. La page renvoie vers la fusion habituelle, après qu'on a éventuellement
décoché des auteurs.

On peut aussi déclarer les auteurs cochés comme **personnes différentes**
(`AuthorDistinction`, paire stockée une fois, avec qui l'a déclarée et quand) : la paire
n'est plus jamais proposée, comme deux ORCID différents. Lors d'une fusion, les
distinctions de l'auteur absorbé sont reportées sur l'auteur conservé.

### Même ORCID

`services/orcid_merge.py`, #158. Un ORCID désigne une seule personne : quand un auteur
reçoit un ORCID déjà porté par un autre (complétion depuis OpenAlex, « Modifier », fusion
manuelle, conflit d'ORCID accepté), ils sont fusionnés automatiquement dans le plus
ancien, avec la forme de nom la plus complète. Le cas venait surtout de la complétion
OpenAlex : « S. Prestemon », publié sans ORCID, devenait un second auteur qui recevait
ensuite l'ORCID de « Soren Prestemon ». Des auteurs **déclarés distincts** ne sont jamais
fusionnés : l'ORCID partagé est signalé comme conflit informatif. La commande
`merge_same_orcid` traite les auteurs déjà en base.

## Conflits

Quand une source contredit une valeur connue, l'existant est gardé et le conflit est
signalé sur la page « Conflits » (`MetadataConflict`, `services/conflicts.py`). La règle
générale (qui fait foi, qui complète) est dans
[sources.md](sources.md#informations-contradictoires-entre-sources).

| Type | Signalé quand | « Prendre la valeur proposée » |
|---|---|---|
| ORCID différent | OpenAlex donne à un auteur un autre ORCID que le sien | Remplace l'ORCID (et fusionne avec un auteur qui le porte déjà) |
| Nom différent selon ORCID | Le nom déclaré sur ORCID ne prolonge pas le nom connu | Remplace prénom et nom |
| Version publiée selon OpenAlex | OpenAlex regroupe une prépublication avec une version publiée vérifiée chez Crossref | Remplace la prépublication par sa version publiée, ou la fusionne avec elle |
| Auteurs différents selon les sources | Les auteurs d'OpenAlex ne concordent pas avec les auteurs publiés (Crossref ou DataCite) | Informatif : seulement « Vu » (les affiliations ne sont pas rattachées) |
| ORCID porté par des auteurs déclarés distincts | Un même ORCID sur des auteurs qu'un humain a déclarés différents | Informatif : seulement « Vu » |

- Un conflit n'est signalé qu'**une fois** (objet, champ, valeur proposée) : une décision
  n'est jamais rouverte par un ré-import. Un conflit devenu obsolète (les sources
  concordent de nouveau) disparaît.
- Les décisions sont communes, tracées (qui, quand) ; les dernières sont listées à la
  seconde près.
- La page montre ce qu'il faut pour trancher sans requête : un nom dans un tableau
  prénom / nom, avec les mots répartis autrement signalés (#244) ; une version publiée
  avec son titre, sa revue et son année (`MetadataConflict.details`).
- Le nombre de conflits ouverts est compté dans la navigation.
