"""
Grow a copy of the base with real publications, for the graph benchmark (#202).

Never run it on a base you care about: it adds publications to the shared base, from the
real sources (Crossref, DataCite, OpenAlex, ORCID). Copy db.sqlite3 into a working copy
of the repository (a git worktree) and run it there, with DJANGO_DEBUG=1 so that the
responses are kept in .http_cache.sqlite.

    DJANGO_DEBUG=1 python tools/graph_bench/grow_base.py --target 2500

Two ways to grow it, both through the services of the application:
- the chain: the publications cited by the corpus of the benchmark user are added to its
  corpus, level by level (the most cited first), so that their own bibliographies are
  imported; it stops at the target number of publications in the base;
- unrelated articles: well-known articles of distant fields, with their bibliographies,
  which form groups without any link to the rest (#230).
"""

import argparse
import collections
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.db.models import Count  # noqa: E402

from references.models import Author, CitedReference, Publication, UserPublication  # noqa: E402
from references.services.corpus.entries import add_to_corpus  # noqa: E402
from references.services.sources import http  # noqa: E402

# Articles of distant fields, much cited, with a bibliography deposited at Crossref.
UNRELATED = [
    "10.1038/s41586-021-03819-2",  # AlphaFold (biology)
    "10.1126/science.1225829",  # CRISPR-Cas9 (biology)
    "10.1016/j.cell.2011.02.013",  # Hallmarks of cancer (medicine)
    "10.1056/nejmoa2034577",  # BNT162b2 vaccine (medicine)
    "10.1038/nature14539",  # Deep learning (computer science)
    "10.1109/cvpr.2016.90",  # ResNet (computer science)
    "10.1145/3065386",  # ImageNet classification (computer science)
    "10.1257/aer.91.5.1369",  # Colonial origins of development (economics)
    "10.1038/nclimate1783",  # Climate change and species (climate)
    "10.1126/science.1228026",  # Global forest change (climate)
    "10.1038/nature11234",  # Human microbiome (biology)
    "10.1103/physrevlett.116.061102",  # Gravitational waves (physics, 1 000 authors)
]

REQUESTS = collections.Counter()


def count_requests():
    """Count the requests sent to each source, apart from those answered by the cache."""
    send = http._request

    def counted(url, params, headers, service, subject, contact, stream=False):
        response = send(url, params, headers, service, subject, contact, stream)
        cached = getattr(response, "from_cache", False) is True
        REQUESTS[(service, "cache" if cached else "network")] += 1
        return response

    http._request = counted


def bench_user():
    user, _ = get_user_model().objects.get_or_create(username="bench")
    return user


def size(user):
    return {
        "publications": Publication.objects.count(),
        "citations": CitedReference.objects.filter(target__isnull=False).count(),
        "authors": Author.objects.count(),
        "corpus": UserPublication.objects.filter(user=user).count(),
    }


def add(user, pub, errors):
    try:
        if add_to_corpus(user, pub) is None:
            errors.append(f"{pub.doi}: métadonnées indisponibles")
    except Exception as error:  # noqa: BLE001 — the benchmark lists them instead of stopping
        errors.append(f"{pub.doi}: {type(error).__name__}: {error}")


def next_level(user, limit):
    """Cited publications with a DOI not in the corpus yet, the most cited first."""
    corpus = UserPublication.objects.filter(user=user).values("publication")
    return list(
        Publication.objects.filter(citations__source__in=corpus)
        .exclude(pk__in=corpus)
        .exclude(doi="")
        .annotate(cited=Count("citations"))
        .order_by("-cited", "pk")[:limit]
    )


def grow(target, per_level, levels):
    count_requests()
    user = bench_user()
    errors = []
    # Level 0: the corpora of the base, already imported.
    for entry in UserPublication.objects.exclude(user=user).select_related("publication"):
        if entry.publication.doi:
            add(user, entry.publication, errors)
    print("niveau 0", size(user), flush=True)
    for level in range(1, levels + 1):
        if Publication.objects.count() >= target:
            break
        for pub in next_level(user, per_level):
            add(user, pub, errors)
            if Publication.objects.count() >= target:
                break
        print(f"niveau {level}", size(user), flush=True)
    for doi in UNRELATED:
        pub = Publication.objects.get_or_create_doi(doi)
        add(user, pub, errors)
    print("sans lien", size(user), flush=True)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--target", type=int, default=2500, help="publications de la base")
    parser.add_argument("--per-level", type=int, default=120, help="ajouts par niveau")
    parser.add_argument("--levels", type=int, default=4)
    args = parser.parse_args()
    start = time.monotonic()
    with http.patient_requests():
        errors = grow(args.target, args.per_level, args.levels)
    print(f"durée : {time.monotonic() - start:.0f} s")
    print("requêtes :", dict(sorted(REQUESTS.items())))
    print("sans date :", Publication.objects.filter(publication_date__isnull=True).count())
    big = (
        Publication.objects.annotate(n=Count("authorpublication"))
        .filter(n__gt=100)
        .values_list("doi", "n")
    )
    print("plus de 100 auteurs :", list(big))
    print(f"erreurs ({len(errors)}) :")
    for error in errors:
        print(" -", error)


if __name__ == "__main__":
    main()
