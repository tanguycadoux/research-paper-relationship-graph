"""
Server side of the graph benchmark (#202): time and SQL queries of the data of each graph
(services/display/graph.py), and the size of the JSON put in the page.

    DJANGO_DEBUG=1 python tools/graph_bench/server.py --user bench

Also prints the size of the base, and a session cookie of the user for bench.py (the
graph of a corpus needs a logged-in user).
"""

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import (  # noqa: E402
    BACKEND_SESSION_KEY,
    HASH_SESSION_KEY,
    SESSION_KEY,
    get_user_model,
)
from django.contrib.sessions.backends.db import SessionStore  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.models import Count  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402

from references.models import Author, CitedReference, Publication  # noqa: E402
from references.services.display.graph import (  # noqa: E402
    base_graph,
    corpus_graph,
    publication_graph,
)


def measure(build, repeat):
    times = []
    for _ in range(repeat):
        with CaptureQueriesContext(connection) as queries:
            start = time.perf_counter()
            graph = build()
            times.append((time.perf_counter() - start) * 1000)
    return {
        "ms": round(statistics.median(times)),
        "queries": len(queries),
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
        "jsonKB": round(len(json.dumps(graph)) / 1024),
    }


def session_of(user):
    session = SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.create()
    return session.session_key


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--user", default="bench")
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()
    user = get_user_model().objects.get(username=args.user)
    hub = Publication.objects.annotate(n=Count("citations")).order_by("-n", "pk").first()
    print(
        json.dumps(
            {
                "publications": Publication.objects.count(),
                "citations": CitedReference.objects.filter(target__isnull=False).count(),
                "authors": Author.objects.count(),
                "undated": Publication.objects.filter(publication_date__isnull=True).count(),
                "mostCited": {"pk": hub.pk, "title": hub.title[:60], "citedBy": hub.n},
            }
        )
    )
    graphs = {
        "base": lambda: base_graph(user),
        "corpus": lambda: corpus_graph(user),
        f"publication {hub.pk}": lambda: publication_graph(hub),
    }
    for name, build in graphs.items():
        print(json.dumps({"graph": name, **measure(build, args.repeat)}))
    print(json.dumps({"session": session_of(user)}))


if __name__ == "__main__":
    main()
