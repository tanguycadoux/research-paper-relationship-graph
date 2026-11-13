# Auteurs : affiliations et ORCID

Ce que les sources apportent sur les **auteurs** d'une publication, au-delà des noms
publiés : leurs affiliations (OpenAlex), leurs ORCID (OpenAlex), leurs noms déclarés et
leur profil (ORCID). Ces sources complètent seulement : elles ne font foi pour rien. Le
parcours général d'un import est dans [sources.md](sources.md) ; les corrections
d'auteurs (fusions, doublons, même ORCID) dans [corrections.md](corrections.md#auteurs).
Vue d'ensemble du projet : [architecture.md](architecture.md).

## Affiliations

Une affiliation est une propriété de la **signature** (`AuthorPublication.organizations`),
pas de la personne : « sur cet article, X a déclaré le laboratoire Y ». Les périodes d'un
auteur dans une organisation (première et dernière publication) **se calculent** et ne
sont pas stockées : un changement de laboratoire apparaît naturellement.

Les institutions viennent d'OpenAlex. Elles sont rattachées aux signatures par **position
et nom publié** : les mots du nom sont comparés quel que soit leur ordre, si bien que
« Thuillier, Thomas » (DataCite) correspond à « Thomas Thuillier ». Si le nombre d'auteurs
ou un nom diffère, rien n'est rattaché pour l'article. Deux cas ne sont pas des
désaccords (#265) :

- **Liste tronquée par OpenAlex.** OpenAlex ne donne jamais plus de 100 auteurs par
  œuvre (`OPENALEX_MAX_AUTHORS`), et ses réponses stockées n'ont pas toujours le champ
  `is_authors_truncated`. Quand OpenAlex en donne exactement 100 et la fiche davantage
  (945 chez Crossref pour `10.1007/lrr-2016-1`), on compare les 100 premiers, et seuls
  ceux-là reçoivent leurs affiliations.
- **Liste vide d'un côté.** Une liste vide ne contredit rien. Si OpenAlex n'a pas
  d'auteurs, il n'y a simplement rien à rattacher. Si la source prioritaire n'en donne
  aucun (« Private Classical Communication », `10.1017/9781316809976.027`, sans auteur
  chez Crossref), la fiche prend ceux de la réponse OpenAlex du même DOI
  (`metadata_formats.openalex_authors` : nom publié `raw_author_name`, ORCID). Une
  publication citée, analysée avant l'arrivée de sa réponse OpenAlex, est analysée de
  nouveau à ce moment-là.

Une organisation est reconnue par
son identifiant OpenAlex ou par son ROR. Les liens sont recréés à chaque analyse, puisque
les signatures le sont aussi.

**Hiérarchie.** Les auteurs déclarent souvent plusieurs niveaux à la fois (« IRFU, CEA
Paris-Saclay »). OpenAlex donne la **lignée** de chaque institution, c'est-à-dire tous ses
ancêtres : IRFU appartient à la Direction de la Recherche Fondamentale, qui appartient au
CEA. Chaque organisation connaît ses ancêtres. Ceux qui ne figurent dans aucune signature
sont récupérés pendant l'étape OpenAlex, en une requête groupée (`/institutions?filter=
openalex:…`), pour que le parser n'ait jamais à appeler le réseau. Sur la fiche d'un
auteur, les organisations sont **regroupées par tutelle** (organisation sans ancêtre),
avec le détail des entités déclarées. Une unité mixte (CEA Paris-Saclay : CEA et
Université Paris-Saclay) apparaît sous chacune de ses tutelles.

Sur la fiche d'une publication, les affiliations sont présentées **comme dans un
article** : chaque auteur porte en exposant le numéro de ses affiliations, listées une
seule fois sous les auteurs, dans l'ordre d'apparition. Une signature n'affiche que ses
organisations **les plus précises** : celles qui sont l'ancêtre d'une autre organisation
de la même signature sont retirées (IRFU plutôt que IRFU et CEA).

La commande `complete_affiliations` complète les publications déjà en base à partir des
données OpenAlex stockées, sans les redemander. L'option `--fetch-missing` interroge
d'abord OpenAlex, par lots, pour celles qui n'ont pas encore de réponse. L'option
`--refresh-ancestors` redemande les ancêtres déjà connus, pour réparer leurs propres
ancêtres.

## ORCID complétés depuis OpenAlex

Pour les auteurs rapprochés (même position, même nom publié), l'ORCID donné par OpenAlex
est attribué à l'**auteur** s'il n'en a pas. S'il en a un autre, rien ne change et un
conflit est signalé : « Prendre la valeur proposée » remplace alors l'ORCID. L'ORCID
publié de la signature (`published_orcid`, donnée Crossref) n'est jamais modifié : il fait
partie de la clé qui retrouve un auteur au ré-import. Mesuré sur la base réelle : les
auteurs avec ORCID passent de 35 à 74 sur 135, sans conflit. 11 ORCID se retrouvent
alors chacun sur plusieurs auteurs : ce sont des doublons certains, fusionnés
automatiquement ([corrections.md](corrections.md#même-orcid)).

## Noms et profil ORCID

L'API publique ORCID répond sans clé, en JSON quand on le demande (en-tête `Accept`).

**Profil, à la demande.** L'enregistrement d'une personne
(`https://pub.orcid.org/v3.0/<orcid>/record`) donne en une requête le profil et le résumé
des travaux. Il n'est **jamais demandé à l'import** : un article peut avoir plus de 1 000
auteurs. Le bouton « Compléter depuis ORCID » de la fiche d'un auteur qui a un ORCID le
demande, et la réponse est stockée (`OrcidRecord`). En cas d'échec, l'enregistrement déjà
stocké est gardé.

La fiche montre, à titre d'information, sans rien modifier dans la base (#59) :
- le nom officiel, le nom d'usage et les autres noms déclarés (« J. Carberry ») ;
- le nombre de travaux déclarés et combien sont dans la base, retrouvés par leur DOI ;
- les travaux de la base où l'auteur ne figure pas parmi les signataires : un nom publié
  rattaché à un autre auteur, ou un ORCID manquant.

**Noms, à l'import** (`services/imports/orcid_names.py`, #220). La recherche étendue
(`/expanded-search/?q=orcid:(A OR B …)`) donne les noms de 50 personnes en une requête
(mesuré : une URL de 1 200 caractères, une demi-seconde). À l'import d'une publication,
les auteurs dont l'ORCID n'a jamais été demandé le sont en une requête groupée ; ceux des
publications citées sont laissés à la commande `complete_orcid_names`, qui traite aussi
les auteurs déjà en base (`--refresh` redemande tout). ORCID donne le nom que la personne
déclare, souvent plus complet que le nom publié, mais rien n'est écrasé :
- un prénom qui **prolonge** le prénom connu le complète, mot par mot : « T. » devient
  « Thomas », « A. K. » devient « Angie K. » ; un prénom moins complet ne change rien ;
- le **nom de famille** de la base est gardé, sa casse étant plus fiable (« SIMON »,
  « vallcorba » sur ORCID) ; un prénom tout en minuscules ou en majuscules est remis en
  forme ;
- un nom qui **diffère** vraiment est signalé comme conflit (« Nom différent selon
  ORCID ») : un ORCID peut être mal attribué, notamment par la complétion OpenAlex ;
- un nom **corrigé à la main** (`name_edited`) n'est jamais modifié, et un nom non public
  ne change rien.

Le bouton de la fiche applique les mêmes règles au nom de l'enregistrement complet. Tant
que celui-ci n'a pas été demandé, la fiche montre les noms de la recherche groupée et
propose « Charger les travaux depuis ORCID ». Sur la base réelle : 59 ORCID en 2
requêtes, 42 prénoms complétés, 2 conflits légitimes (un nom mal découpé par Crossref,
« E. Fernandez Mora » ; un vrai désaccord).

Les autres noms déclarés permettraient plus tard de rapprocher automatiquement des
auteurs, et les travaux de relier un auteur à ses articles. On attend de voir ce que
donnent les données avant de l'automatiser.
