# Prépublications arXiv et actes JACoW

Deux sortes de documents très cités en physique (des accélérateurs en particulier), dont
les DOI sont chez **DataCite** et non chez Crossref : les prépublications arXiv
(`10.48550/arXiv.…`) et les actes des conférences JACoW (`10.18429/JACoW-…`). Leurs
auteurs écrivent souvent leur identifiant plutôt que leur DOI. Le parcours général d'un
import est dans [sources.md](sources.md) ; vue d'ensemble du projet :
[architecture.md](architecture.md).

## Identifiants arXiv saisis

Un chercheur copie plus souvent l'identifiant ou le lien arXiv que le DOI
`10.48550/arXiv.…` (#267). `services/identifiers/arxiv.py` réunit leur lecture :

- `arxiv_doi` : une saisie entière, `arXiv:1706.03762`, `1706.03762v5`,
  `arxiv.org/abs/…` ou `arxiv.org/pdf/…(.pdf)`, et les anciens identifiants
  (`hep-th/9901001`). La version est ignorée : le DOI désigne l'article.
- `typed_doi` : ce qu'un utilisateur saisit comme DOI, écrit comme un DOI ou comme un
  identifiant arXiv. L'ajout au corpus, « Cette publication est en fait… » et la méthode
  « DOI ou arXiv » de l'identification d'une référence l'utilisent ; le DOI obtenu suit
  ensuite le chemin d'un DOI saisi, vérification par doi.org comprise.
- `bare_arxiv_doi` : le champ `eprint` d'un fichier BibTeX (#165).
- `written_arxiv_doi` : un identifiant écrit dans un texte (bibliographie des sources
  LaTeX, référence citée sans DOI : voir ci-dessous).

## Identifiants écrits dans une référence

Une référence sans DOI écrit souvent l'identifiant de ce qu'elle cite. Ce sont des
identifiants **écrits par les auteurs**, pas des rapprochements : ils sont reliés à
l'import d'une bibliographie (`services/imports/written_identifiers.py`), comme un DOI.

- **Code JACoW** (#160). Les DOI des articles JACoW ont une forme fixe :
  `10.18429/JACoW-<CONFÉRENCE><ANNÉE>-<CODE>` (vérifié sur 5 000 de leurs 26 000 DOI ; les
  autres formes sont des volumes entiers). Un code `JACoW-IPAC2019-WEPRB007` écrit dans
  une référence donne donc son DOI (`jacow.written_jacow_doi`).
- **Identifiant arXiv** (#266). 16 références de « Deep learning »
  (`10.1038/nature14539`) donnent `Preprint at http://arxiv.org/abs/1409.4842`, d'autres
  `arXiv preprint arXiv:1512.03385` ou `arXiv:hep-th/9711200` (`written_arxiv_doi`).

Le code JACoW est essayé d'abord, plus précis. Garde-fou commun : une référence n'est
reliée que si DataCite connaît le DOI **et** que son titre se retrouve dans la référence.
Sinon rien n'est créé : un identifiant faux ou trop ancien ne laisse pas de publication
vide dans la base. Les DOI des deux sortes que la base ne connaît pas encore partent en
un seul appel à DataCite, par lots. Une prépublication reliée ainsi est ensuite remplacée
par sa version publiée déclarée (voir plus bas), comme une prépublication citée par son
DOI ; une prépublication déjà remplacée dans la base est retrouvée par son `preprint_doi`.

La commande `link_written_identifiers` applique la même liaison aux bibliographies déjà
importées. Sur la page d'identification, un code JACoW écrit dans la référence est aussi
proposé comme candidat ([corrections.md](corrections.md#identifier-une-référence)).

## Prépublications arXiv

### Version publiée déclarée

Les DOI arXiv (`10.48550/arXiv.…`) sont chez DataCite, sans bibliographie (#227). Quand
les auteurs déclarent sur arXiv le DOI de la version publiée, DataCite le donne en
`IsVersionOf` : la publication est alors **remplacée** par cette version
(`services/imports/preprints.py`), dont Crossref fournit métadonnées et bibliographie.
Elle garde ses entrées de corpus, ses citations et ses corrections ; le DOI arXiv passe
dans `preprint_doi`. Si la version publiée est déjà en base, la prépublication fusionne
avec elle (corpus et citations déplacés). Les références citées importées par lots le
sont aussi, avec un lot Crossref pour les versions déclarées.

Garde-fous, puisqu'on ne remplace que sur une information fiable :
- seul le préfixe arXiv compte (chez Zenodo, `IsVersionOf` relie une version à son concept) ;
- Crossref doit connaître le DOI comme publication (article de revue ou de conférence,
  chapitre, livre), jamais `posted-content` : des copies d'articles arXiv sont déposées
  ailleurs sous de nouveaux DOI (`10.65215/…` pour « Attention Is All You Need ») ;
- les titres doivent se ressembler (60 % des mots du plus court dans l'autre) : une faute
  de frappe dans le DOI déclaré désignerait un autre article.

Toutes les recherches par DOI passent par `Publication.objects.with_doi` /
`get_or_create_doi`, qui regardent aussi `preprint_doi`. La commande `replace_preprints`
applique le remplacement aux publications déjà en base, sans nouvel appel à DataCite.

### Version publiée trouvée par OpenAlex

Quand les auteurs ne déclarent rien, OpenAlex regroupe souvent la prépublication et sa
version publiée sous une même œuvre : ses `locations` donnent les DOI de toutes les
versions (`openalex_api.work_dois`). Ce regroupement est automatique et parfois faux (il
range les copies `10.65215/…` avec « Attention Is All You Need ») : la version n'est donc
jamais appliquée d'office, mais **proposée** comme conflit « Version publiée selon
OpenAlex » (`services/imports/published_versions.py`).

- À la fin d'un import, pour la publication et, avec ses références, celles qu'elle cite :
  les DOI non arXiv de leur œuvre OpenAlex sont vérifiés chez Crossref en une requête par
  lot. Le premier qui passe les garde-fous ci-dessus et deux de plus (même premier auteur,
  année au moins égale à celle de la prépublication) est proposé ; une prépublication
  n'est examinée qu'une fois.
- « Prendre la valeur proposée » redemande la version à Crossref, la remplace comme une
  version déclarée (`replace_preprint`, ou fusion si elle est déjà en base, le conflit
  suivant la version publiée), puis la réimporte. Sans réponse de Crossref, rien n'est
  décidé.
- La fiche de la prépublication signale la proposition tant qu'elle est ouverte.
- `replace_preprints` propose aussi les versions des prépublications déjà en base, en
  redemandant leur œuvre OpenAlex quand elle manque.

### Bibliographie tirée des sources arXiv

Une prépublication sans version publiée déclarée n'a de bibliographie nulle part
ailleurs que dans le texte de ses auteurs. arXiv ne lance pas BibTeX : les auteurs
déposent le `.bbl`, ou écrivent `thebibliography` dans le `.tex`. Quand une telle
prépublication entre dans un corpus (ou par « Importer ses références »), son e-print
est téléchargé **une fois** (`arxiv_api.py`, 30 Mo au plus, lu en mémoire sans rien
extraire sur le disque) ; les entrées `\bibitem` sont stockées brutes dans un
`ExternalRecord` de source `arxiv` (`latex_bibliography.read_eprint`). À la lecture, elles
deviennent des références au format Crossref, au texte nettoyé du LaTeX (accents,
`\newblock`, `{\em …}`, `\bibinfo`…) : `metadata_message` les prend quand la source
prioritaire (DataCite) n'a pas de bibliographie. Un nettoyage amélioré s'applique donc
sans nouveau téléchargement.

Seuls les identifiants **écrits par les auteurs** relient une référence : un DOI, ou un
identifiant arXiv (DOI `10.48550/arXiv.…`, lui-même remplacé par sa version publiée s'il
en déclare une). Les autres restent « à identifier ». Sur « Attention Is All You Need » :
40 références, 22 reliées, 18 à identifier. La fiche dit d'où vient la bibliographie, ou
pourquoi elle manque : prépublication déposée en PDF seul (environ 30 % en physique des
accélérateurs), ou sources sans bibliographie.

## Actes JACoW : ordre des auteurs incertain

L'ordre des auteurs que JACoW dépose chez DataCite ne correspond pas toujours à celui de
l'article, où l'auteur principal vient en premier, suivi des coauteurs regroupés par
laboratoire (#250). Sur `JACoW-IPAC2023-TUPA193`, DataCite met O. Piquet en tête, l'article
M. Moscatello ; OpenAlex recopie DataCite. La page JACoW n'offre aucun export structuré :
plutôt que de lire son HTML, la fiche d'une publication JACoW le signale et renvoie à sa
page, qui fait foi.
