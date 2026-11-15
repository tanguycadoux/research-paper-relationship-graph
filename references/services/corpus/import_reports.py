"""
The report of the last import of a file (#330), kept in the session until the user
closes it: a toast faded out after 6 s and left nothing after a reload.
"""

from django.utils import timezone

SESSION_KEY = "import_report"
# The lists of a report stay short: the rest is counted.
LIMIT = 20


def remember(session, report):
    """Keep an ImportReport (services/corpus/corpus_transfer.py) for the corpus page."""
    session[SESSION_KEY] = {
        "at": timezone.now().isoformat(),
        "added": shortened([(pub.pk, str(pub)) for pub in report.added]),
        "already_there": len(report.already_there),
        "without_metadata": shortened([(pub.pk, str(pub)) for pub in report.without_metadata]),
        "ignored": shortened(report.ignored),
        "unregistered": shortened(report.unregistered),
    }


def shortened(items):
    return {"items": list(items[:LIMIT]), "count": len(items)}


def last(session):
    """The report of the last import, with its lists as dicts, or None."""
    data = session.get(SESSION_KEY)
    if not data:
        return None
    return {
        **data,
        "at": timezone.datetime.fromisoformat(data["at"]),
        "added": publications(data["added"]),
        "without_metadata": publications(data["without_metadata"]),
        "ignored": titles(data["ignored"]),
        "unregistered": titles(data["unregistered"]),
    }


def publications(part):
    items = [{"pk": pk, "title": title} for pk, title in part["items"]]
    return {"items": items, "count": part["count"], "rest": part["count"] - len(items)}


def titles(part):
    items = [title or "Entrée sans titre" for title in part["items"]]
    return {"items": items, "count": part["count"], "rest": part["count"] - len(items)}


def forget(session):
    session.pop(SESSION_KEY, None)
